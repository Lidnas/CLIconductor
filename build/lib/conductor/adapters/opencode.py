import asyncio
import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List
from conductor.process import ProcessHandle
from conductor.adapters.base import Adapter, Session, NormalizedEvent
from conductor.models import FailureClass


def _env():
    env = dict(os.environ)
    return env


class OpenCodeSession(Session):
    pass


class OpenCodeAdapter(Adapter):
    name = "opencode"

    def __init__(self, binary: str = "opencode", model: str = "opencode/big-pickle"):
        import shutil
        self.binary = shutil.which(binary) or binary
        self.model = model
        self._procs: Dict[str, ProcessHandle] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._seqs: Dict[str, int] = {}
        self._done: Dict[str, bool] = {}

    def capabilities(self) -> Dict:
        return {"stream": True, "resume": True, "mcp": True, "cancel": True, "json": True}

    async def start(self, task, workspace, role, context):
        sid = "oc_" + uuid.uuid4().hex[:8]
        task_id = task.task_id if hasattr(task, "task_id") else str(task)
        agent_id = context.get("agent_id", "")
        sess = Session(session_id=sid, agent_id=agent_id, cli="opencode", task_id=task_id,
                       workspace=workspace, role=role, started_at=time.time())
        prompt = context.get("prompt", task.objective if hasattr(task, "objective") else str(task))
        cmd = [self.binary, "run", "--format", "json", "--model", self.model, "--auto", prompt]
        await self._spawn(sess, cmd, workspace)
        return sess

    async def _spawn(self, sess, cmd, cwd):
        loop = asyncio.get_event_loop()
        q = asyncio.Queue()
        self._queues[sess.session_id] = q
        self._seqs[sess.session_id] = 0
        self._done[sess.session_id] = False

        def on_line(line, seq):
            # store seq later
            try:
                loop.call_soon_threadsafe(q.put_nowait, ("line", line))
            except Exception:
                pass

        ph = ProcessHandle(cmd, cwd=cwd, env=_env(), on_line=on_line)
        ph.start()
        sess.process = ph
        self._procs[sess.session_id] = ph
        # async task to read queue and normalize
        asyncio.create_task(self._pump_safe(sess, ph, q))

    async def _pump(self, sess, ph, q):
        native_sid = ""
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if not ph.is_alive() and q.empty():
                    break
                continue
            if item is None:
                break
            _, line = item
            line = line.rstrip("\n")
            if not line.strip():
                continue
            self._seqs[sess.session_id] += 1
            seq = self._seqs[sess.session_id]
            # try parse json
            content = line
            evtype = "stdout"
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if "sessionID" in obj and not native_sid:
                        native_sid = obj["sessionID"]
                        sess.native_session_id = native_sid
                    # text events
                    if obj.get("type") == "text":
                        part = obj.get("part", {})
                        t = part.get("text", "")
                        content = t
                        evtype = "stdout"
                    elif obj.get("type") == "error":
                        evtype = "error"
                        content = json.dumps(obj)
                    else:
                        evtype = "stdout"
                        content = line
            except json.JSONDecodeError:
                evtype = "stdout"
                content = line
            ev = NormalizedEvent(seq=seq, timestamp=time.time(), type=evtype, content=content, raw=line)
            # push to a stored list for stream() consumers
            self._queues[sess.session_id + "_events"] = self._queues.get(sess.session_id + "_events") or asyncio.Queue()
            await self._queues[sess.session_id + "_events"].put(ev)
        # process done
        self._done[sess.session_id] = True
        # emit final status
        self._seqs[sess.session_id] += 1
        seq = self._seqs[sess.session_id]
        ec = ph.exit_code
        ev = NormalizedEvent(seq=seq, timestamp=time.time(), type="status", content=f"exit:{ec if ec is not None else -1}")
        q2 = self._queues.get(sess.session_id + "_events")
        if q2:
            await q2.put(ev)

    async def _pump_safe(self, sess, ph, q):
        try:
            await self._pump(sess, ph, q)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._done[sess.session_id] = True
            evq = self._queues.get(sess.session_id + "_events")
            if evq:
                self._seqs[sess.session_id] += 1
                await evq.put(NormalizedEvent(seq=self._seqs[sess.session_id], timestamp=time.time(), type="status", content=f"exit:{ph.exit_code if ph.exit_code is not None else -1}"))

    async def send(self, session, message):
        # follow-up via session resume
        sid = session.native_session_id or session.session_id
        cmd = [self.binary, "run", "--format", "json", "--session", sid, "--auto", message]
        # run as separate process but stream into same queue? We'll spawn and pump into same events queue
        await self._spawn_followup(session, cmd, session.workspace)

    async def _spawn_followup(self, sess, cmd, cwd):
        loop = asyncio.get_event_loop()
        q = asyncio.Queue()
        # reuse events queue
        evq = self._queues.get(sess.session_id + "_events")
        if evq is None:
            evq = asyncio.Queue()
            self._queues[sess.session_id + "_events"] = evq

        def on_line(line, seq):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ("line", line))
            except Exception:
                pass

        ph = ProcessHandle(cmd, cwd=cwd, env=_env(), on_line=on_line)
        ph.start()
        # pump
        async def pump():
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if not ph.is_alive() and q.empty():
                        break
                    continue
                if item is None:
                    break
                _, line = item
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                self._seqs[sess.session_id] += 1
                seq = self._seqs[sess.session_id]
                content = line
                evtype = "stdout"
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("type") == "text":
                        content = obj.get("part", {}).get("text", "")
                except Exception:
                    pass
                ev = NormalizedEvent(seq=seq, timestamp=time.time(), type=evtype, content=content, raw=line)
                await evq.put(ev)
            self._seqs[sess.session_id] += 1
            seq = self._seqs[sess.session_id]
            await evq.put(NormalizedEvent(seq=seq, timestamp=time.time(), type="status", content=f"exit:{ph.exit_code if ph.exit_code is not None else -1}"))
        asyncio.create_task(pump())

    async def stream(self, session):
        evq = self._queues.get(session.session_id + "_events")
        if evq is None:
            evq = asyncio.Queue()
            self._queues[session.session_id + "_events"] = evq
        # yield until done and queue empty
        while True:
            try:
                ev = await asyncio.wait_for(evq.get(), timeout=0.5)
                yield ev
                continue
            except asyncio.TimeoutError:
                pass
            ph = self._procs.get(session.session_id)
            if self._done.get(session.session_id):
                # drain remaining
                while True:
                    try:
                        ev = evq.get_nowait()
                        yield ev
                    except Exception:
                        break
                break
            if ph is not None and not ph.is_alive():
                await asyncio.sleep(0.5)
                if self._done.get(session.session_id):
                    continue
                # fallback: drain and break
                while True:
                    try:
                        ev = evq.get_nowait()
                        yield ev
                    except Exception:
                        break
                break
            continue

    async def cancel(self, session, graceful=True):
        ph = self._procs.get(session.session_id)
        if ph is not None:
            ph.cancel(graceful_timeout=5.0, force=not graceful)

    async def health(self, session):
        ph = self._procs.get(session.session_id)
        if ph is None:
            return "unknown"
        if ph.is_alive():
            return "live"
        if ph.exit_code == 0:
            return "finished"
        return "crashed"

    async def resume(self, session):
        # try resume via session id
        return True

    def classify_failure(self, output, exit_code):
        low = (output or "").lower()
        if "auth" in low or "unauthorized" in low or "401" in low:
            return FailureClass.AUTH.value
        if "rate" in low and "limit" in low or "429" in low:
            return FailureClass.RATE_LIMIT.value
        if "model" in low and ("not found" in low or "unavailable" in low):
            return FailureClass.MODEL_UNAVAILABLE.value
        if "crash" in low or (exit_code is not None and exit_code < 0):
            return FailureClass.CRASH.value
        if "unexpected" in low and "prompt" in low:
            return FailureClass.UNEXPECTED_PROMPT.value
        return FailureClass.UNKNOWN.value
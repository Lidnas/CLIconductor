import asyncio
import time
import uuid
from typing import Any, AsyncIterator, Dict, List
from tests.base_adapter import Adapter, Session, NormalizedEvent
from conductor.models import FailureClass


class MockBehavior:
    def __init__(self, **kw):
        self.delay = kw.get("delay", 0.0)
        self.crash = kw.get("crash", False)
        self.malformed = kw.get("malformed", False)
        self.hang = kw.get("hang", False)
        self.false_complete = kw.get("false_complete", False)
        self.output = kw.get("output", "mock done")
        self.exit_code = kw.get("exit_code", 0)
        self.auth_fail = kw.get("auth_fail", False)
        self.rate_limit = kw.get("rate_limit", False)
        self.token_to_emit = kw.get("token_to_emit", None)  # for message test
        self.progress_events = kw.get("progress_events", 0)


class MockCLI(Adapter):
    name = "mock"

    def __init__(self, behavior: MockBehavior = None):
        self.behavior = behavior or MockBehavior()
        self._sessions: Dict[str, Session] = {}
        self._streams: Dict[str, List[NormalizedEvent]] = {}
        self._seq = 0

    def capabilities(self) -> Dict:
        return {"stream": True, "resume": True, "mcp": False, "cancel": True}

    async def start(self, task, workspace, role, context):
        sid = "mocksess_" + uuid.uuid4().hex[:8]
        sess = Session(session_id=sid, agent_id=context.get("agent_id", ""), cli="mock",
                       task_id=task.task_id if hasattr(task, "task_id") else str(task),
                       workspace=workspace, role=role, started_at=time.time())
        self._sessions[sid] = sess
        self._streams[sid] = []
        # run behavior in background
        asyncio.create_task(self._run(sess))
        return sess

    async def _run(self, sess):
        b = self.behavior
        if b.delay:
            await asyncio.sleep(b.delay)
        if b.hang:
            await asyncio.sleep(2)
            return
        if b.auth_fail:
            await self._emit(sess, "error", "auth failure: invalid credentials")
            await self._emit(sess, "status", "exit:1")
            return
        if b.rate_limit:
            await self._emit(sess, "error", "rate limit exceeded 429")
            await self._emit(sess, "status", "exit:1")
            return
        # emit progress events
        for i in range(b.progress_events):
            await self._emit(sess, "stdout", f"progress {i}")
            await asyncio.sleep(0.05)
        if b.token_to_emit:
            await self._emit(sess, "stdout", f"RECEIVED_TOKEN={b.token_to_emit}")
        if b.malformed:
            await self._emit(sess, "stdout", "{broken json")
        await self._emit(sess, "stdout", b.output)
        if b.false_complete:
            await self._emit(sess, "stdout", "TASK_COMPLETE")
        if b.crash:
            await self._emit(sess, "error", "crashed")
            # simulate process death
            sess.metadata["crashed"] = True
            return
        await self._emit(sess, "status", f"exit:{b.exit_code}")

    async def _emit(self, sess, typ, content):
        self._seq += 1
        ev = NormalizedEvent(seq=self._seq, timestamp=time.time(), type=typ, content=content)
        self._streams[sess.session_id].append(ev)

    async def send(self, session, message):
        # agent-initiated not supported; orchestrator appends as stdout-ish? record
        self._seq += 1
        self._streams[session.session_id].append(
            NormalizedEvent(seq=self._seq, timestamp=time.time(), type="instruction", content=message))

    async def stream(self, session):
        # yield existing + poll
        idx = 0
        while True:
            lst = self._streams.get(session.session_id, [])
            while idx < len(lst):
                yield lst[idx]
                idx += 1
            if not self.is_running(session) and idx >= len(lst):
                break
            await asyncio.sleep(0.05)

    def is_running(self, session):
        # crude: if last event is exit/crash
        lst = self._streams.get(session.session_id, [])
        if not lst:
            return True
        last = lst[-1].content
        return not (last.startswith("exit:") or last == "crashed" or "crashed" in last)

    async def cancel(self, session, graceful=True):
        self._seq += 1
        self._streams[session.session_id].append(
            NormalizedEvent(seq=self._seq, timestamp=time.time(), type="status", content="cancelled"))
        session.metadata["cancelled"] = True

    async def health(self, session):
        return "crashed" if session.metadata.get("crashed") else ("cancelled" if session.metadata.get("cancelled") else "ok")

    async def resume(self, session):
        return True

    def classify_failure(self, output, exit_code):
        low = (output or "").lower()
        if "auth" in low:
            return FailureClass.AUTH.value
        if "rate limit" in low or "429" in low:
            return FailureClass.RATE_LIMIT.value
        if "crash" in low:
            return FailureClass.CRASH.value
        if "malformed" in low:
            return FailureClass.MALFORMED.value
        return FailureClass.UNKNOWN.value
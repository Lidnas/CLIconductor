import asyncio
import time
import hashlib
from typing import Dict, List, Optional
from conductor.models import Task, TaskState, Agent, AgentState, Event
from conductor.task_engine import TaskEngine, StaleLeaseError
from conductor.adapters.base import Adapter
from conductor.db import Store


class Scheduler:
    def __init__(self, engine: TaskEngine, store: Store, run_id: str, max_concurrency: int = 2):
        self.engine = engine
        self.store = store
        self.run_id = run_id
        self.max_concurrency = max_concurrency
        self._watchers = set()
        self.agents: Dict[str, Agent] = {}
        self.agent_adapters: Dict[str, Adapter] = {}
        self.agent_sessions: Dict[str, object] = {}
        self.paused = False
        self.paused_all = False
        self._progress_hashes: Dict[str, str] = {}  # task -> last progress hash
        self._progress_times: Dict[str, float] = {}
        self.stagnation_window = 60.0
        self._running = False

    def register_agent(self, agent: Agent, adapter: Adapter):
        self.agents[agent.agent_id] = agent
        self.agent_adapters[agent.agent_id] = adapter
        self.store.save_agent(agent, self.run_id)

    def available_agents(self, role: str = None):
        out = []
        for aid, ag in self.agents.items():
            if ag.state in (AgentState.LIVE.value, AgentState.FINISHED.value):
                if role is None or ag.role == role or ag.role == "":
                    out.append(aid)
        return out

    async def run_loop(self):
        self._running = True
        while self._running:
            self.engine.expire_leases()
            if self.paused or self.paused_all:
                await asyncio.sleep(0.5)
                continue
            # detect stagnation
            self._check_stagnation()
            # schedule
            await self._schedule_ready()
            # check completion
            active_states = {TaskState.PENDING.value, TaskState.READY.value, TaskState.LEASED.value, TaskState.RUNNING.value}
            has_active = any(t.state in active_states for t in self.engine.tasks.values())
            if (self.engine.all_done() or not has_active):
                # cancel outstanding watchers
                for w in list(self._watchers):
                    w.cancel()
                break
            await asyncio.sleep(0.5)

    def stop(self):
        self._running = False

    async def _schedule_ready(self):
        done_ids = self.engine.done_ids()
        ready = self.engine.ready_set(done_ids)
        # cap concurrency: count running/leased
        active = sum(1 for t in self.engine.tasks.values() if t.state in (TaskState.LEASED.value, TaskState.RUNNING.value))
        for tid in ready:
            if active >= self.max_concurrency:
                break
            t = self.engine.tasks[tid]
            # pick agent by role
            candidates = self.available_agents(t.role)
            if not candidates:
                # any available
                candidates = self.available_agents()
            if not candidates:
                continue
            aid = candidates[0]
            ag = self.agents[aid]
            adapter = self.agent_adapters[aid]
            # lease
            try:
                lease = self.engine.lease(tid, aid)
            except Exception:
                continue
            ag.state = AgentState.BUSY.value
            self.store.save_agent(ag, self.run_id)
            # start
            workspace = ag.workspace
            ctx = {"agent_id": aid, "prompt": t.objective, "run_id": self.run_id}
            try:
                sess = await adapter.start(t, workspace, t.role or "implementer", ctx)
                self.agent_sessions[aid] = sess
                t.state = TaskState.RUNNING.value
                t.updated_at = time.time()
                self.store.save_task(t, self.run_id)
                self._progress_times[tid] = time.time()
                active += 1
                w = asyncio.create_task(self._watch_task(t, aid, adapter, sess, lease.fencing_token))
                self._watchers.add(w)
                w.add_done_callback(self._watchers.discard)
            except Exception as e:
                # fail task
                try:
                    self.engine.transition(tid, TaskState.FAILED.value, actor="scheduler", reason=str(e))
                except Exception:
                    pass
                ag.state = AgentState.LIVE.value
                self.store.save_agent(ag, self.run_id)

    async def _watch_task(self, task, agent_id, adapter, sess, fencing_token):
        ag = self.agents[agent_id]
        # collect stream; detect completion
        full_output = []
        try:
            async for ev in adapter.stream(sess):
                full_output.append(ev.content)
                # progress signal: new output doesn't count; but we update last_progress on verified artifact? 
                # For mock, completion signaled by exit status
                if ev.type == "status" and ev.content.startswith("exit:"):
                    ec = int(ev.content.split(":", 1)[1])
                    if ec == 0:
                        # task done -> verifying later; mark needs_review? We'll mark verifying
                        try:
                            self.engine.transition(task.task_id, TaskState.VERIFYING.value, actor="agent", reason="agent completed")
                        except Exception:
                            pass
                    else:
                        fc = adapter.classify_failure("\n".join(full_output), ec)
                        try:
                            if fc == "auth":
                                self.engine.transition(task.task_id, TaskState.FAILED.value, actor="scheduler", reason="auth failure")
                            else:
                                # retry or fail
                                t = self.engine.tasks[task.task_id]
                                if t.attempts < t.max_attempts:
                                    self.engine.transition(task.task_id, TaskState.READY.value, actor="scheduler", reason="retry")
                                else:
                                    self.engine.transition(task.task_id, TaskState.FAILED.value, actor="scheduler", reason="max attempts")
                        except Exception:
                            pass
            # after stream ends
        except Exception as e:
            try:
                self.engine.transition(task.task_id, TaskState.FAILED.value, actor="scheduler", reason=str(e))
            except Exception:
                pass
        # release lease with fencing
        try:
            self.engine.release_lease(task.task_id, fencing_token, result="\n".join(full_output), success=True)
        except StaleLeaseError:
            pass
        ag.state = AgentState.LIVE.value
        self.store.save_agent(ag, self.run_id)
        # store task output
        t = self.engine.tasks[task.task_id]
        t.result = "\n".join(full_output)
        self.store.save_task(t, self.run_id)

    def _check_stagnation(self):
        now = time.time()
        for tid, t in self.engine.tasks.items():
            if t.state == TaskState.RUNNING.value:
                if tid not in self._progress_times:
                    self._progress_times[tid] = now
                # hash of result? use task result
                h = hashlib.sha256((t.result or "").encode()).hexdigest()
                if tid in self._progress_hashes and self._progress_hashes[tid] == h:
                    if now - self._progress_times.get(tid, now) > self.stagnation_window:
                        # stagnation
                        self._progress_times[tid] = now
                        try:
                            self.engine.transition(tid, TaskState.BLOCKED.value, actor="scheduler", reason="stagnation")
                        except Exception:
                            pass
                else:
                    self._progress_hashes[tid] = h
                    self._progress_times[tid] = now

    async def pause(self):
        self.paused = True

    async def pause_all(self):
        self.paused_all = True
        # cancel running? "pause all safely pausable" - just stop scheduling; running continue
    async def resume(self):
        self.paused = False
        self.paused_all = False

    def message_agent(self, agent_id, message):
        sess = self.agent_sessions.get(agent_id)
        adapter = self.agent_adapters.get(agent_id)
        if sess and adapter:
            asyncio.ensure_future(adapter.send(sess, message))
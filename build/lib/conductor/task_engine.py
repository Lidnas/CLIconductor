import time
import hashlib
from conductor.models import Task, TaskState, LEGAL_TRANSITIONS, Event, Lease
from conductor.dag import detect_cycle
from conductor.db import Store


class TaskEngine:
    def __init__(self, store: Store, run_id: str):
        self.store = store
        self.run_id = run_id
        self.tasks: dict = {}  # task_id -> Task
        self._fencing_counter = 0

    def load(self):
        for d in self.store.list_tasks(self.run_id):
            t = Task(**{k: d[k] for k in Task.__dataclass_fields__ if k in d})
            self.tasks[t.task_id] = t

    def create_task(self, objective, role="", dependencies=None, priority=0, metadata=None, task_id=None):
        t = Task(objective=objective, role=role, dependencies=list(dependencies or []),
                 priority=priority, metadata=dict(metadata or {}))
        if task_id:
            t.task_id = task_id
        # cycle check
        tmp = {tid: list(t2.dependencies) for tid, t2 in self.tasks.items()}
        tmp[t.task_id] = list(t.dependencies)
        cyc, cycle = detect_cycle(tmp)
        if cyc:
            raise ValueError(f"circular dependency: {cycle}")
        self.tasks[t.task_id] = t
        self.store.save_task(t, self.run_id)
        self._event("task_created", task_id=t.task_id, actor="orchestrator", reason="created")
        return t

    def transition(self, task_id, new_state, actor="orchestrator", reason=""):
        t = self.tasks[task_id]
        if TaskState(new_state) not in LEGAL_TRANSITIONS[TaskState(t.state)]:
            raise ValueError(f"illegal transition {t.state} -> {new_state}")
        old = t.state
        t.state = new_state
        t.updated_at = time.time()
        self.store.save_task(t, self.run_id)
        self._event("task_state_changed", task_id=task_id, actor=actor, reason=reason or f"{old}->{new_state}",
                    payload={"from": old, "to": new_state})
        return t

    def _event(self, typ, task_id="", agent_id="", actor="", reason="", payload=None):
        ev = Event(run_id=self.run_id, task_id=task_id, agent_id=agent_id, type=typ, actor=actor, reason=reason, payload=payload)
        self.store.append_event(ev, self.run_id)

    def lease(self, task_id, agent_id, ttl=300.0):
        t = self.tasks[task_id]
        if t.state not in (TaskState.READY.value, TaskState.PENDING.value):
            # allow re-lease from ready
            pass
        self._fencing_counter += 1
        ft = self._fencing_counter
        lease = Lease(task_id=task_id, agent_id=agent_id, fencing_token=ft,
                      expires_at=time.time() + ttl)
        t.lease_id = lease.lease_id
        t.fencing_token = ft
        t.assignee = agent_id
        t.attempts += 1
        self.transition(task_id, TaskState.LEASED.value, actor="scheduler", reason=f"leased to {agent_id}")
        self.store.save_lease(lease)
        return lease

    def release_lease(self, task_id, fencing_token, result=None, success=True):
        t = self.tasks[task_id]
        if t.fencing_token != fencing_token:
            # stale
            raise StaleLeaseError("fencing token mismatch")
        self.store.delete_lease(task_id)
        t.lease_id = ""
        if success:
            t.result = result
        return t

    def expire_leases(self):
        now = time.time()
        for tid, t in list(self.tasks.items()):
            if t.state == TaskState.LEASED.value:
                lease = self.store.load_lease(tid)
                if lease and lease["expires_at"] < now:
                    # expire
                    try:
                        self.transition(tid, TaskState.READY.value, actor="scheduler", reason="lease expired")
                    except Exception:
                        pass
                    self.store.delete_lease(tid)
                    t.lease_id = ""

    def ready_set(self, done_ids):
        out = []
        for tid, t in self.tasks.items():
            if t.state in (TaskState.PENDING.value, TaskState.READY.value):
                if all(d in done_ids for d in t.dependencies):
                    if t.state == TaskState.PENDING.value:
                        self.transition(tid, TaskState.READY.value, actor="scheduler", reason="deps satisfied")
                    out.append(tid)
        return out

    def done_ids(self):
        return {tid for tid, t in self.tasks.items() if t.state == TaskState.DONE.value}

    def all_done(self):
        return all(t.state in (TaskState.DONE.value, TaskState.CANCELLED.value, TaskState.FAILED.value, TaskState.ABANDONED.value) for t in self.tasks.values()) and len(self.tasks) > 0

    def cancel_run_tasks(self):
        for tid, t in self.tasks.items():
            if t.state not in (TaskState.DONE.value, TaskState.FAILED.value, TaskState.CANCELLED.value):
                try:
                    self.transition(tid, TaskState.CANCELLED.value, actor="user", reason="run cancelled")
                except Exception:
                    pass


class StaleLeaseError(Exception):
    pass
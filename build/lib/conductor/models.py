import uuid
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional, List, Dict


def new_id(prefix="id"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    LEASED = "leased"
    RUNNING = "running"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


LEGAL_TRANSITIONS = {
    TaskState.PENDING: {TaskState.READY, TaskState.CANCELLED},
    TaskState.READY: {TaskState.LEASED, TaskState.CANCELLED},
    TaskState.LEASED: {TaskState.RUNNING, TaskState.READY, TaskState.CANCELLED, TaskState.ABANDONED},
    TaskState.RUNNING: {TaskState.BLOCKED, TaskState.NEEDS_REVIEW, TaskState.VERIFYING, TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.BLOCKED: {TaskState.READY, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.NEEDS_REVIEW: {TaskState.VERIFYING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.VERIFYING: {TaskState.DONE, TaskState.FAILED, TaskState.NEEDS_REVIEW, TaskState.CANCELLED},
    TaskState.DONE: set(),
    TaskState.FAILED: {TaskState.READY, TaskState.CANCELLED},
    TaskState.CANCELLED: set(),
    TaskState.ABANDONED: {TaskState.READY},
}


class AgentState(str, Enum):
    LIVE = "live"
    BUSY = "busy"
    BLOCKED = "blocked"
    CRASHED = "crashed"
    STALLED = "stalled"
    FINISHED = "finished"
    ABANDONED = "abandoned"


class MsgType(str, Enum):
    TASK_ASSIGN = "task_assign"
    RESULT = "result"
    QUESTION = "question"
    FINDING = "finding"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESULT = "review_result"
    CHALLENGE = "challenge"
    BLOCKER = "blocker"
    ESCALATION = "escalation"
    STATUS = "status"
    INSTRUCTION = "instruction"


class MsgStatus(str, Enum):
    QUEUED = "queued"
    DELIVERED = "delivered"
    ACKED = "acked"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class Message:
    message_id: str = field(default_factory=lambda: new_id("msg"))
    correlation_id: str = ""
    task_id: str = ""
    sender: str = ""
    recipient: str = ""
    type: str = MsgType.STATUS.value
    timestamp: float = field(default_factory=time.time)
    payload: Any = None
    status: str = MsgStatus.QUEUED.value
    attempts: int = 0
    idempotency_key: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: new_id("task"))
    objective: str = ""
    state: str = TaskState.PENDING.value
    role: str = ""
    assignee: str = ""
    dependencies: List[str] = field(default_factory=list)
    lease_id: str = ""
    fencing_token: int = 0
    attempts: int = 0
    max_attempts: int = 3
    priority: int = 0
    metadata: Dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: Any = None
    failure_reason: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Lease:
    lease_id: str = field(default_factory=lambda: new_id("lease"))
    task_id: str = ""
    agent_id: str = ""
    fencing_token: int = 0
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0
    heartbeat_at: float = field(default_factory=time.time)


@dataclass
class Agent:
    agent_id: str = field(default_factory=lambda: new_id("agent"))
    cli: str = ""
    role: str = ""
    instance: int = 0
    state: str = AgentState.LIVE.value
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    workspace: str = ""
    branch: str = ""
    process_pid: int = 0
    session_id: str = ""
    last_progress: float = field(default_factory=time.time)
    capabilities: Dict = field(default_factory=dict)


@dataclass
class Criterion:
    criterion_id: str = field(default_factory=lambda: new_id("crit"))
    description: str = ""
    verifier: str = ""  # command
    expected_exit: int = 0
    verifier_type: str = "command"  # command|deterministic|human_signoff|reviewer_evidence
    status: str = "pending"
    evidence: Dict = field(default_factory=dict)


@dataclass
class Event:
    event_id: str = field(default_factory=lambda: new_id("evt"))
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    type: str = ""
    actor: str = ""
    reason: str = ""
    payload: Any = None


@dataclass
class Run:
    run_id: str = field(default_factory=lambda: new_id("run"))
    objective: str = ""
    state: str = "running"
    created_at: float = field(default_factory=time.time)
    base_commit: str = ""
    integration_branch: str = ""
    criteria: List[Criterion] = field(default_factory=list)
    budget: Dict = field(default_factory=dict)


class FailureClass(str, Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNEXPECTED_PROMPT = "unexpected_prompt"
    CRASH = "crash"
    MALFORMED = "malformed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
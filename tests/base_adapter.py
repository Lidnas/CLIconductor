import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict
from abc import ABC, abstractmethod


@dataclass
class NormalizedEvent:
    seq: int
    timestamp: float
    type: str
    content: str
    raw: Any = None


@dataclass
class Session:
    session_id: str
    agent_id: str
    cli: str
    task_id: str
    workspace: str
    role: str
    process: Any = None
    native_session_id: str = ""
    started_at: float = 0.0
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Adapter(ABC):
    name: str = "base"

    @abstractmethod
    def capabilities(self) -> Dict: ...

    @abstractmethod
    async def start(self, task, workspace, role, context): ...

    @abstractmethod
    async def send(self, session, message): ...

    @abstractmethod
    def stream(self, session) -> AsyncIterator[NormalizedEvent]: ...

    @abstractmethod
    async def cancel(self, session, graceful=True): ...

    @abstractmethod
    async def health(self, session): ...

    @abstractmethod
    async def resume(self, session): ...

    @abstractmethod
    def classify_failure(self, output, exit_code): ...
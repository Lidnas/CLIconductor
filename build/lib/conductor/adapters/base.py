from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, List, Dict, AsyncIterator
import time


@dataclass
class NormalizedEvent:
    seq: int
    timestamp: float
    type: str  # stdout|stderr|status|error|result
    content: str
    raw: Any = None


class Adapter(ABC):
    name: str = "base"

    @abstractmethod
    def capabilities(self) -> Dict:
        ...

    @abstractmethod
    async def start(self, task, workspace: str, role: str, context: dict) -> "Session":
        ...

    @abstractmethod
    async def send(self, session: "Session", message: str) -> None:
        ...

    @abstractmethod
    def stream(self, session: "Session") -> AsyncIterator[NormalizedEvent]:
        ...

    @abstractmethod
    async def cancel(self, session: "Session", graceful: bool = True) -> None:
        ...

    @abstractmethod
    async def health(self, session: "Session") -> str:
        ...

    @abstractmethod
    async def resume(self, session: "Session") -> bool:
        ...

    @abstractmethod
    def classify_failure(self, output: str, exit_code: Optional[int]) -> str:
        ...


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
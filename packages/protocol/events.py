from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


def generate_uuid() -> str:
    return str(uuid4())


def get_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseEvent(BaseModel):
    type: str
    request_id: str = Field(default_factory=generate_uuid)
    workspace_id: str = "default"
    session_id: Optional[str] = None
    timestamp: str = Field(default_factory=get_utc_now)


# --- Session Events ---
class SessionConnectedEvent(BaseEvent):
    type: Literal["session.connected"] = "session.connected"
    user_id: Optional[str] = None


class SessionDisconnectedEvent(BaseEvent):
    type: Literal["session.disconnected"] = "session.disconnected"


# --- Terminal Events ---
class TerminalInputEvent(BaseEvent):
    type: Literal["terminal.input"] = "terminal.input"
    data: str


class TerminalOutputEvent(BaseEvent):
    type: Literal["terminal.output"] = "terminal.output"
    data: str


class TerminalResizeEvent(BaseEvent):
    type: Literal["terminal.resize"] = "terminal.resize"
    cols: int
    rows: int


from pydantic import BaseModel, Field, field_validator


# --- Agent Events ---
class AgentStartEvent(BaseEvent):
    type: Literal["agent.start"] = "agent.start"
    prompt: str

    @field_validator("prompt", mode="before")
    @classmethod
    def convert_prompt(cls, v):
        if isinstance(v, dict):
            return str(v.get("prompt", ""))
        return str(v)


class AgentStatusEvent(BaseEvent):
    type: Literal["agent.status"] = "agent.status"
    status: str
    phase: Optional[str] = None  # e.g., "EXPLORE", "PLAN", "IMPLEMENT", "VERIFY"


class AgentMessageEvent(BaseEvent):
    type: Literal["agent.message"] = "agent.message"
    role: Literal["assistant", "system", "user"] = "assistant"
    content: str


class AgentToolStartedEvent(BaseEvent):
    type: Literal["agent.tool.started"] = "agent.tool.started"
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class AgentToolCompletedEvent(BaseEvent):
    type: Literal["agent.tool.completed"] = "agent.tool.completed"
    tool_name: str
    result: Any
    duration_ms: int = 0
    diff: Optional[str] = None
    added: int = 0
    removed: int = 0


class AgentToolFailedEvent(BaseEvent):
    type: Literal["agent.tool.failed"] = "agent.tool.failed"
    tool_name: str
    error: str
    duration_ms: int = 0


# --- Workspace & File Events ---
class FileReadRequest(BaseEvent):
    type: Literal["file.read"] = "file.read"
    path: str


class FileWriteRequest(BaseEvent):
    type: Literal["file.write"] = "file.write"
    path: str
    content: str


class FilePatchRequest(BaseEvent):
    type: Literal["file.patch"] = "file.patch"
    path: str
    target_content: str
    replacement_content: str


class FileListRequest(BaseEvent):
    type: Literal["file.list"] = "file.list"
    path: str = ""


class FileEvent(BaseEvent):
    type: Literal["file.created", "file.updated", "file.deleted"]
    path: str


# --- Process Events ---
class ProcessStartRequest(BaseEvent):
    type: Literal["process.start"] = "process.start"
    command: str
    cwd: Optional[str] = None


class ProcessStopRequest(BaseEvent):
    type: Literal["process.stop"] = "process.stop"
    process_id: str


class ProcessEvent(BaseEvent):
    type: Literal["process.started", "process.exited", "process.failed"]
    process_id: str
    command: str
    pid: Optional[int] = None
    status: Literal["STARTING", "RUNNING", "STOPPED", "FAILED"]
    exit_code: Optional[int] = None


# --- Preview & Port Events ---
class PortUpdateEvent(BaseEvent):
    type: Literal["preview.ports_updated"] = "preview.ports_updated"
    ports: List[str] = Field(default_factory=list)


class PreviewReadyEvent(BaseEvent):
    type: Literal["preview.ready"] = "preview.ready"
    port: str
    url: str


# --- Approval & Error Events ---
class ApprovalRequiredEvent(BaseEvent):
    type: Literal["approval.required"] = "approval.required"
    action_id: str
    operation: str
    command_or_path: str
    risk_level: Literal["restricted", "destructive", "privileged"]
    description: str


class ApprovalResponseEvent(BaseEvent):
    type: Literal["approval.response"] = "approval.response"
    action_id: str
    approved: bool


class ErrorEvent(BaseEvent):
    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

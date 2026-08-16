from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field


class WorkspaceStatus(str, Enum):
    CREATING = "CREATING"
    STARTING = "STARTING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


VALID_TRANSITIONS = {
    WorkspaceStatus.CREATING: {WorkspaceStatus.STARTING, WorkspaceStatus.FAILED},
    WorkspaceStatus.STARTING: {WorkspaceStatus.READY, WorkspaceStatus.FAILED},
    WorkspaceStatus.READY: {WorkspaceStatus.ACTIVE, WorkspaceStatus.IDLE, WorkspaceStatus.STOPPING, WorkspaceStatus.FAILED},
    WorkspaceStatus.ACTIVE: {WorkspaceStatus.IDLE, WorkspaceStatus.STOPPING, WorkspaceStatus.FAILED},
    WorkspaceStatus.IDLE: {WorkspaceStatus.ACTIVE, WorkspaceStatus.STOPPING, WorkspaceStatus.FAILED},
    WorkspaceStatus.STOPPING: {WorkspaceStatus.STOPPED, WorkspaceStatus.FAILED},
    WorkspaceStatus.STOPPED: {WorkspaceStatus.STARTING, WorkspaceStatus.CREATING},
    WorkspaceStatus.FAILED: {WorkspaceStatus.CREATING, WorkspaceStatus.STOPPED},
}


class WorkspaceRecord(BaseModel):
    workspace_id: str
    project_id: str
    status: WorkspaceStatus = WorkspaceStatus.CREATING
    pod_name: Optional[str] = None
    service_name: Optional[str] = None
    namespace: str = "default"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None


class WorkspaceStateMachine:
    """
    Manages state transitions for Kubernetes Workspaces.
    Enforces valid state lifecycle and handles recovery.
    """

    def __init__(self):
        self.workspaces: Dict[str, WorkspaceRecord] = {}

    def create(self, workspace_id: str, project_id: str, namespace: str = "default") -> WorkspaceRecord:
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            project_id=project_id,
            status=WorkspaceStatus.CREATING,
            namespace=namespace,
        )
        self.workspaces[workspace_id] = record
        return record

    def transition(self, workspace_id: str, target: WorkspaceStatus, error: Optional[str] = None) -> WorkspaceRecord:
        record = self.workspaces.get(workspace_id)
        if not record:
            raise ValueError(f"Workspace not found: {workspace_id}")

        allowed = VALID_TRANSITIONS.get(record.status, set())
        if target not in allowed:
            raise ValueError(f"Invalid transition from {record.status} to {target}")

        record.status = target
        record.last_active_at = datetime.now(timezone.utc).isoformat()
        if error:
            record.error = error
        return record

    def get(self, workspace_id: str) -> Optional[WorkspaceRecord]:
        return self.workspaces.get(workspace_id)

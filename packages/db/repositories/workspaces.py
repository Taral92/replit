import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models.workspace import Workspace

class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_workspace(self, project_id: uuid.UUID, user_id: uuid.UUID, status: str = 'provisioning') -> Workspace:
        workspace = Workspace(project_id=project_id, user_id=user_id, status=status)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def get_workspace(self, workspace_id: uuid.UUID) -> Optional[Workspace]:
        return await self.session.get(Workspace, workspace_id)

    async def get_user_workspaces(self, user_id: uuid.UUID, status: Optional[str] = None) -> List[Workspace]:
        stmt = select(Workspace).where(Workspace.user_id == user_id)
        if status:
            stmt = stmt.where(Workspace.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_workspace_status(self, workspace_id: uuid.UUID, status: str, container_id: Optional[str] = None) -> Optional[Workspace]:
        values = {"status": status}
        if container_id is not None:
            values["container_id"] = container_id
            
        stmt = update(Workspace).where(Workspace.id == workspace_id).values(**values).returning(Workspace)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def update_last_active(self, workspace_id: uuid.UUID) -> None:
        stmt = update(Workspace).where(Workspace.id == workspace_id).values(
            last_active_at=datetime.now(timezone.utc)
        )
        await self.session.execute(stmt)
        await self.session.commit()

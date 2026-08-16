import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models.project import Project

class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_project(self, user_id: uuid.UUID, name: str, slug: str) -> Project:
        project = Project(user_id=user_id, name=name, slug=slug)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_project(self, project_id: uuid.UUID) -> Optional[Project]:
        return await self.session.get(Project, project_id)

    async def get_user_projects(self, user_id: uuid.UUID) -> List[Project]:
        stmt = select(Project).where(
            Project.user_id == user_id,
            Project.archived_at.is_(None)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def archive_project(self, project_id: uuid.UUID) -> Optional[Project]:
        stmt = update(Project).where(Project.id == project_id).values(
            archived_at=datetime.now(timezone.utc)
        ).returning(Project)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

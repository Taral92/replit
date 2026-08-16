import pytest
import uuid
from packages.db.repositories.projects import ProjectRepository

@pytest.mark.asyncio
async def test_project_repository_crud(db_session):
    repo = ProjectRepository(db_session)
    user_id = uuid.uuid4()
    
    project = await repo.create_project(user_id, "Test Project", "test-project")
    assert project.id is not None
    assert project.name == "Test Project"
    
    fetched = await repo.get_project(project.id)
    assert fetched is not None
    assert fetched.id == project.id
    
    projects = await repo.get_user_projects(user_id)
    assert len(projects) == 1
    
    archived = await repo.archive_project(project.id)
    assert archived is not None
    assert archived.archived_at is not None
    
    projects_after_archive = await repo.get_user_projects(user_id)
    assert len(projects_after_archive) == 0

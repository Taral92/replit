import pytest
import uuid
from packages.db.repositories.workspaces import WorkspaceRepository

@pytest.mark.asyncio
async def test_workspace_repository_crud(db_session):
    repo = WorkspaceRepository(db_session)
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    workspace = await repo.create_workspace(project_id, user_id, "provisioning")
    assert workspace.id is not None
    assert workspace.status == "provisioning"
    
    fetched = await repo.get_workspace(workspace.id)
    assert fetched is not None
    assert fetched.id == workspace.id
    
    updated = await repo.update_workspace_status(workspace.id, "running", "container_123")
    assert updated is not None
    assert updated.status == "running"
    assert updated.container_id == "container_123"
    
    workspaces = await repo.get_user_workspaces(user_id)
    assert len(workspaces) == 1
    assert workspaces[0].status == "running"
    
    # Capture the value, not the attribute. The session uses
    # expire_on_commit=False, so `workspace` and any later get() return the
    # SAME identity-mapped object — comparing workspace.last_active_at after
    # the update would compare the new value against itself.
    # Read both out as plain values first. expire_all() below invalidates every
    # attribute on the instance, and touching one afterwards triggers a lazy
    # reload — which raises MissingGreenlet under async.
    workspace_id = workspace.id
    before = workspace.last_active_at

    await repo.update_last_active(workspace_id)

    # update() issues raw SQL and does not touch the identity map, so the
    # cached instance must be expired to force a re-read from the database.
    db_session.expire_all()

    fetched_again = await repo.get_workspace(workspace_id)
    assert fetched_again.last_active_at > before

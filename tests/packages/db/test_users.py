import pytest
from packages.db.repositories.users import UserRepository

@pytest.mark.asyncio
async def test_user_repository_crud(db_session):
    repo = UserRepository(db_session)
    
    # Create
    user = await repo.create_user("test@example.com", "hash123", "Test User")
    assert user.id is not None
    assert user.email == "test@example.com"
    
    # Read
    fetched = await repo.get_user_by_email("test@example.com")
    assert fetched is not None
    assert fetched.id == user.id
    
    fetched_by_id = await repo.get_user_by_id(user.id)
    assert fetched_by_id is not None
    assert fetched_by_id.email == "test@example.com"
    
    # Update
    updated = await repo.update_user_status(user.id, "suspended")
    assert updated is not None
    assert updated.status == "suspended"
    
    # Api Keys
    key = await repo.add_api_key(user.id, "openai", "enc_key", "sk-1")
    assert key.id is not None
    
    keys = await repo.get_api_keys(user.id)
    assert len(keys) == 1
    assert keys[0].provider == "openai"

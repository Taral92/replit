import pytest
import uuid
from packages.db.repositories.usage import UsageRepository

@pytest.mark.asyncio
async def test_usage_repository_crud(db_session):
    repo = UsageRepository(db_session)
    user_id = uuid.uuid4()
    
    # Record usage
    record = await repo.record_usage(
        user_id=user_id,
        provider="openai",
        model="gpt-4o",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.015
    )
    assert record.id is not None
    assert record.input_tokens == 100
    
    # Budget
    budget = await repo.set_budget(user_id, 20.0)
    assert budget.user_id == user_id
    assert budget.monthly_limit_usd == 20.0
    
    fetched = await repo.get_budget(user_id)
    assert fetched is not None
    assert fetched.monthly_limit_usd == 20.0
    
    # Update budget
    updated = await repo.set_budget(user_id, 50.0)
    assert updated.monthly_limit_usd == 50.0

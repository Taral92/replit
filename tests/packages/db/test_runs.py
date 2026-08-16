import pytest
import uuid
import asyncio
from packages.db.repositories.runs import RunRepository

@pytest.mark.asyncio
async def test_run_repository_crud(db_session):
    repo = RunRepository(db_session)
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    run = await repo.create_run(workspace_id, user_id, "test prompt", "gpt-4o")
    assert run.id is not None
    assert run.status == "queued"
    
    fetched = await repo.get_run(run.id)
    assert fetched is not None
    assert fetched.id == run.id
    
    updated = await repo.update_run_status(run.id, "running")
    assert updated.status == "running"
    
    tool = await repo.record_tool_call(run.id, 1, "test_tool", {"arg": "value"}, "started", "low")
    assert tool.id is not None
    
    updated_tool = await repo.update_tool_result(tool.id, "success", result_inline="result")
    assert updated_tool.status == "success"
    assert updated_tool.result_inline == "result"


@pytest.mark.asyncio
async def test_run_events_monotonic_seq_concurrent(db_session, db_engine):
    repo = RunRepository(db_session)
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    run = await repo.create_run(workspace_id, user_id, "test concurrent", "gpt-4o")

    # Each task needs its OWN session. A single AsyncSession cannot be used
    # concurrently, and sharing one would serialise the writes — which would
    # make this test pass without ever exercising the row lock in
    # append_event(). Sessions come from the test engine so they share the
    # running event loop.
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def worker():
        async with factory() as session:
            worker_repo = RunRepository(session)
            await worker_repo.append_event(run.id, "test_event", {"data": "test"})
            
    tasks = [asyncio.create_task(worker()) for _ in range(10)]
    await asyncio.gather(*tasks)
    
    # Now verify with the main session
    events = await repo.get_events_after(run.id, 0)
    assert len(events) == 10
    
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, 11)), "Sequences must be contiguous starting from 1"

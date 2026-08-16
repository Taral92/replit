import uuid
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
from sqlalchemy import select, update, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from packages.db.models.run import AgentRun, RunEvent, ToolCall

class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, workspace_id: uuid.UUID, user_id: uuid.UUID, prompt: str, model: str) -> AgentRun:
        run = AgentRun(
            workspace_id=workspace_id,
            user_id=user_id,
            prompt=prompt,
            model=model,
            status="queued"
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: uuid.UUID) -> Optional[AgentRun]:
        return await self.session.get(AgentRun, run_id)

    async def update_run_status(self, run_id: uuid.UUID, status: str, error: Optional[str] = None) -> Optional[AgentRun]:
        values = {"status": status}
        if error:
            values["error"] = error
        if status in ("completed", "failed", "cancelled"):
            values["ended_at"] = datetime.now(timezone.utc)
            
        stmt = update(AgentRun).where(AgentRun.id == run_id).values(**values).returning(AgentRun)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def append_event(self, run_id: uuid.UUID, event_type: str, payload: Dict[str, Any]) -> RunEvent:
        """
        Appends a run event with a monotonic sequence number allocated inside the transaction.
        """
        async with self.session.begin_nested():
            # Get max seq for the run with row lock (FOR UPDATE is handled automatically if we do a subquery or we can explicitly lock, but max() over indexed column under repeatable read or serializable is okay. To be safe against race conditions under read committed, we should lock the run row or use a subquery).
            # We lock the AgentRun row to ensure monotonic sequence without gaps.
            stmt = select(AgentRun).where(AgentRun.id == run_id).with_for_update()
            run = (await self.session.execute(stmt)).scalar_one_or_none()
            if not run:
                raise ValueError("Run not found")
                
            # Get max seq
            max_seq_stmt = select(func.max(RunEvent.seq)).where(RunEvent.run_id == run_id)
            current_max = (await self.session.execute(max_seq_stmt)).scalar()
            next_seq = 1 if current_max is None else current_max + 1
            
            event = RunEvent(run_id=run_id, seq=next_seq, type=event_type, payload=payload)
            self.session.add(event)
        
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def get_events_after(self, run_id: uuid.UUID, after_seq: int) -> List[RunEvent]:
        stmt = select(RunEvent).where(
            RunEvent.run_id == run_id,
            RunEvent.seq > after_seq
        ).order_by(RunEvent.seq)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_tool_call(self, run_id: uuid.UUID, seq: int, tool_name: str, arguments: Dict[str, Any], status: str, risk_level: str) -> ToolCall:
        tool_call = ToolCall(
            run_id=run_id,
            seq=seq,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            risk_level=risk_level
        )
        self.session.add(tool_call)
        await self.session.commit()
        await self.session.refresh(tool_call)
        return tool_call

    async def update_tool_result(self, tool_call_id: uuid.UUID, status: str, result_inline: Optional[str] = None, result_ref: Optional[str] = None) -> Optional[ToolCall]:
        stmt = update(ToolCall).where(ToolCall.id == tool_call_id).values(
            status=status,
            result_inline=result_inline,
            result_ref=result_ref
        ).returning(ToolCall)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

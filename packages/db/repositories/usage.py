import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models.usage import UsageRecord, Budget

class UsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_usage(
        self, user_id: uuid.UUID, provider: str, model: str, 
        input_tokens: int, output_tokens: int, cost_usd: float,
        workspace_id: Optional[uuid.UUID] = None, run_id: Optional[uuid.UUID] = None
    ) -> UsageRecord:
        record = UsageRecord(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_budget(self, user_id: uuid.UUID) -> Optional[Budget]:
        return await self.session.get(Budget, user_id)

    async def set_budget(self, user_id: uuid.UUID, monthly_limit_usd: float) -> Budget:
        budget = await self.session.get(Budget, user_id)
        if budget:
            budget.monthly_limit_usd = monthly_limit_usd
        else:
            budget = Budget(
                user_id=user_id, 
                monthly_limit_usd=monthly_limit_usd,
                current_period_start=datetime.now(timezone.utc)
            )
            self.session.add(budget)
        await self.session.commit()
        await self.session.refresh(budget)
        return budget

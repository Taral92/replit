import uuid
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models.user import User, ApiKey

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, email: str, password_hash: str, name: Optional[str] = None) -> User:
        user = User(email=email, password_hash=password_hash, name=name)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def update_user_status(self, user_id: uuid.UUID, status: str) -> Optional[User]:
        stmt = update(User).where(User.id == user_id).values(status=status).returning(User)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def add_api_key(self, user_id: uuid.UUID, provider: str, encrypted_key: str, key_hint: str) -> ApiKey:
        key = ApiKey(user_id=user_id, provider=provider, encrypted_key=encrypted_key, key_hint=key_hint)
        self.session.add(key)
        await self.session.commit()
        await self.session.refresh(key)
        return key

    async def get_api_keys(self, user_id: uuid.UUID) -> List[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

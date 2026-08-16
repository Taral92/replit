import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Use DATABASE_URL from environment; if not set, fallback to settings default but we should try to avoid importing it if it causes circular deps.
# Actually, it's fine to import settings if we need it.
from packages.config.settings import settings

db_url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)

engine = create_async_engine(db_url, echo=False)
async_session_maker = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

async def get_db_session():
    async with async_session_maker() as session:
        yield session

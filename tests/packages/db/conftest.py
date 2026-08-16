"""
Test fixtures for the database layer.

Two deliberate choices here:

1. The schema is created by running `alembic upgrade head` in a subprocess,
   not by Base.metadata.create_all(). create_all() builds tables from the
   models and never exercises the migration, so a migration that has drifted
   from the models would pass every test and fail on first deploy. This tests
   the artifact we actually ship.

2. The engine is FUNCTION scoped. pytest-asyncio runs each test in its own
   event loop; a session-scoped async engine binds its connection pool to the
   loop that created it, producing "attached to a different loop" and
   "another operation is in progress" on every subsequent test.

Requires a real PostgreSQL. There is no SQLite fallback — the schema uses
JSONB and timestamptz, which SQLite does not implement faithfully, so a
SQLite pass would prove nothing.
"""
import os
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.db.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/runner_ide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _postgres_reachable() -> bool:
    import socket

    try:
        with socket.create_connection(("localhost", 5432), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Build the schema from the Alembic migration, once per test session."""
    if not _postgres_reachable():
        pytest.skip(
            "PostgreSQL is not reachable on localhost:5432. "
            "Start it with `brew services start postgresql@15`."
        )

    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}

    # Reset to a clean slate, then migrate up. downgrade may no-op on a fresh
    # database, which is fine.
    subprocess.run(
        ["alembic", "downgrade", "base"],
        cwd=PROJECT_ROOT, env=env, capture_output=True,
    )
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    yield


@pytest_asyncio.fixture
async def db_engine():
    """Function-scoped engine — see the module docstring for why."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """A clean session against a truncated schema."""
    # Truncate rather than drop/create: the schema comes from the migration and
    # should not be rebuilt per test. CASCADE handles FK ordering for us.
    table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

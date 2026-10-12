"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

# SQLite (local dev / tests) needs a generous busy timeout for concurrent writes.
_CONNECT_ARGS: dict = {}
if settings.async_database_url.startswith("sqlite"):
    _CONNECT_ARGS = {"timeout": 30}

engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
    connect_args=_CONNECT_ARGS,
)

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Resolve the session factory at call time (allows test overrides)."""
    return SessionFactory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionFactory() as session:
        yield session

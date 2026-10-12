"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

# SQLite (local dev / tests) is a single-writer database: many pooled
# connections busy-waiting on each other's write locks can exhaust the pool.
# A single serialized connection + WAL avoids SQLITE_BUSY storms entirely.
# In-memory SQLite (tests) auto-selects StaticPool, which takes no pool args.
_url = make_url(settings.async_database_url)
_IS_SQLITE = _url.get_backend_name() == "sqlite"
_IS_SQLITE_FILE = _IS_SQLITE and bool(_url.database) and _url.database != ":memory:"
_ENGINE_KWARGS: dict = {"pool_pre_ping": True}
_CONNECT_ARGS: dict = {}
if _IS_SQLITE_FILE:
    _CONNECT_ARGS = {"timeout": 30}
    _ENGINE_KWARGS.update({"pool_size": 1, "max_overflow": 0})
if _IS_SQLITE:
    _ENGINE_KWARGS["connect_args"] = _CONNECT_ARGS

engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    **_ENGINE_KWARGS,
)

if _IS_SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragma(dbapi_connection, _record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

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

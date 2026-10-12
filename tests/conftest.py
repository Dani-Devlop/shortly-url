"""Shared pytest fixtures.

Test stack: async SQLite (file-backed per test) + fakeredis for the rate limiter.
The app is exercised through httpx's ASGITransport, so background click tasks
run to completion before a request returns.
"""

import os

# Hard-override ambient env (CI/sandbox) BEFORE app modules are imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = ""
os.environ["MASTER_API_KEY"] = "test-master-key"
os.environ["IP_HASH_SALT"] = "test-salt"
os.environ["BASE_URL"] = "http://testserver"
os.environ["AUTO_CREATE_TABLES"] = "false"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fakeredis import FakeAsyncRedis  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.core.redis as redis_module  # noqa: E402
import app.db.session as session_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

API_KEY = os.environ["MASTER_API_KEY"]
AUTH_HEADERS = {"X-API-Key": API_KEY}
SECOND_API_KEY = "second-user-key"


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    """Fresh SQLite database per test, with FK enforcement enabled."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db",
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine, monkeypatch):
    """HTTP client bound to the app, with DB overrides and a seeded master user."""
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionFactory", factory)

    from app.db.session import get_db

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with factory() as session:
        session.add(User(api_key=API_KEY))
        session.add(User(api_key=SECOND_API_KEY))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def fake_redis(monkeypatch):
    """Inject a fakeredis client so the rate limiter & counters are exercisable."""
    fake = FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_client", fake)
    return fake

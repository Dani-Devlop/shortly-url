"""Config DSN normalisation (sync_database_url used by Alembic)."""

from app.core.config import Settings


def test_sync_database_url_strips_async_sqlite_driver():
    settings = Settings(database_url="sqlite+aiosqlite:////tmp/x.db", _env_file=None)
    assert settings.sync_database_url == "sqlite:////tmp/x.db"


def test_sync_database_url_swaps_asyncpg_for_psycopg2():
    settings = Settings(database_url="postgresql://u:p@host/db", _env_file=None)
    assert settings.sync_database_url == "postgresql+psycopg2://u:p@host/db"
    assert settings.async_database_url.startswith("postgresql+asyncpg://")

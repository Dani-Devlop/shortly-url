"""Central application settings (12-factor, env-driven)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    project_name: str = "shortly-url"
    environment: str = "development"  # development | test | production
    base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # --- Storage ---
    database_url: str = "postgresql+asyncpg://shortly:shortly@localhost:5432/shortly"
    redis_url: str = "redis://localhost:6379/0"

    # --- Security ---
    master_api_key: str = "change-me-master-key"
    ip_hash_salt: str = "change-me-ip-salt"

    # --- Behaviour ---
    code_length: int = 7
    cache_ttl_seconds: int = 3600
    counter_ttl_seconds: int = 7 * 24 * 3600
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60
    auto_create_tables: bool = False

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def async_database_url(self) -> str:
        """DSN normalised for SQLAlchemy async drivers."""
        return self._normalize_postgres_scheme(self.database_url)

    @property
    def sync_database_url(self) -> str:
        """DSN normalised for sync tooling (Alembic)."""
        url = self.async_database_url.replace("+asyncpg", "+psycopg2")
        return url.replace("+aiosqlite", "")  # pysqlite is the sync sqlite driver

    @staticmethod
    def _normalize_postgres_scheme(url: str) -> str:
        """Upgrade plain postgres DSNs (e.g. from Render) to the asyncpg driver."""
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()

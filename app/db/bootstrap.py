"""Startup bootstrap: optional table creation and the master API user."""

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.models import User

logger = logging.getLogger(__name__)
settings = get_settings()


async def create_all_tables() -> None:
    """Dev/demo convenience — production uses Alembic migrations."""
    import app.models  # noqa: F401
    from app.db.base import Base
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("created tables from ORM metadata")


async def ensure_master_user() -> None:
    """Ensure the bootstrap ``master`` user exists (idempotent, DB-outage safe)."""
    if settings.auto_create_tables:
        try:
            await create_all_tables()
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_create_tables failed: %s", exc)
    try:
        from app.db.session import get_session_factory

        async with get_session_factory()() as session:
            existing = await session.scalar(
                select(User).where(User.api_key == settings.master_api_key)
            )
            if existing is None:
                session.add(User(api_key=settings.master_api_key))
                await session.commit()
                logger.info("created master API user")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not ensure master user (database unavailable?): %s", exc)

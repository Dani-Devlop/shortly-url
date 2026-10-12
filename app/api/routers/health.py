"""Health/readiness probe with graceful degradation reporting."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_db

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False

    redis = get_redis()
    redis_ok: bool | None = None  # None = disabled
    if redis is not None:
        try:
            await redis.ping()
            redis_ok = True
        except Exception:  # noqa: BLE001
            redis_ok = False

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "redis": redis_ok,
        "version": "1.0.0",
        "environment": settings.environment,
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=payload)

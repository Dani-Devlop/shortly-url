"""Reusable FastAPI dependencies (auth)."""

from fastapi import Depends, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.db.session import get_db
from app.models import User

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    api_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the caller from the ``X-API-Key`` header."""
    if not api_key:
        raise AuthenticationError("Missing API key — provide it via the X-API-Key header")
    user = await db.scalar(select(User).where(User.api_key == api_key))
    if user is None:
        raise AuthenticationError("Invalid API key")
    return user

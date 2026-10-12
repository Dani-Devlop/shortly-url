"""Click recording — runs in a Starlette BackgroundTask after the redirect response.

The recorder opens its *own* short-lived session (resolved at call time), so it
never depends on the request-scoped session lifecycle.
"""

import logging

from starlette.background import BackgroundTask

from app.core.redis import incr_counter
from app.core.security import hash_ip
from app.core.user_agent import classify_user_agent
from app.db.session import get_session_factory
from app.models import Click

logger = logging.getLogger(__name__)


async def record_click(
    link_id: int,
    code: str,
    ip: str | None,
    user_agent: str | None,
    referrer: str | None = None,
) -> None:
    try:
        async with get_session_factory()() as session:
            session.add(
                Click(
                    link_id=link_id,
                    ip_hash=hash_ip(ip),
                    user_agent=user_agent[:512] if user_agent else None,
                    referrer=referrer[:512] if referrer else None,
                    device=classify_user_agent(user_agent),
                )
            )
            await session.commit()
        await incr_counter(f"shortly:clicks:{code}")
    except Exception:  # noqa: BLE001
        logger.exception("failed to record click for code=%s", code)


def click_task(
    link_id: int,
    code: str,
    ip: str | None,
    user_agent: str | None,
    referrer: str | None = None,
) -> BackgroundTask:
    return BackgroundTask(
        record_click,
        link_id=link_id,
        code=code,
        ip=ip,
        user_agent=user_agent,
        referrer=referrer,
    )

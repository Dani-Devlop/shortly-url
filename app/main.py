"""Application entrypoint.

Kept intentionally thin: the FastAPI app is assembled in ``create_app``.
Routers, middleware and exception handlers are added milestone by milestone.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="shortly-url",
    description="Fast link shortener with click analytics.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness probe (expanded to a DB/Redis readiness probe in later milestones)."""
    return {"status": "ok", "service": "shortly-url"}

"""Application entrypoint — app factory, exception handlers, router wiring."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routers import health, links, pages, redirects, stats, tags
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.redis import close_redis, init_redis
from app.db.bootstrap import ensure_master_user

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("shortly")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_redis()
    await ensure_master_user()
    logger.info("%s started (env=%s)", settings.project_name, settings.environment)
    yield
    await close_redis()
    logger.info("%s shutting down", settings.project_name)


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def create_app() -> FastAPI:
    application = FastAPI(
        title="shortly-url",
        description="Fast link shortener with click analytics.",
        version=__version__,
        lifespan=lifespan,
    )

    # Order matters: the catch-all /{code} redirect route must be registered LAST.
    application.include_router(health.router)
    application.include_router(pages.router)
    application.include_router(links.router)
    application.include_router(stats.router)
    application.include_router(tags.router)
    application.include_router(redirects.router)

    @application.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {}
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        budget = getattr(exc, "budget", None)
        if budget is not None:
            headers.update(budget.headers())
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
            headers=headers,
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", str(exc.detail)),
            headers=getattr(exc, "headers", None) or {},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": ".".join(str(part) for part in err.get("loc", [])),
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        body = _error_body("validation_error", "Request validation failed")
        body["error"]["details"] = details
        return JSONResponse(status_code=422, content=body)

    @application.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "An unexpected error occurred"),
        )

    return application


app = create_app()

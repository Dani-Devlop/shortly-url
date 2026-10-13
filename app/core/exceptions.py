"""Domain exceptions with a uniform JSON error envelope."""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)


class ValidationError(AppError):
    """Semantic validation failure that pydantic cannot express (e.g. a
    query combination). Renders through the uniform error envelope."""

    status_code = 422
    code = "validation_error"

    def __init__(self, message: str = "Request validation failed") -> None:
        super().__init__(message)


class GoneError(AppError):
    status_code = 410
    code = "link_expired"

    def __init__(
        self,
        message: str = "This short link has expired",
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code)


class ConflictError(AppError):
    status_code = 409
    code = "conflict"

    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message)


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(
        self,
        message: str = "Too many requests",
        *,
        retry_after: int = 60,
        budget: object | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = max(1, retry_after)
        # Optional RateLimitBudget — the exception handler turns it into
        # X-RateLimit-* headers on the 429 response.
        self.budget = budget

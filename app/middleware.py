import json
import logging
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from app.config import Settings

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request id from the contextvar for logging."""

    return request_id_ctx_var.get()


class RequestIdFilter(logging.Filter):
    """Inject the request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Structured log formatter that renders records as JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt) if record.created else None,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_info"] = record.stack_info
        return json.dumps({k: v for k, v in log_record.items() if v is not None})


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a stable request id to the request scope and context var."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:  # type: ignore[override]
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming or str(uuid.uuid4())
        token = request_id_ctx_var.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            request_id_ctx_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a sanitized response when a client exceeds limits."""

    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Too many requests. Please slow down.",
        },
        headers=headers,
    )


def configure_middlewares(app: FastAPI, settings: Settings) -> Limiter:
    """Attach CORS, rate limiting, and request id middleware."""

    limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(RequestIdMiddleware)

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    return limiter
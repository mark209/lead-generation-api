"""
Run locally: uvicorn app.main:app --reload
Production: gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app
Example:
curl -X POST http://localhost:8000/lead \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Jane","last_name":"Doe","phone":"+15551234567","email":"jane@example.com","state":"CA","postal":"90210"}'
"""

import logging
import logging.config
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.google_sheets import append_lead_to_sheet
from app.middleware import configure_middlewares, get_request_id
from app.models import ErrorResponse, Lead, LeadResponse
from app.services import forward_to_crm

settings = get_settings()


def configure_logging() -> None:
    """Configure application-wide structured logging."""

    level = settings.log_level.upper()
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "app.middleware.RequestIdFilter"},
        },
        "formatters": {
            "json": {
                "()": "app.middleware.JsonFormatter",
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": level, "propagate": False},
        },
    }
    logging.config.dictConfig(logging_config)


configure_logging()

openapi_tags = [
    {"name": "health", "description": "Service uptime checks."},
    {"name": "lead", "description": "Lead intake endpoints."},
]

app = FastAPI(
    title="Lead Generation API",
    description="Accept and process inbound lead submissions.",
    version="1.0.0",
    openapi_tags=openapi_tags,
)

limiter = configure_middlewares(app, settings)
logger = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a standardized validation error response."""

    errors = exc.errors()
    message = errors[0]["msg"] if errors else "Validation error"
    logger.warning("Validation failed", extra={"errors": errors})
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(message=message, details=errors).model_dump(exclude_none=True),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle controlled HTTP errors with sanitized payloads."""

    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    logger.warning(
        "HTTP exception raised",
        extra={"status_code": exc.status_code, "detail": detail},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler to avoid leaking internal details."""

    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Server error"},
    )


@app.get("/health", tags=["health"], response_model=dict)
async def health_check() -> dict[str, str]:
    """Return service health information."""

    return {"status": "success", "message": "OK"}


@app.post("/lead", tags=["lead"], response_model=LeadResponse, status_code=201)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def create_lead(lead: Lead, request: Request) -> LeadResponse:
    """Accept a lead payload, validate, and forward to the CRM layer."""

    client_host = request.client.host if request.client else "unknown"
    source_hint = (
        str(lead.source_url)
        if lead.source_url
        else request.headers.get("X-Source-Url")
        or request.headers.get("Referer")
        or request.headers.get("Origin")
    )
    logger.info(
        "Lead accepted",
        extra={
            "lead_email": lead.email,
            "client_ip": client_host,
            "source_url": source_hint,
        },
    )
    try:
        await forward_to_crm(lead)
        await append_lead_to_sheet(lead, source_hint)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed processing downstream integrations")
        raise HTTPException(status_code=502, detail="Failed to process lead") from exc
    return LeadResponse(message="Lead accepted", data=lead)


@app.middleware("http")
async def append_request_id_header(request: Request, call_next: Any):
    """Ensure every response includes the request id even after other middlewares."""

    response = await call_next(request)
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    if request_id:
        response.headers.setdefault("X-Request-ID", request_id)
    return response
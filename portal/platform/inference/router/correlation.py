"""Per-request correlation id: contextvar + ASGI middleware + logging filter.

One id is minted (or accepted from an inbound ``X-Correlation-ID`` /
``X-Request-ID`` header) per HTTP request, stored in a ``ContextVar`` so every log
line and downstream helper in that request sees the same value, and echoed back in
the response header. The streaming path sources its ``request_id`` from here, so the
id already forwarded into ``tool_registry.dispatch`` and the MCP POST body now
matches the id on every surrounding log line. Never raises.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

_HEADER = "X-Correlation-ID"
_ALT_HEADER = "X-Request-ID"


def new_correlation_id() -> str:
    return f"p5-{uuid.uuid4().hex[:12]}"


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid or "")


def get_correlation_id() -> str:
    return _correlation_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        cid = (
            request.headers.get(_HEADER) or request.headers.get(_ALT_HEADER) or new_correlation_id()
        )
        token = _correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            _correlation_id.reset(token)
        with contextlib.suppress(Exception):
            response.headers[_HEADER] = cid
        return response


class CorrelationIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


def install_log_filter() -> None:
    """Attach the filter to the root logger's handlers (best-effort, idempotent)."""
    flt = CorrelationIdLogFilter()
    root = logging.getLogger()
    for h in root.handlers:
        if not any(isinstance(f, CorrelationIdLogFilter) for f in h.filters):
            h.addFilter(flt)

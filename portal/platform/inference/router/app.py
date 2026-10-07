"""FastAPI app wiring — instantiates the app and binds route handlers."""

from __future__ import annotations

import importlib.metadata
import logging
import os

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from portal.platform.inference.router import handlers, ollama_passthrough
from portal.platform.inference.router.lifespan import lifespan
from portal.platform.inference.router.request_limits import (
    MAX_REQUEST_BYTES,
    RequestBodyLimitMiddleware,
)

logger = logging.getLogger(__name__)

try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"

app = FastAPI(title="Portal Pipeline", version=_PKG_VERSION, lifespan=lifespan)

# Per-request correlation id: mint/accept at entry, bind to a contextvar for
# uniform log stamping, echo back in the response header. See router.correlation.
from portal.platform.inference.router.correlation import (  # noqa: E402
    CorrelationIdMiddleware,
    install_log_filter,
)

# Middleware is applied in reverse registration order. Keep correlation outermost
# so even a body-limit rejection receives the request correlation header.
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)
app.add_middleware(CorrelationIdMiddleware)
# uvicorn's spawned workers do not inherit __main__'s basicConfig. With no root
# handler, every portal.* INFO line from a worker was dropped (only WARNING+
# reached the last-resort handler), which hid routing, health and cancel logs.
if not logging.getLogger().handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
install_log_filter()

app.get("/health")(handlers.health)
app.get("/health/all")(handlers.health_all)
app.post("/admin/refresh-tools")(handlers.admin_refresh_tools)
app.post("/admin/load-plan")(handlers.admin_load_plan)
app.post("/ollama/api/chat")(ollama_passthrough.chat)
app.post("/ollama/api/generate")(ollama_passthrough.generate)
app.post("/ollama/api/embed")(ollama_passthrough.embed)
app.get("/ollama/api/ps")(ollama_passthrough.ps)
app.get("/ollama/api/tags")(ollama_passthrough.tags)
app.post("/ollama/api/show")(ollama_passthrough.show)
app.post("/notifications/test")(handlers.test_notifications)
app.get("/metrics", response_class=PlainTextResponse)(handlers.metrics)
app.get("/v1/models")(handlers.list_models)
app.get("/v1/backends")(handlers.list_backends_endpoint)
app.post("/v1/chat/completions")(handlers.chat_completions)
app.post("/v1/messages")(handlers.anthropic_messages)
app.get("/v1/trace")(handlers.list_traces)
app.get("/v1/trace/{correlation_id}")(handlers.get_trace)

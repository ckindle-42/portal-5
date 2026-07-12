"""FastAPI app wiring — instantiates the app and binds route handlers."""

from __future__ import annotations

import importlib.metadata
import logging

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from portal.platform.inference.router import handlers
from portal.platform.inference.router.lifespan import lifespan

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

app.add_middleware(CorrelationIdMiddleware)
install_log_filter()

app.get("/health")(handlers.health)
app.get("/health/all")(handlers.health_all)
app.post("/admin/refresh-tools")(handlers.admin_refresh_tools)
app.post("/notifications/test")(handlers.test_notifications)
app.get("/metrics", response_class=PlainTextResponse)(handlers.metrics)
app.get("/v1/models")(handlers.list_models)
app.get("/v1/backends")(handlers.list_backends_endpoint)
app.post("/v1/chat/completions")(handlers.chat_completions)
app.post("/v1/messages")(handlers.anthropic_messages)

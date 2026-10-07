"""Cancel non-streaming backend work when the client disconnects (W3.1).

Uvicorn does not cancel a handler whose client has gone, so a non-streaming
request otherwise runs to completion (and may retry after
``model_still_running``) for nobody. This runs the handling as a task, polls
``request.is_disconnected()``, and cancels the task on disconnect. Cancelling
aborts the in-flight httpx request, which closes the engine connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Coroutine
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from portal.platform.inference.router.metrics import _client_disconnect_cancel_total

logger = logging.getLogger(__name__)

#: Disconnect poll cadence (seconds); the task contract asks for <= 1 s.
POLL_S = 0.5

#: Status recorded for a request whose client left (nginx's convention).
CLIENT_CLOSED = 499


async def cancel_on_disconnect(request: Request, work: Coroutine[Any, Any, Any], path: str) -> Any:
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=POLL_S)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                _client_disconnect_cancel_total.labels(path=path).inc()
                logger.info("client disconnected; cancelled non-streaming work path=%s", path)
                return Response(status_code=CLIENT_CLOSED)
    finally:
        if not task.done():
            task.cancel()

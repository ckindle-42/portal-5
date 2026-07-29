"""ASGI request-body limits that also cover streamed/chunked uploads."""

from __future__ import annotations

import os

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(4 * 1024 * 1024)))
LIMITED_PATHS = frozenset({"/v1/chat/completions", "/v1/messages"})


class RequestBodyLimitMiddleware:
    """Buffer and bound JSON request bodies before a route can consume them.

    A ``Content-Length`` check alone is bypassed by HTTP chunked transfer.  The
    two inference endpoints already parse the entire JSON body, so bounded
    buffering here does not change their memory model; it makes the bound real.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int = MAX_REQUEST_BYTES,
        paths: frozenset[str] = LIMITED_PATHS,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.paths = paths

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        detail = f"Request body too large (max {self.max_bytes // 1024 // 1024}MB)"
        await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_length = headers.get(b"content-length", b"")
        try:
            content_length = int(raw_length) if raw_length else 0
        except ValueError:
            content_length = 0
        if content_length > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

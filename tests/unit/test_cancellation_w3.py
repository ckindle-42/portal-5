"""HOST_MEMORY_SAFETY W3: a client that gives up stops the work it started."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from typing import Any

import pytest
from starlette.requests import Request

from portal.modules.compliance.core import cancellation, council
from portal.modules.compliance.tools import compliance_mcp
from portal.platform.inference import streaming_client
from portal.platform.inference.router import disconnect
from portal.platform.inference.router.metrics import _client_disconnect_cancel_total


def _request(messages: list[dict[str, Any]], path: str = "/tools/x") -> Request:
    """A Starlette request whose receive() replays ``messages`` then disconnects."""
    queue = list(messages)

    async def receive() -> dict[str, Any]:
        # Like uvicorn: once the client has gone, receive() answers at once.
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": path, "headers": [], "query_string": b""}
    return Request(scope, receive)


# ── stream_chat_turn ─────────────────────────────────────────────────────────


def _hanging_server(first_line: bytes, release: threading.Event) -> tuple[int, threading.Thread]:
    """One-shot HTTP server: sends headers + one chunk, then blocks (a model
    in prefill) until ``release`` is set or the client goes away."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve() -> None:
        conn, _ = server.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n")
        conn.sendall(b"Transfer-Encoding: chunked\r\n\r\n")
        conn.sendall(b"%x\r\n%s\r\n" % (len(first_line), first_line))
        release.wait(10)
        conn.close()
        server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return port, thread


def test_stream_cancel_wakes_a_read_blocked_in_prefill():
    release = threading.Event()
    port, thread = _hanging_server(b": warming\n", release)
    started = time.monotonic()
    flag = threading.Event()
    threading.Timer(0.3, flag.set).start()

    with pytest.raises(streaming_client.StreamTurnCancelledError):
        streaming_client.stream_chat_turn(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            {},
            {"model": "m", "messages": []},
            is_pipeline_mode=True,
            idle_timeout_s=30,
            should_cancel=flag.is_set,
        )
    # Cancelled well inside the 30 s idle timeout: the watcher shut the socket.
    assert time.monotonic() - started < 3
    release.set()
    thread.join(5)


def test_stream_cancelled_before_send_raises_without_a_request():
    with pytest.raises(streaming_client.StreamTurnCancelledError):
        streaming_client.stream_chat_turn(
            "http://127.0.0.1:9/never",
            {},
            {},
            is_pipeline_mode=True,
            idle_timeout_s=1,
            should_cancel=lambda: True,
        )


# ── compliance council and transport ─────────────────────────────────────────


def test_council_stops_between_seats_once_cancelled():
    token = cancellation.CancelToken()
    asked: list[str] = []

    def seat_fn(model: str, system: str, user: str) -> str:
        asked.append(model)
        token.cancel()
        return json.dumps({"determination": "SUPPORTED"})

    seats = [{"id": f"s{i}", "label": f"s{i}", "model": f"m{i}"} for i in range(3)]
    packet = {"governing_unit": {"ref": "CIP-007-6 R2"}}

    def run() -> None:
        cancellation.bind(token)
        council.run_council(packet, seats, seat_fn=seat_fn)

    import contextvars

    with pytest.raises(cancellation.TurnCancelled):
        contextvars.copy_context().run(run)
    assert len(asked) == 1


def test_cancelled_turn_is_not_swallowed_as_a_seat_error():
    # A BaseException passes the seat loop's `except Exception` (non-vote) path.
    assert not issubclass(cancellation.TurnCancelled, Exception)


def test_reading_post_checks_the_token_before_each_call():
    import contextvars

    from portal.modules.compliance.core import reading_transport

    token = cancellation.CancelToken()
    token.cancel()

    def run() -> None:
        cancellation.bind(token)
        reading_transport._post({}, 1, dialect=object())

    with pytest.raises(cancellation.TurnCancelled):
        contextvars.copy_context().run(run)


# ── compliance invoke_tool ───────────────────────────────────────────────────


def test_invoke_tool_cancels_on_disconnect_and_records_cancelled(monkeypatch):
    stopped = threading.Event()

    def slow_tool() -> dict[str, Any]:
        for _ in range(200):  # ~10 s unless cancelled
            cancellation.check()
            time.sleep(0.05)
        return {"verdict": "partial"}  # pragma: no cover - must not be reached

    def tool() -> dict[str, Any]:
        try:
            return slow_tool()
        finally:
            stopped.set()

    monkeypatch.setitem(compliance_mcp._DISPATCH, "slow", tool)
    monkeypatch.setattr(compliance_mcp, "_DISCONNECT_POLL_S", 0.05)
    request = _request([{"type": "http.request", "body": b"{}", "more_body": False}])
    request.scope["path_params"] = {"tool_name": "slow"}

    started = time.monotonic()
    response = asyncio.run(compliance_mcp.invoke_tool(request))

    assert response.status_code == 499
    body = json.loads(response.body)
    assert body["receipt"]["status"] == "cancelled"
    assert "verdict" not in body
    assert stopped.is_set()
    assert time.monotonic() - started < 3


# ── pipeline non-streaming ───────────────────────────────────────────────────


def test_pipeline_cancels_non_streaming_work_on_disconnect(monkeypatch):
    monkeypatch.setattr(disconnect, "POLL_S", 0.05)
    cancelled = asyncio.Event()
    before = _client_disconnect_cancel_total.labels(path="test")._value.get()

    async def backend_call() -> str:
        try:
            await asyncio.sleep(30)
            return "late"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def run() -> Any:
        request = _request([{"type": "http.request", "body": b"{}", "more_body": False}])
        await request.body()
        return await disconnect.cancel_on_disconnect(request, backend_call(), "test")

    response = asyncio.run(run())

    assert response.status_code == disconnect.CLIENT_CLOSED
    assert cancelled.is_set()
    assert _client_disconnect_cancel_total.labels(path="test")._value.get() == before + 1


def test_pipeline_returns_the_result_when_the_client_stays(monkeypatch):
    monkeypatch.setattr(disconnect, "POLL_S", 0.05)

    async def run() -> Any:
        async def receive() -> dict[str, Any]:
            await asyncio.sleep(60)  # client still connected
            return {"type": "http.disconnect"}

        request = Request({"type": "http", "method": "POST", "headers": []}, receive)

        async def work() -> str:
            await asyncio.sleep(0.12)
            return "done"

        return await disconnect.cancel_on_disconnect(request, work(), "test")

    assert asyncio.run(run()) == "done"


def test_disconnect_is_seen_through_the_pipeline_middleware_stack(monkeypatch):
    """Raw ASGI client that disconnects mid-request, through the real
    correlation + body-limit middleware (BaseHTTPMiddleware hid the disconnect)."""
    from fastapi import FastAPI

    from portal.platform.inference.router.correlation import CorrelationIdMiddleware
    from portal.platform.inference.router.request_limits import RequestBodyLimitMiddleware

    monkeypatch.setattr(disconnect, "POLL_S", 0.05)
    cancelled = asyncio.Event()

    async def backend_call() -> str:
        try:
            await asyncio.sleep(30)
            return "late"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def endpoint(request: Request) -> Any:
        await request.body()
        return await disconnect.cancel_on_disconnect(request, backend_call(), "asgi")

    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=1024)
    app.add_middleware(CorrelationIdMiddleware)

    async def run() -> list[dict[str, Any]]:
        gone = asyncio.Event()
        sent: list[dict[str, Any]] = []
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b"{}", "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        }
        asyncio.get_running_loop().call_later(0.2, gone.set)
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        return sent

    sent = asyncio.run(run())
    assert cancelled.is_set()
    assert sent[0]["status"] == disconnect.CLIENT_CLOSED

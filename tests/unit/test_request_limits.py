"""Request body limits apply to declared and chunked inference bodies."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from portal.platform.inference.router.request_limits import RequestBodyLimitMiddleware


def _limited_app(max_bytes: int = 8) -> tuple[FastAPI, list[bytes]]:
    app = FastAPI()
    received: list[bytes] = []
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_bytes)

    @app.post("/v1/messages")
    async def messages(request: Request):
        body = await request.body()
        received.append(body)
        return {"size": len(body)}

    return app, received


@pytest.mark.asyncio
async def test_chunked_body_over_limit_is_rejected_before_handler():
    app, received = _limited_app()

    async def chunks():
        yield b"12345"
        yield b"67890"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/messages",
            content=chunks(),
            headers={"transfer-encoding": "chunked"},
        )

    assert response.status_code == 413
    assert received == []


@pytest.mark.asyncio
async def test_body_at_limit_is_replayed_to_handler():
    app, received = _limited_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/messages", content=b"12345678")

    assert response.status_code == 200
    assert response.json() == {"size": 8}
    assert received == [b"12345678"]

"""POST /v1/embeddings — the Pipeline's embeddings route.

Pins the request contract (model acceptance, batch/input bounds, dimensions), the
typed error mapping (never a 200 with empty vectors), and admission: the route's
semaphore is its own, so a batch neither takes a chat slot nor waits behind one.
"""

from __future__ import annotations

import json

import httpx
import pytest
import yaml
from fastapi import HTTPException
from starlette.requests import Request

from portal.platform.inference.router import embeddings as route
from portal.platform.inference.router.auth import PIPELINE_API_KEY

_AUTH = f"Bearer {PIPELINE_API_KEY}"
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _request(body: object) -> Request:
    payload = json.dumps(body).encode()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/embeddings",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive,
    )


@pytest.fixture
def embedder(tmp_path, monkeypatch) -> str:
    """A backends config with a platform_embedder block, installed as the route's source."""
    path = tmp_path / "backends.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "platform_embedder": {
                    "model": "test/embedder",
                    "url": "http://embedder:9999",
                    "aliases": ["test/embedder-alias"],
                    "max_batch": 3,
                    "max_input_chars": 12,
                    "max_concurrent": 2,
                    "timeout_s": 5,
                }
            }
        )
    )
    monkeypatch.setattr(route, "DEFAULT_CONFIG_PATH", str(path))
    monkeypatch.setattr(route, "_SEMAPHORE", None)
    monkeypatch.setattr(route, "_SEMAPHORE_LIMIT", 0)
    return str(path)


def _vectors(count: int, dim: int = 768) -> dict:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": [1.0 / dim] * dim}
            for i in range(count)
        ],
        "model": "test/embedder",
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


async def _answer(monkeypatch, data: dict | Exception) -> None:
    async def post(_config, _payload):
        if isinstance(data, Exception):
            raise data
        return data

    monkeypatch.setattr(route, "_post_upstream", post)


def test_the_route_is_registered() -> None:
    from portal.platform.inference.router_pipe import app

    routes = {(r.path, m) for r in app.routes if hasattr(r, "methods") for m in r.methods}
    assert ("/v1/embeddings", "POST") in routes


@pytest.mark.anyio
async def test_auth_is_the_same_as_chat(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), None)
    assert caught.value.status_code == 401


@pytest.mark.anyio
async def test_a_string_input_returns_one_vector(embedder, monkeypatch) -> None:
    await _answer(monkeypatch, _vectors(1))
    response = await route.embeddings(_request({"input": "a behaviour"}), _AUTH)
    body = json.loads(response.body)
    assert body["object"] == "list"
    assert body["model"] == "test/embedder"
    assert len(body["data"]) == 1
    assert len(body["data"][0]["embedding"]) == 768
    assert body["usage"] == {"prompt_tokens": 0, "total_tokens": 0}


@pytest.mark.anyio
async def test_an_unknown_model_names_what_is_accepted(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"model": "nope", "input": "x"}), _AUTH)
    assert caught.value.status_code == 400
    assert "test/embedder" in caught.value.detail
    assert "test/embedder-alias" in caught.value.detail


@pytest.mark.anyio
async def test_a_declared_alias_is_accepted(embedder, monkeypatch) -> None:
    await _answer(monkeypatch, _vectors(1))
    response = await route.embeddings(
        _request({"model": "test/embedder-alias", "input": "x"}), _AUTH
    )
    assert json.loads(response.body)["model"] == "test/embedder-alias"


@pytest.mark.anyio
async def test_the_batch_limit_is_a_typed_error(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": ["a", "b", "c", "d"]}), _AUTH)
    assert caught.value.status_code == 413
    assert "at most 3" in caught.value.detail


@pytest.mark.anyio
async def test_a_too_long_input_is_a_typed_error(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x" * 13}), _AUTH)
    assert caught.value.status_code == 413
    assert "at most 12" in caught.value.detail


@pytest.mark.anyio
async def test_an_untrained_dimension_is_rejected(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x", "dimensions": 300}), _AUTH)
    assert caught.value.status_code == 400
    assert "768" in caught.value.detail


@pytest.mark.anyio
async def test_dimensions_are_forwarded_and_checked(embedder, monkeypatch) -> None:
    seen: dict = {}

    async def post(_config, payload):
        seen.update(payload)
        return _vectors(1, dim=256)

    monkeypatch.setattr(route, "_post_upstream", post)
    response = await route.embeddings(_request({"input": "x", "dimensions": 256}), _AUTH)
    assert seen["dimensions"] == 256
    assert len(json.loads(response.body)["data"][0]["embedding"]) == 256


@pytest.mark.anyio
async def test_a_short_vector_is_a_502_not_a_200(embedder, monkeypatch) -> None:
    await _answer(monkeypatch, _vectors(1, dim=256))
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x", "dimensions": 768}), _AUTH)
    assert caught.value.status_code == 502


@pytest.mark.anyio
async def test_a_missing_vector_is_a_502(embedder, monkeypatch) -> None:
    await _answer(monkeypatch, _vectors(2))
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "only one"}), _AUTH)
    assert caught.value.status_code == 502


@pytest.mark.anyio
async def test_an_empty_input_is_a_400(embedder) -> None:
    for body in ({"input": ""}, {"input": []}, {"input": [1, 2]}, {}):
        with pytest.raises(HTTPException) as caught:
            await route.embeddings(_request(body), _AUTH)
        assert caught.value.status_code == 400


@pytest.mark.anyio
async def test_base64_encoding_is_refused(embedder) -> None:
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x", "encoding_format": "base64"}), _AUTH)
    assert caught.value.status_code == 400


@pytest.mark.anyio
async def test_busy_admission_is_a_429_with_retry_after(embedder, monkeypatch) -> None:
    monkeypatch.setattr(route, "_SEMAPHORE_TIMEOUT", 0.001)
    semaphore = route._admission(route.load_embedder_config())
    await semaphore.acquire()
    await semaphore.acquire()
    try:
        with pytest.raises(HTTPException) as caught:
            await route.embeddings(_request({"input": "x"}), _AUTH)
    finally:
        semaphore.release()
        semaphore.release()
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "1"


def _with_transport(monkeypatch, handler) -> None:
    def factory(**_kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(route.httpx, "AsyncClient", factory)


@pytest.mark.anyio
async def test_upstream_timeout_is_a_504(embedder, monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=_request)

    _with_transport(monkeypatch, handler)
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 504


@pytest.mark.anyio
async def test_an_unreachable_embedder_is_a_503_with_retry_after(embedder, monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=_request)

    _with_transport(monkeypatch, handler)
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 503
    assert caught.value.headers["Retry-After"] == "5"


@pytest.mark.anyio
async def test_a_not_ready_embedder_is_a_503_with_retry_after(embedder, monkeypatch) -> None:
    _with_transport(monkeypatch, lambda _r: httpx.Response(503, json={"error": "loading"}))
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 503
    assert caught.value.headers["Retry-After"] == "30"


@pytest.mark.anyio
async def test_an_upstream_error_is_a_502(embedder, monkeypatch) -> None:
    _with_transport(monkeypatch, lambda _r: httpx.Response(500, text="boom"))
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 502
    assert "boom" in caught.value.detail


@pytest.mark.anyio
async def test_a_malformed_upstream_body_is_a_502(embedder, monkeypatch) -> None:
    _with_transport(monkeypatch, lambda _r: httpx.Response(200, json=["not", "an", "object"]))
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 502


@pytest.mark.anyio
async def test_an_unconfigured_embedder_is_a_503(tmp_path, monkeypatch) -> None:
    path = tmp_path / "backends.yaml"
    path.write_text(yaml.safe_dump({"backends": []}))
    monkeypatch.setattr(route, "DEFAULT_CONFIG_PATH", str(path))
    monkeypatch.setattr(route, "_CONFIG", None)
    assert route.load_embedder_config() is None
    with pytest.raises(HTTPException) as caught:
        await route.embeddings(_request({"input": "x"}), _AUTH)
    assert caught.value.status_code == 503

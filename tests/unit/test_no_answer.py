"""No dead ends: a turn no candidate can serve still ends with an answer for a chat UI.

Open WebUI forwards the pipeline's status (and body) to the browser, so a 502 on
a workspace whose pinned model will not load leaves the user with an error banner
and no turn to continue from — while a script, opencode or the WFE harness needs
that status to retry. These tests pin both framings, the message that replaces
the status for a chat UI, and the metric every give-up records.
"""

from __future__ import annotations

import json
import time
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import portal.platform.inference.router.backend_introspect as bi
import portal.platform.inference.router.handlers as handlers
import portal.platform.inference.router.no_answer as no_answer
import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.metrics import _REGISTRY
from portal.platform.inference.router.non_streaming import BackendRequestError

WS = "auto-daily"
HINT = str(no_answer.WORKSPACES.get(WS, {}).get("model_hint") or "gemma4:26b")
OWUI = {"user-agent": "Python/3.11 aiohttp/3.14.3"}
API = {"user-agent": "python-httpx/0.28.1"}
GUARD_DETAIL = (
    f"Cannot load {HINT}: projected memory 22.7 GiB would exceed host headroom "
    "10.0 GiB (oMLX headroom 8.0 + idle Ollama 2.0 - margin 2) with nothing in flight to wait for"
)
DONE = b"data: [DONE]\n\n"


@pytest.fixture(autouse=True)
def _audience() -> typing.Iterator[None]:
    no_answer.set_chat_ui({})
    yield
    no_answer.set_chat_ui({})


def _count(workspace: str, reason: str, client: str, path: str) -> float:
    return (
        _REGISTRY.get_sample_value(
            "portal5_no_answer_total",
            {"workspace": workspace, "reason": reason, "client": client, "path": path},
        )
        or 0.0
    )


def _payloads(chunks: list[bytes]) -> list[dict[str, typing.Any]]:
    out = []
    for chunk in chunks:
        for line in chunk.decode().splitlines():
            if not line.startswith("data: "):
                continue
            body = line[6:].strip()
            if body == "[DONE]":
                continue
            payload = json.loads(body)
            assert "choices" in payload, f"non-chat event reached the client: {payload}"
            out.append(payload)
    return out


def _content(chunks: list[bytes]) -> str:
    return "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload.get("choices") or []
    )


# ── who is reading ───────────────────────────────────────────────────


def test_owui_aiohttp_user_agent_is_a_chat_ui() -> None:
    assert no_answer.is_chat_ui({"user-agent": "Python/3.11 aiohttp/3.14.3"})


def test_program_clients_are_not_a_chat_ui() -> None:
    for agent in ("python-httpx/0.28.1", "curl/8.7.1", "opencode/0.4.2", "", None):
        assert not no_answer.is_chat_ui({"user-agent": agent})


def test_forwarded_user_header_marks_owui() -> None:
    assert no_answer.is_chat_ui({"x-openwebui-user-id": "u-1"})


def test_explicit_client_header_wins_both_ways() -> None:
    assert no_answer.is_chat_ui({"x-portal-client": "chat", "user-agent": "python-httpx/0.28"})
    assert not no_answer.is_chat_ui(
        {"x-portal-client": "api", "user-agent": "Python/3.11 aiohttp/3.14"}
    )


@pytest.fixture
def api() -> typing.Iterator[typing.Any]:
    """FastAPI TestClient over the real app with a fake backend registry."""
    from fastapi.testclient import TestClient

    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers.registry = None


@pytest.mark.anyio
async def test_owui_turn_through_the_route_ends_with_a_completion(
    api: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handler records the audience from the headers Open WebUI sends."""
    from portal.platform.inference.router.auth import PIPELINE_API_KEY

    body = {"model": WS, "messages": [{"role": "user", "content": "hi"}], "stream": False}
    filled: dict[str, typing.Any] = {"model": WS, "messages": []}

    async def resolved_route(_request: typing.Any, _slot: typing.Any) -> typing.Any:
        return WS, filled, False, "", [_backend("b1")]

    async def _fail(
        backend: typing.Any,
        _body: typing.Any,
        _ws: str,
        _start: float,
        tried=None,
        **__: typing.Any,
    ) -> None:
        if tried is not None:
            tried[(backend.chat_url, HINT)] = f"{HINT}: {GUARD_DETAIL}"
        return None

    monkeypatch.setattr(handlers, "_resolve_request_route", resolved_route)
    monkeypatch.setattr(handlers, "_try_non_streaming", _fail)
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    auth = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}

    chat = api.post(
        "/v1/chat/completions", json=body, headers={**auth, "user-agent": OWUI["user-agent"]}
    )
    assert chat.status_code == 200, chat.text
    message = chat.json()["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert HINT in message["content"] and "retry in a minute" in message["content"]

    program = api.post(
        "/v1/chat/completions", json=body, headers={**auth, "user-agent": API["user-agent"]}
    )
    assert program.status_code == 502


# ── the message and the count ────────────────────────────────────────


def test_reason_class_names_what_held_the_model_back() -> None:
    assert no_answer.reason_class([GUARD_DETAIL]) == "memory_refused"
    assert no_answer.reason_class(["m: timed out after 300s"]) == "timeout"
    assert no_answer.reason_class(["m: HTTP 500"]) == "engine_error"
    assert no_answer.reason_class([]) == "no_candidate"


def test_message_names_the_model_the_reason_and_the_retry() -> None:
    text = no_answer.message(HINT, [GUARD_DETAIL], None)
    assert HINT in text
    assert "could not be loaded" in text
    assert "would exceed host headroom" in text
    assert "retry in a minute" in text
    assert "switch to the" not in text


def test_message_wording_follows_the_reason() -> None:
    timeout = no_answer.message(HINT, [f"{HINT}: timed out after 300s"], None)
    assert "did not answer in time" in timeout and "retry in a moment" in timeout
    engine = no_answer.message(HINT, ["backend unreachable"], None)
    assert "could not be served" in engine and "retry in a moment" in engine


@pytest.mark.anyio
async def test_alternative_workspace_is_a_loaded_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        no_answer,
        "WORKSPACES",
        {
            WS: {"model_hint": HINT},
            "auto-fast": {"model_hint": "qwen3:8b"},
            "bench-x": {"model_hint": "bench:1b"},
        },
    )
    monkeypatch.setattr(bi, "loaded_models", _loaded({"qwen3:8b", "bench:1b"}))
    assert await no_answer.alternative_workspace(WS, HINT) == ("auto-fast", "qwen3:8b")
    text = no_answer.message(HINT, [GUARD_DETAIL], await no_answer.alternative_workspace(WS, HINT))
    assert "**auto-fast**" in text and "qwen3:8b" in text


@pytest.mark.anyio
async def test_alternative_workspace_matches_a_case_only_resident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        no_answer,
        "WORKSPACES",
        {WS: {"model_hint": HINT}, "auto-fast": {"model_hint": "qwen3:Q4_K_M"}},
    )
    monkeypatch.setattr(bi, "loaded_models", _loaded({"qwen3:q4_k_m"}))
    assert await no_answer.alternative_workspace(WS, HINT) == ("auto-fast", "qwen3:Q4_K_M")


@pytest.mark.anyio
async def test_no_alternative_when_nothing_else_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        no_answer, "WORKSPACES", {WS: {"model_hint": HINT}, "auto-fast": {"model_hint": "qwen3:8b"}}
    )
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    assert await no_answer.alternative_workspace(WS, HINT) is None


@pytest.mark.anyio
async def test_chat_reply_counts_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    before = _count(WS, "memory_refused", "chat", "streaming")
    await no_answer.chat_reply(WS, HINT, [GUARD_DETAIL], path="streaming")
    assert _count(WS, "memory_refused", "chat", "streaming") == before + 1


def _loaded(names: set[str]) -> typing.Callable[[], typing.Awaitable[set[str]]]:
    async def _call() -> set[str]:
        return names

    return _call


@pytest.mark.anyio
async def test_loaded_models_merges_both_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    import portal.platform.inference.router.validation as validation

    class _Resp:
        def __init__(self, payload: dict[str, typing.Any]) -> None:
            self._payload = payload

        def json(self) -> dict[str, typing.Any]:
            return self._payload

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: typing.Any) -> None:
            return None

        async def get(self, url: str, **_: typing.Any) -> _Resp:
            if url.endswith("/api/ps"):
                return _Resp({"models": [{"name": "llama:8b"}]})
            return _Resp(
                {"models": [{"id": "omlx-27b", "loaded": True}, {"id": "cold", "loaded": False}]}
            )

    monkeypatch.setattr(bi.httpx, "AsyncClient", lambda **_: _Client())
    monkeypatch.setattr(
        validation,
        "registry",
        SimpleNamespace(
            list_healthy_backends=lambda: [
                SimpleNamespace(url="http://ollama", type="ollama"),
                SimpleNamespace(url="http://omlx", type="omlx"),
            ]
        ),
    )
    assert await bi.loaded_models() == {"llama:8b", "omlx-27b"}


@pytest.mark.anyio
async def test_loaded_models_without_a_registry_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import portal.platform.inference.router.validation as validation

    monkeypatch.setattr(validation, "registry", None)
    assert await bi.loaded_models() == set()


# ── non-streaming: the 502 a chat UI never sees ──────────────────────


def _fail_every_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail(
        backend: typing.Any,
        body: dict[str, typing.Any],
        workspace_id: str,
        start_time: float,
        *,
        enforce_hint: bool = True,
        persona: str = "",
        tried: dict[tuple[str, str], str] | None = None,
        max_hops: int = 1,
    ) -> None:
        if tried is not None:
            tried[(backend.chat_url, HINT)] = f"{HINT}: {GUARD_DETAIL}"
        return None

    monkeypatch.setattr(handlers, "_try_non_streaming", _fail)
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))


async def _dispatch(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]) -> typing.Any:
    _fail_every_candidate(monkeypatch)
    no_answer.set_chat_ui(headers)
    return await handlers._dispatch_non_streaming(
        [_backend("b1"), _backend("b2")],
        {"model": WS, "messages": []},
        WS,
        "",
        False,
        time.monotonic(),
    )


def _backend(bid: str, kind: str = "ollama") -> SimpleNamespace:
    return SimpleNamespace(
        id=bid, type=kind, url=f"http://{bid}", chat_url=f"http://{bid}/v1/chat/completions"
    )


@pytest.mark.anyio
async def test_chat_ui_gets_a_completion_not_a_502(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _count(WS, "memory_refused", "chat", "non_streaming")
    resp = await _dispatch(monkeypatch, OWUI)
    assert resp.status_code == 200
    message = json.loads(resp.body)["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert HINT in message["content"] and "retry in a minute" in message["content"]
    assert _count(WS, "memory_refused", "chat", "non_streaming") == before + 1


@pytest.mark.anyio
async def test_api_client_keeps_the_502(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _count(WS, "memory_refused", "api", "non_streaming")
    with pytest.raises(HTTPException) as exc:
        await _dispatch(monkeypatch, API)
    assert exc.value.status_code == 502
    assert "All backends failed" in str(exc.value.detail)
    assert _count(WS, "memory_refused", "api", "non_streaming") == before + 1


@pytest.mark.anyio
async def test_capacity_refusal_reaches_a_chat_ui_as_a_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fail(
        backend: typing.Any,
        body: dict[str, typing.Any],
        workspace_id: str,
        start_time: float,
        **_: typing.Any,
    ) -> None:
        calls.append(backend.id)
        if len(calls) == 1:
            raise BackendRequestError(
                400, "prefill memory guard: projected memory would exceed the ceiling"
            )
        return None

    monkeypatch.setattr(handlers, "_try_non_streaming", _fail)
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    no_answer.set_chat_ui(OWUI)
    resp = await handlers._dispatch_non_streaming(
        [_backend("b1", "omlx"), _backend("b2")],
        {"model": WS, "messages": []},
        WS,
        "",
        False,
        time.monotonic(),
    )
    assert resp.status_code == 200
    text = json.loads(resp.body)["choices"][0]["message"]["content"]
    assert "prefill memory guard" in text and HINT in text


@pytest.mark.anyio
async def test_malformed_request_still_surfaces_its_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _bad(*_: typing.Any, **__: typing.Any) -> None:
        raise BackendRequestError(413, "request too large")

    monkeypatch.setattr(handlers, "_try_non_streaming", _bad)
    no_answer.set_chat_ui(OWUI)
    with pytest.raises(HTTPException) as exc:
        await handlers._dispatch_non_streaming(
            [_backend("b1")], {"model": WS, "messages": []}, WS, "", False, time.monotonic()
        )
    assert exc.value.status_code == 413 and "too large" in str(exc.value.detail)


# ── streaming: the same turn, as SSE ─────────────────────────────────


class _StreamCtx:
    """``_http_client.stream(...)`` returning a non-200 reply."""

    def __init__(self, status: int, body: bytes) -> None:
        self._status, self._body = status, body

    async def __aenter__(self) -> typing.Any:
        resp = MagicMock()
        resp.status_code = self._status

        async def _aread() -> bytes:
            return self._body

        resp.aread = _aread
        return resp

    async def __aexit__(self, *_: typing.Any) -> None:
        return None


async def _guarded(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]) -> list[bytes]:
    client = MagicMock()
    client.stream.side_effect = lambda *_a, **_k: _StreamCtx(
        507, json.dumps({"error": GUARD_DETAIL}).encode()
    )
    monkeypatch.setattr(st, "_http_client", client)
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    no_answer.set_chat_ui(headers)
    return [
        chunk
        async for chunk in st._stream_from_backend_guarded(
            "http://ollama/v1/chat/completions",
            {"model": HINT, "messages": []},
            WS,
            HINT,
        )
    ]


@pytest.mark.anyio
async def test_single_candidate_guard_refusal_answers_a_chat_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _count(WS, "memory_refused", "chat", "streaming")
    chunks = await _guarded(monkeypatch, OWUI)
    text = _content(chunks)
    assert HINT in text and "retry in a minute" in text
    assert "[Pipeline stream error" not in text
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE
    assert _payloads(chunks)[-1]["choices"][0]["finish_reason"] == "stop"
    assert _count(WS, "memory_refused", "chat", "streaming") == before + 1


@pytest.mark.anyio
async def test_single_candidate_guard_refusal_keeps_the_technical_ending_for_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _count(WS, "memory_refused", "api", "streaming")
    chunks = await _guarded(monkeypatch, API)
    text = _content(chunks)
    assert "[Pipeline stream error" in text and "HTTP 507" in text
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE
    assert _count(WS, "memory_refused", "api", "streaming") == before + 1


@pytest.mark.anyio
async def test_fallback_exhausted_answers_a_chat_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _inner(*_: typing.Any, **__: typing.Any) -> typing.AsyncIterator[bytes]:
        yield st._backend_error_chunk(507, json.dumps({"error": GUARD_DETAIL}).encode())
        yield DONE

    async def _no_freed() -> list[str]:
        return []

    async def _no_result(*_: typing.Any, **__: typing.Any) -> None:
        return None

    monkeypatch.setattr(st, "_select_stream_fn", lambda *_a, **_k: _inner())
    monkeypatch.setattr(st, "_try_non_streaming", _no_result)
    monkeypatch.setattr(st, "free_ollama_for_omlx", _no_freed)
    monkeypatch.setattr(bi, "loaded_models", _loaded(set()))
    no_answer.set_chat_ui(OWUI)
    before = _count(WS, "memory_refused", "chat", "streaming")

    chunks = [
        chunk
        async for chunk in st._stream_with_fallback(
            backend=_backend("omlx", "omlx"),
            body={"model": WS, "messages": []},
            workspace_id=WS,
            target_model=HINT,
            persona="",
            effective_tools=[],
            start_time=time.monotonic(),
            has_tools=False,
            chain=[],
            portal_no_tools=False,
            secondary_model="",
            tertiary_model="",
            remaining=[_backend("b2")],
            slot=MagicMock(),
            backend_body={"model": HINT},
        )
    ]
    text = _content(chunks)
    assert HINT in text and "retry in a minute" in text
    assert "[Pipeline stream error" not in text
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE
    assert _count(WS, "memory_refused", "chat", "streaming") == before + 1


@pytest.mark.anyio
async def test_malformed_stream_error_keeps_the_technical_ending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_answer.set_chat_ui(OWUI)
    before = _count(WS, "engine_error", "chat", "streaming")
    frames = await st._backend_error_ending(400, b'{"error": "bad parameter"}', "rid", WS)
    text = _content(frames)
    assert "[Pipeline stream error" in text and "HTTP 400" in text
    assert _count(WS, "engine_error", "chat", "streaming") == before


@pytest.mark.anyio
async def test_capacity_rejection_is_a_retryable_chat_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_answer.set_chat_ui(OWUI)
    frames = await st._backend_error_ending(
        400,
        b'{"error": "prefill memory guard: projected memory would exceed the ceiling"}',
        "rid",
        WS,
    )
    assert "retry in a minute" in _content(frames)


@pytest.mark.anyio
async def test_failed_chain_hop_answers_a_chat_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    no_answer.set_chat_ui(OWUI)
    error = st._backend_error_chunk(507, json.dumps({"error": GUARD_DETAIL}).encode())
    before = _count(WS, "memory_refused", "chat", "streaming")
    hop = SimpleNamespace(error=error, started=True)
    frames = await st._hop_stop_frames(
        hop, cascade_to_candidates=True, request_id="rid", workspace_id=WS
    )
    assert "retry in a minute" in _content(frames)
    assert _count(WS, "memory_refused", "chat", "streaming") == before + 1

    intermediate = SimpleNamespace(error=error, started=False)
    frames = await st._hop_stop_frames(
        intermediate, cascade_to_candidates=True, request_id="rid", workspace_id=WS
    )
    assert frames == [error]  # an intermediate hop cascades, it is not a give-up


@pytest.mark.anyio
async def test_fallback_exhausted_keeps_the_technical_ending_for_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _inner(*_: typing.Any, **__: typing.Any) -> typing.AsyncIterator[bytes]:
        yield st._backend_error_chunk(503, b"engine down")
        yield DONE

    async def _no_result(*_: typing.Any, **__: typing.Any) -> None:
        return None

    monkeypatch.setattr(st, "_select_stream_fn", lambda *_a, **_k: _inner())
    monkeypatch.setattr(st, "_try_non_streaming", _no_result)
    no_answer.set_chat_ui(API)
    chunks = [
        chunk
        async for chunk in st._stream_with_fallback(
            backend=_backend("omlx", "omlx"),
            body={"model": WS, "messages": []},
            workspace_id=WS,
            target_model=HINT,
            persona="",
            effective_tools=[],
            start_time=time.monotonic(),
            has_tools=False,
            chain=[],
            portal_no_tools=False,
            secondary_model="",
            tertiary_model="",
            remaining=[_backend("b2")],
            slot=MagicMock(),
            backend_body={"model": HINT},
        )
    ]
    text = _content(chunks)
    assert "[Pipeline stream error" in text and "HTTP 503" in text
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE

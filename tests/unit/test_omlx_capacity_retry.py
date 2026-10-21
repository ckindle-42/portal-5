"""oMLX capacity refusals (the 400 prefill guard, the 507 load ceiling) free idle Ollama once and
retry oMLX, on every path; a free never takes a busy or protected Ollama model."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from portal.platform.inference import load_guard
from portal.platform.inference.router import backend_introspect as bi
from portal.platform.inference.router import streaming
from portal.platform.inference.router.non_streaming import is_omlx_capacity_refusal

LOAD_CEILING = (
    b'{"error":{"message":"Model \'unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit\' (21.16GB) does not fit '
    b'under the dynamic memory ceiling (8.12GB). Close other apps to free RAM"}}'
)
PREFILL_GUARD = b'{"error":{"message":"prefill memory guard: would exceed the memory ceiling"}}'
OLLAMA_LOAD = b'{"error":"model requires 27.1 GiB, 26.7 GiB available; cannot load"}'


def test_the_predicate_matches_both_omlx_refusals_and_nothing_else() -> None:
    assert is_omlx_capacity_refusal(507, LOAD_CEILING)
    assert is_omlx_capacity_refusal(400, PREFILL_GUARD)
    assert not is_omlx_capacity_refusal(400, b'{"error":"invalid parameter temperature"}')
    assert not is_omlx_capacity_refusal(500, LOAD_CEILING)


def test_freeable_skips_the_router_busy_and_protected_models(monkeypatch) -> None:
    guard = SimpleNamespace(
        busy=lambda engine, model: 1 if model == "busy:7b" else 0,
        protected=lambda engine: {"failover:9b"} if engine == load_guard.OLLAMA else set(),
    )
    monkeypatch.setattr(load_guard, "GUARD", guard)
    names = ["router:1b", "busy:7b", "failover:9b", "idle:30b"]
    assert bi._freeable(names, "router:1b") == ["idle:30b"]


def test_an_omlx_protection_never_shields_an_ollama_model(monkeypatch) -> None:
    class _Guard(load_guard.LoadGuard):
        def __init__(self) -> None:  # bypass the real constructor
            self._protected = {("omlx", "same-name"): float("inf")}
            self._busy = {}

    monkeypatch.setattr(load_guard, "GUARD", _Guard())
    assert bi._freeable(["same-name"], "router") == ["same-name"]


class _Resp:
    def __init__(self, status: int, body: bytes = b"", lines: list[str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self._lines = lines or []

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _Stream:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *exc) -> None:
        return None


def test_a_507_on_the_tool_loop_frees_once_and_retries_omlx(monkeypatch) -> None:
    answer = json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]})
    responses = [
        _Resp(507, LOAD_CEILING),
        _Resp(200, lines=[f"data: {answer}", "data: [DONE]"]),
    ]
    posts: list[str] = []
    freed: list[int] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            posts.append(url)
            return _Stream(responses.pop(0))

    async def fake_free(*_a, **_k):
        freed.append(1)
        return ["idle:30b"]

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)

    async def run() -> bytes:
        out = b""
        gen = streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
            "auto-daily",
            "m",
            "",
            set(),
        )
        async for chunk in gen:
            out += chunk
        return out

    out = asyncio.run(run())

    assert len(posts) == 2 and freed == [1]
    assert b"hello" in out
    assert b'"error"' not in out  # the 507 never reaches the client


def _drive_tool_loop(monkeypatch, outcomes: list) -> tuple[bytes, list[str]]:
    """Run the tool loop against scripted POST outcomes (a _Resp, or an exception to raise)."""
    posts: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            posts.append(url)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return _Stream(outcome)

    async def no_engine(*_a, **_k):
        return False

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    from portal.platform.inference.router import backend_introspect

    monkeypatch.setattr(backend_introspect, "model_still_running", no_engine)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
            "auto-daily",
            "m",
            "",
            set(),
        ):
            out += chunk
        return out

    return asyncio.run(run()), posts


def test_a_connect_timeout_retries_the_same_backend_once(monkeypatch) -> None:
    """The connection never opened, so nothing was sent: retry instead of failing the turn over."""
    import httpx

    answer = json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]})
    out, posts = _drive_tool_loop(
        monkeypatch,
        [httpx.ConnectTimeout("connect"), _Resp(200, lines=[f"data: {answer}", "data: [DONE]"])],
    )
    assert len(posts) == 2 and b"hello" in out and b'"error"' not in out


def test_a_second_connect_timeout_and_any_read_timeout_surface_as_errors(monkeypatch) -> None:
    import httpx

    out, posts = _drive_tool_loop(
        monkeypatch, [httpx.ConnectTimeout("a"), httpx.ConnectTimeout("b")]
    )
    assert len(posts) == 2
    assert "Backend timed out and no model is loaded" in out.decode()
    assert b'"error"' not in out and out.endswith(b"data: [DONE]\n\n")

    out, posts = _drive_tool_loop(monkeypatch, [httpx.ReadTimeout("slow")])
    # A read timeout may have started generating: report it, never retry.
    assert len(posts) == 1
    assert "Backend timed out and no model is loaded" in out.decode()
    assert b'"error"' not in out and out.endswith(b"data: [DONE]\n\n")

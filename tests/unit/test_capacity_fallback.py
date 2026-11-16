"""A memory-refused interactive turn gets a lighter declared seat, or an explicit notice.

The load guard's 507 is the last resort, not the answer: a chat UI whose seat will
not load is offered the workspace's own declared variants that fit right now, with
a visible note naming the seat that answered. Pins, chains and councils are never
substituted; API clients keep their status; every failure falls through to the
no-answer notice (tests/unit/test_no_answer.py pins that framing).
"""

from __future__ import annotations

import json
import typing
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse

import portal.platform.inference.router.handlers as handlers
import portal.platform.inference.router.no_answer as no_answer
import portal.platform.inference.router.streaming as st
from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import capacity_fallback as cf
from portal.platform.inference.router import validation
from portal.platform.inference.router.metrics import _REGISTRY
from portal.platform.inference.router.workspaces import WORKSPACES

WS = "auto-reasoning"  # declares deep / math / glm-thinker variants
HINT = str(WORKSPACES.get(WS, {}).get("model_hint") or "")
GUARD_DETAIL = (
    f"Cannot load {HINT}: projected memory 32.8 GiB would exceed host headroom "
    "21.9 GiB (oMLX headroom 23.9 + idle Ollama 0.0 - margin 2) with nothing in flight to wait for"
)
OWUI = {"user-agent": "Python/3.11 aiohttp/3.14.3"}
API = {"user-agent": "python-httpx/0.28.1"}
BODY: dict[str, typing.Any] = {"model": WS, "messages": [{"role": "user", "content": "hi"}]}


def _backend() -> typing.Any:
    return SimpleNamespace(
        id="fake",
        type="ollama",
        url="http://ollama:11434",
        chat_url="http://ollama:11434/v1/chat/completions",
        resolve_model=lambda hint: hint,
    )


def _registry() -> typing.Any:
    backend = _backend()
    return SimpleNamespace(
        list_backends=lambda: [backend],
        get_backend_candidates=lambda _ws: [backend],
    )


def _completion(model: str) -> JSONResponse:
    return JSONResponse(
        content={
            "choices": [{"message": {"role": "assistant", "content": "the answer"}, "index": 0}]
        },
        headers={"x-portal-route": f"{WS}::deep;fake;{model}"},
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> typing.Iterator[None]:
    no_answer.set_chat_ui(OWUI)
    monkeypatch.setattr(validation, "registry", _registry())
    monkeypatch.setattr(lg, "GUARD", SimpleNamespace(plan=_fits(True)))
    yield
    no_answer.set_chat_ui({})


def _fits(value: bool) -> typing.Any:
    async def plan(_base: str, _models: typing.Any) -> dict[str, typing.Any]:
        return {"fits": value}

    return plan


def _content(response: JSONResponse) -> str:
    data = json.loads(response.body)
    return str(data["choices"][0]["message"]["content"])


def _fallback_count(variant: str) -> float:
    return (
        _REGISTRY.get_sample_value(
            "portal5_capacity_fallback_total", {"workspace": WS, "variant": variant}
        )
        or 0.0
    )


async def test_memory_refusal_answers_from_a_fitting_declared_variant() -> None:
    before = _fallback_count("deep")
    result = await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=_dispatch_ok)
    assert result is not None
    text = _content(result)
    assert text.startswith("⚠️") and HINT in text
    assert "auto-reasoning::deep" in text and "the answer" in text
    assert _fallback_count("deep") == before + 1


async def _dispatch_ok(
    backend: typing.Any, body: typing.Any, ws: str, *_a: typing.Any, **_k: typing.Any
) -> JSONResponse:
    assert ws == f"{WS}::deep" and body["stream"] is False
    return _completion("glm-4.7-flash:Q4_K_M-ctx64k")


async def test_no_fitting_variant_leaves_the_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lg, "GUARD", SimpleNamespace(plan=_fits(False)))
    called = False

    async def dispatch(*_a: typing.Any, **_k: typing.Any) -> None:
        nonlocal called
        called = True
        return None

    assert await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=dispatch) is None
    assert not called  # a seat that does not fit is never loaded


async def test_pinned_model_is_never_substituted() -> None:
    pinned = f"{WS}::model={HINT}"
    assert (
        await cf.try_capacity_fallback(pinned, BODY, [GUARD_DETAIL], dispatch=_dispatch_ok) is None
    )


async def test_chain_workspace_is_never_substituted(monkeypatch: pytest.MonkeyPatch) -> None:
    base = dict(WORKSPACES[WS])
    monkeypatch.setitem(WORKSPACES, WS, {**base, "chain": [{"model": "x"}]})
    assert await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=_dispatch_ok) is None


async def test_non_memory_failure_is_not_a_capacity_fallback() -> None:
    assert (
        await cf.try_capacity_fallback(WS, BODY, ["timed out after 300s"], dispatch=_dispatch_ok)
        is None
    )


async def test_dispatch_failure_falls_through_to_the_notice() -> None:
    async def dispatch(*_a: typing.Any, **_k: typing.Any) -> None:
        raise OSError("engine down")

    assert await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=dispatch) is None


async def test_api_client_keeps_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    no_answer.set_chat_ui(API)
    called = False

    async def dispatch(*_a: typing.Any, **_k: typing.Any) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(handlers, "_try_non_streaming", dispatch)
    with pytest.raises(HTTPException) as err:
        await handlers._give_up(WS, BODY, None, [GUARD_DETAIL])
    assert err.value.status_code == 502
    assert not called


async def test_give_up_returns_the_noted_fallback_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(handlers, "_try_non_streaming", _dispatch_ok)
    result = await handlers._give_up(WS, BODY, None, [GUARD_DETAIL])
    assert result.status_code == 200
    assert "auto-reasoning::deep" in _content(result)


async def test_stream_exhaustion_answers_with_the_noted_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(st, "_try_non_streaming", _dispatch_ok)
    frames = await st._exhausted_frames(WS, BODY, GUARD_DETAIL)
    text = _sse_text(frames)
    assert "auto-reasoning::deep" in text and "the answer" in text
    assert frames[-1] == b"data: [DONE]\n\n"


async def test_standalone_stream_507_answers_with_the_noted_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-candidate stream refused before any output also gets the lighter seat."""
    monkeypatch.setattr(st, "_try_non_streaming", _dispatch_ok)
    raw = json.dumps({"error": GUARD_DETAIL}).encode()
    frames = await st._backend_error_ending(507, raw, f"chatcmpl-{WS}", WS, BODY)
    text = _sse_text(frames)
    assert "auto-reasoning::deep" in text and "the answer" in text
    assert frames[-1] == b"data: [DONE]\n\n"


def _sse_text(frames: list[bytes]) -> str:
    return "".join(
        json.loads(line[6:])["choices"][0]["delta"].get("content", "")
        for chunk in frames
        for line in chunk.decode().splitlines()
        if line.startswith("data: ") and line[6:].strip() != "[DONE]"
    )


async def test_stack_down_only_variant_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from portal.platform.inference import config as cfg

    real = cfg.load_portal_config()
    spec = real.workspaces[WS]
    variants = {**spec.variants}
    first = next(iter(variants))
    variants[first] = {**variants[first], "stack_down_only": True}
    monkeypatch.setattr(spec, "variants", variants)
    names = cf._variant_names(WS)
    assert first not in names and names  # the other declared variants remain

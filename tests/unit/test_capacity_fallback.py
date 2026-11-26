"""A memory-refused interactive turn gets a lighter declared seat, or an explicit notice.

The load guard's 507 is the last resort, not the answer: a chat UI whose seat will
not load is offered the workspace's own declared variants that fit right now, with
a visible note naming the seat that answered. Pins, chains and councils are never
substituted; API clients keep their status; every failure falls through to the
no-answer notice (tests/unit/test_no_answer.py pins that framing).
"""

from __future__ import annotations

import typing
from types import SimpleNamespace

import pytest

import portal.platform.inference.router.no_answer as no_answer
from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import capacity_fallback as cf
from portal.platform.inference.router import validation
from portal.platform.inference.router.workspaces import WORKSPACES

WS = "auto-reasoning"  # declares deep / math / glm-thinker variants

HINT = str(WORKSPACES.get(WS, {}).get("model_hint") or "")

GUARD_DETAIL = (
    f"Cannot load {HINT}: projected memory 32.8 GiB would exceed host headroom "
    "21.9 GiB (oMLX headroom 23.9 + idle Ollama 0.0 - margin 2) with nothing in flight to wait for"
)

OWUI = {"user-agent": "Python/3.11 aiohttp/3.14.3"}

BODY: dict[str, typing.Any] = {"model": WS, "messages": [{"role": "user", "content": "hi"}]}


def _backend() -> typing.Any:
    return SimpleNamespace(
        id="fake",
        type="ollama",
        group="general",
        url="http://ollama:11434",
        chat_url="http://ollama:11434/v1/chat/completions",
        resolve_model=lambda hint: hint,
    )


def _registry(groups: list[str] | None = None) -> typing.Any:
    backend = _backend()
    return SimpleNamespace(
        list_backends=lambda: [backend],
        get_backend_candidates=lambda _ws: [backend],
        declared_groups=lambda _ws: groups if groups is not None else ["general"],
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


async def test_dispatch_failure_falls_through_to_the_notice() -> None:
    async def dispatch(*_a: typing.Any, **_k: typing.Any) -> None:
        raise OSError("engine down")

    assert await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=dispatch) is None


async def test_served_variant_leaves_a_receipt_on_the_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record must name the seat that answered, not end with no outcome at all.

    Without the receipt a trace consumer reading ``backend``/``model``/``outcome``
    (bench_security_qat.trace_failures) sees a turn that WAS served as an unnamed,
    outcome-less record.
    """
    from fastapi.responses import JSONResponse

    notes: list[dict[str, typing.Any]] = []
    spans: list[dict[str, typing.Any]] = []
    monkeypatch.setattr(cf, "trace_note", lambda **fields: notes.append(fields))
    monkeypatch.setattr(
        cf, "trace_span", lambda name, **fields: spans.append({"name": name, **fields})
    )
    synthetic = f"{WS}::lite"
    monkeypatch.setattr(cf, "_variant_names", lambda _ws: ["lite"])
    monkeypatch.setattr(cf, "_register_variant", lambda _base, _name: synthetic)
    monkeypatch.setitem(WORKSPACES, synthetic, {"model_hint": "lite-hint"})

    async def dispatch(_backend: typing.Any, _body: typing.Any, ws_id: str, *_a: typing.Any, **_k):
        assert ws_id == synthetic
        return JSONResponse(
            {"choices": [{"message": {"role": "assistant", "content": "lite answer"}}]},
            headers={"x-portal-route": f"{ws_id};fake;lite-hint"},
        )

    result = await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=dispatch)

    assert result is not None
    assert notes == [
        {
            "backend": "fake",
            "model": "lite-hint",
            "workspace": synthetic,
            "outcome": "ok",
            "capacity_fallback": "lite",
        }
    ]
    assert spans == [
        {
            "name": "backend.selected",
            "backend": "fake",
            "model": "lite-hint",
            "fallback": True,
            "capacity_fallback": "lite",
        }
    ]


async def test_a_variant_outside_the_declared_groups_is_never_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-11-26: the tiny extract seat answered a memory-refused turn from a
    group the workspace never routes to — another workspace's chain, not this
    seat's fallback. The substitute must come from the declared routing, or not
    at all."""
    from fastapi.responses import JSONResponse

    stranger = SimpleNamespace(
        id="stranger",
        type="ollama",
        group="creative",
        url="http://ollama:11434",
        chat_url="http://ollama:11434/v1/chat/completions",
        resolve_model=lambda hint: hint,
    )
    local = _backend()
    monkeypatch.setattr(
        validation,
        "registry",
        SimpleNamespace(
            list_backends=lambda: [local, stranger],
            get_backend_candidates=lambda _ws: [local, stranger],
            declared_groups=lambda _ws: ["general"],
        ),
    )
    monkeypatch.setattr(cf, "_variant_names", lambda _ws: ["extract"])
    monkeypatch.setattr(cf, "_register_variant", lambda _base, _n: f"{WS}::extract")
    monkeypatch.setitem(WORKSPACES, f"{WS}::extract", {"model_hint": "tiny-hint"})
    dispatches: list[str] = []

    async def dispatch(backend: typing.Any, _body: typing.Any, *_a: typing.Any, **_k):
        dispatches.append(backend.id)
        return JSONResponse(
            {"choices": [{"message": {"role": "assistant", "content": "x"}}]},
            headers={"x-portal-route": f"{WS}::extract;{backend.id};tiny-hint"},
        )

    result = await cf.try_capacity_fallback(WS, BODY, [GUARD_DETAIL], dispatch=dispatch)

    assert dispatches == ["fake"]  # the stranger group's backend never dispatched
    assert result is not None

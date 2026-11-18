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

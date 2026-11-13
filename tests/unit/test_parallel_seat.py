"""Parallel-seat routing: idle Ollama twin release, and the chat yield gate.

No network. Engines are ``httpx.MockTransport`` and in-process yield state.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx

from portal.platform.inference.load_guard import OLLAMA
from portal.platform.inference.router import streaming
from portal.platform.inference.router.concurrency import RequestSlot
from portal.platform.inference.router.parallel_seat import (
    YIELD,
    _release_one,
    release_fallback_copy,
)

HINT = "gemma4:26b-a4b-it-qat-ctx8k-hunt"


def setup_function() -> None:
    YIELD._pins = 0
    YIELD._held.clear()
    YIELD._clear.set()


def teardown_function() -> None:
    YIELD._pins = 0
    YIELD._held.clear()
    YIELD._clear.set()


class _Guard:
    def __init__(self, *, busy: set[str] | None = None, protected: set[str] | None = None) -> None:
        self._busy = busy or set()
        self._protected = protected or set()

    def busy(self, engine: str, name: str) -> int:
        return 1 if name in self._busy else 0

    def protected(self, engine: str) -> set[str]:
        return set(self._protected)


def _client(models: list[str]) -> tuple[httpx.AsyncClient, list[dict[str, object]]]:
    posted: list[dict[str, object]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": n, "size": 1} for n in models]})
        if req.url.path == "/api/generate":
            posted.append(json.loads(req.content))
            return httpx.Response(200, json={"done": True})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), posted


async def test_idle_fallback_copy_is_unloaded() -> None:
    client, posted = _client([HINT])
    async with client:
        freed = await _release_one(client, "http://ollama:11434", HINT, _Guard(), OLLAMA, "router")
    assert freed == [HINT]
    assert posted == [{"model": HINT, "keep_alive": 0}]


async def test_busy_protected_and_router_copies_stay() -> None:
    client, posted = _client([HINT])
    async with client:
        busy = await _release_one(
            client, "http://ollama:11434", HINT, _Guard(busy={HINT}), OLLAMA, "router"
        )
        protected = await _release_one(
            client,
            "http://ollama:11434",
            HINT,
            _Guard(protected={HINT.lower()}),
            OLLAMA,
            "router",
        )
        router = await _release_one(client, "http://ollama:11434", HINT, _Guard(), OLLAMA, HINT)
    assert busy == [] and protected == [] and router == []
    assert posted == []


async def test_release_is_a_no_op_for_a_seat_that_is_not_parallel(monkeypatch) -> None:
    from portal.platform.inference.router.workspaces import WORKSPACES

    monkeypatch.setitem(WORKSPACES, "auto-daily", {"max_concurrent": 1, "model_hint": HINT})
    assert await release_fallback_copy("auto-daily") == []


async def test_release_swallows_a_registry_failure(monkeypatch) -> None:
    from portal.platform.inference.router import validation
    from portal.platform.inference.router.workspaces import WORKSPACES

    monkeypatch.setitem(WORKSPACES, "hunt-reasoning", {"max_concurrent": 8, "model_hint": HINT})

    class _Registry:
        def list_backends(self) -> list[object]:
            raise RuntimeError("registry down")

    monkeypatch.setattr(validation, "registry", _Registry())
    assert await release_fallback_copy("hunt-reasoning") == []


async def test_single_candidate_stream_drops_the_twin_after_the_frames(monkeypatch) -> None:
    seen: list[str] = []

    async def _release(workspace_id: str) -> list[str]:
        seen.append(workspace_id)
        return []

    async def _room(*_args: object) -> list[str]:
        return []

    async def _frames():
        yield b"data: {}\n\n"

    monkeypatch.setattr(streaming, "make_room_for_omlx", _room)
    monkeypatch.setattr(
        "portal.platform.inference.router.parallel_seat.release_fallback_copy", _release
    )
    backend = SimpleNamespace(type="omlx")
    chunks = [
        chunk
        async for chunk in streaming._with_room_for_omlx(backend, {}, _frames(), "hunt-reasoning")
    ]
    assert chunks == [b"data: {}\n\n"]
    assert seen == ["hunt-reasoning"]


def test_pins_hold_until_every_admission_releases() -> None:
    YIELD.hold("hunt-reasoning")
    YIELD.pin()
    YIELD.pin()
    YIELD.release()
    assert YIELD.holding("hunt-reasoning")
    YIELD.release()
    assert not YIELD.holding("hunt-reasoning")


async def test_a_yield_holds_new_seat_requests_until_release() -> None:
    YIELD.hold("hunt-reasoning")
    slot = RequestSlot()
    task = asyncio.create_task(slot.acquire_workspace("hunt-reasoning"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not task.done()
    YIELD.release()
    await asyncio.wait_for(task, 1)
    slot.release()


async def test_a_yield_does_not_hold_a_different_workspace() -> None:
    YIELD.hold("hunt-reasoning")
    slot = RequestSlot()
    await asyncio.wait_for(slot.acquire_workspace("auto-daily"), 1)
    slot.release()

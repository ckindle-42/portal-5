"""Parallel seats stay on the batching engine, and yield when chat cannot fit.

A workspace with ``max_concurrent`` > 1 (hunt-reasoning) is declared parallel:
oMLX batches it, Ollama serves it one at a time. Hot-seat protection must not
steer that seat onto the Ollama copy, and a chat load that cannot fit beside
the busy seat holds new parallel work so the seat can drain and be unloaded.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from portal.platform.inference.model_names import model_key

logger = logging.getLogger(__name__)


def _workspace(workspace_id: str) -> dict[str, Any]:
    from portal.platform.inference.router.workspaces import WORKSPACES

    base = workspace_id.split("::", 1)[0]
    found = WORKSPACES.get(workspace_id) or WORKSPACES.get(base)
    return found if isinstance(found, dict) else {}


def is_parallel_workspace(workspace_id: str) -> bool:
    """True when the workspace declares a batching cap above one."""
    cap = _workspace(workspace_id).get("max_concurrent")
    return isinstance(cap, int) and cap > 1


def _seat_models() -> dict[str, str]:
    from portal.platform.inference.router.workspaces import WORKSPACES

    seats: dict[str, str] = {}
    for wid, ws in WORKSPACES.items():
        cap = ws.get("max_concurrent")
        hint = ws.get("model_hint") or ""
        if isinstance(cap, int) and cap > 1 and hint:
            seats[str(hint)] = wid
    if not seats:
        return {}
    try:
        from portal.platform.inference.cluster_backends import BackendRegistry

        for backend in BackendRegistry().list_backends():
            if backend.type != "omlx":
                continue
            for hint, native in backend.aliases.items():
                if hint in seats and native:
                    seats[native] = seats[hint]
    except Exception:
        logger.debug("parallel seat model map: registry unavailable", exc_info=True)
    return seats


_SEAT_MODELS: dict[str, str] | None = None


def seat_for_loaded_model(model_id: str) -> str | None:
    """Workspace id when ``model_id`` is a parallel seat's hint or oMLX native id."""
    global _SEAT_MODELS
    if not model_id:
        return None
    if _SEAT_MODELS is None:
        _SEAT_MODELS = _seat_models()
    return _SEAT_MODELS.get(model_id)


class ParallelYield:
    """Blocks new parallel-seat requests until every chat admission that armed one releases."""

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._pins = 0
        self._clear = asyncio.Event()
        self._clear.set()

    def hold(self, workspace_id: str) -> None:
        base = workspace_id.split("::", 1)[0]
        self._held.add(base)
        self._clear.clear()

    def pin(self) -> None:
        """Count one admission that needs the hold kept until it releases."""
        self._pins += 1

    def release(self) -> None:
        """Drop one admission's pin. The last pin clears the hold."""
        if self._pins > 0:
            self._pins -= 1
        if self._pins == 0:
            self._held.clear()
            self._clear.set()

    def holding(self, workspace_id: str) -> bool:
        base = workspace_id.split("::", 1)[0]
        return base in self._held

    async def wait(self, workspace_id: str, timeout: float) -> None:
        """Wait out a hold. A spent timeout lets the seat proceed."""
        if not self.holding(workspace_id):
            return
        try:
            await asyncio.wait_for(self._clear.wait(), timeout=max(0.0, timeout))
        except TimeoutError:
            if self.holding(workspace_id):
                logger.warning(
                    "parallel seat %s still yielding after %.0fs; letting the request proceed",
                    workspace_id,
                    timeout,
                )


YIELD = ParallelYield()


async def release_omlx_fallback(backend: Any, workspace_id: str) -> None:
    """After an oMLX answer, drop a parallel seat's idle Ollama twin."""
    if getattr(backend, "type", "") == "omlx":
        await release_fallback_copy(workspace_id)


def prefer_batching_engine(candidates: list[Any], workspace_id: str) -> list[Any]:
    """Keep a parallel seat's oMLX backend at the head of an already-ordered list.

    Hot-seat protection may have moved an Ollama candidate in front so a different
    model's prefix stays warm. A declared parallel seat batches only on oMLX, so
    that reorder is undone when oMLX can serve the hint. The input is not mutated.
    """
    if not is_parallel_workspace(workspace_id) or len(candidates) < 2:
        return list(candidates)
    hint = str(_workspace(workspace_id).get("model_hint") or "")
    if not hint:
        return list(candidates)
    for index, candidate in enumerate(candidates):
        if getattr(candidate, "type", "") != "omlx":
            continue
        resolve = getattr(candidate, "resolve_model", None)
        if resolve is None or resolve(hint) is None:
            continue
        if index == 0:
            return list(candidates)
        return [candidate, *candidates[:index], *candidates[index + 1 :]]
    return list(candidates)


async def release_fallback_copy(workspace_id: str) -> list[str]:
    """Drop an idle Ollama resident of a parallel seat just served by oMLX.

    Normal traffic must not leave the GGUF twin resident beside the batching
    copy. A busy or protected resident is left for the request that holds it.
    Failures are logged and swallowed: the user's answer is already in hand.
    """
    if not is_parallel_workspace(workspace_id):
        return []
    hint = str(_workspace(workspace_id).get("model_hint") or "")
    if not hint:
        return []
    try:
        from portal.platform.inference.router import validation

        registry = validation.registry
    except Exception:
        registry = None
    if registry is None:
        return []
    from portal.platform.inference.load_guard import GUARD, OLLAMA
    from portal.platform.inference.router.routing import _LLM_ROUTER_MODEL

    freed: list[str] = []
    try:
        urls = sorted({b.url.rstrip("/") for b in registry.list_backends() if b.type == "ollama"})
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in urls:
                freed.extend(
                    await _release_one(client, url, hint, GUARD, OLLAMA, _LLM_ROUTER_MODEL)
                )
    except Exception as exc:
        logger.warning("parallel seat: could not release Ollama fallback copy: %s", exc)
    return freed


async def _release_one(
    client: httpx.AsyncClient,
    url: str,
    hint: str,
    guard: Any,
    ollama: str,
    router_model: str,
) -> list[str]:
    response = await client.get(f"{url}/api/ps")
    if response.status_code != 200:
        return []
    freed: list[str] = []
    for row in response.json().get("models") or []:
        name = str(row.get("name") or "")
        if not name or model_key(name) != model_key(hint):
            continue
        if model_key(name) == model_key(router_model):
            continue
        if guard is not None and (
            guard.busy(ollama, name) or model_key(name) in guard.protected(ollama)
        ):
            continue
        unload = await client.post(f"{url}/api/generate", json={"model": name, "keep_alive": 0})
        if unload.is_success:
            freed.append(name)
            logger.info("parallel seat: released idle Ollama fallback %s", name)
    return freed

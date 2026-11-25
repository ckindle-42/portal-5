"""Hot-seat prefix-cache placement policy (P5-OMLX-PREFIX-CACHE-001).

Admitting a second oMLX model onto the shared oMLX engine while one model holds a
hot prefix cache is a *deep* reset: the displaced seat's next first token goes from
~1-2 s (warm append) to 76-245 s (cold re-encode of the whole prefix). The load
guard's unloader is not prefix-cache aware, and the first-candidate rule can swap a
different oMLX model onto the hot engine purely because the user (or a second seat)
picked a different coding model — no error, no capacity event, just a silent reset.

This module protects an active hot seat from that *accidental* admission at the
router/placement layer: when the ordered-candidate head would swap a different
model onto the engine that served a request within the last ``hot_seat_protect_s``
seconds, the request is steered to the first later candidate that does not touch
that engine, if one exists.

Design constraints (see coding_task/REPORT_HOT_SEAT.md §3):

- **Never denies service.** With no qualifying alternative the list is returned
  unchanged and the second model is admitted; the load guard stays the final
  arbiter. The displaced model's request is also always served — the demoted head
  stays second in the list, so every dispatch ladder still reaches it.
- **Pinned requests are exempt.** A ``::model=`` synthetic workspace
  (``preinject._resolve_model_override``) is an explicit user choice; protecting a
  cache against it would fight the pin the ladder enforces anyway.
- **Advisory reorder only.** State is a process-local, in-memory map (self-heals
  within one request after a restart); each uvicorn worker keeps its own, so under
  ``PIPELINE_WORKERS > 1`` a seat touched elsewhere is invisible — degrading to
  today's ordering, never to a failure. Nothing here touches ``load_guard``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from portal.platform.inference.cluster_backends import Backend


def engine_key(url: str) -> str:
    """Normalize a backend URL to a ``scheme://netloc`` engine identity.

    The oMLX transport base is ``url.split("/v1/chat/completions")[0]``
    (``ollama_native._omlx_request`` URL match) while ``Backend.chat_url``
    appends ``/v1/chat/completions`` to ``backend.url``; the shared oMLX engine
    is one host:port regardless of which path form is in hand, so only the
    origin is compared. Trailing slashes and any path are dropped.
    """
    parts = urlsplit(url.strip().rstrip("/"))
    return f"{parts.scheme}://{parts.netloc}".lower()


@dataclass(frozen=True)
class SeatState:
    """Most recent model served on one oMLX engine, and when."""

    model: str
    last_seen: float


class HotSeatTracker:
    """Process-local map of ``engine_key -> SeatState`` for the oMLX fleet.

    Thread-safe: recording happens on the oMLX transport path (any worker
    thread/async task), reads on the router path. Values are plain floats from
    ``time.monotonic``-compatible callables so tests can inject a clock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seats: dict[str, SeatState] = {}
        self._loaded: dict[str, set[str]] = {}

    def touch(self, key: str, model: str, *, now: float | None = None) -> None:
        """Record that ``model`` was just served on engine ``key``."""
        if not key or not model:
            return
        with self._lock:
            self._seats[key] = SeatState(
                model=model, last_seen=time.monotonic() if now is None else now
            )

    def hot_model(self, key: str, protect_s: float, *, now: float | None = None) -> str | None:
        """Return the engine's recent model, or ``None`` when nothing is hot.

        ``protect_s <= 0`` disables the policy entirely (returns ``None``), which
        is the default configuration and byte-identical to today's behaviour.
        """
        if protect_s <= 0 or not key:
            return None
        with self._lock:
            state = self._seats.get(key)
        if state is None:
            return None
        current = time.monotonic() if now is None else now
        if current - state.last_seen > protect_s:
            return None
        return state.model

    def clear(self, key: str, model: str | None = None) -> None:
        """Drop hot-seat state for ``key`` (or only when ``model`` matches)."""
        if not key:
            return
        with self._lock:
            state = self._seats.get(key)
            if state is not None and (model is None or state.model == model):
                self._seats.pop(key, None)
            if model is None:
                self._loaded.pop(key, None)
            else:
                self._loaded.get(key, set()).discard(model)

    def sync_loaded(self, key: str, loaded_models: set[str]) -> None:
        """Record what engine ``key`` has loaded; drop a hot model it unloaded."""
        if not key:
            return
        with self._lock:
            self._loaded[key] = set(loaded_models)
            state = self._seats.get(key)
            if state is not None and state.model not in loaded_models:
                self._seats.pop(key, None)

    def loaded_models(self, key: str) -> set[str]:
        """Models engine ``key`` reported resident at the last status read."""
        with self._lock:
            return set(self._loaded.get(key, ()))


#: Module-level tracker — one per pipeline process. See the module docstring for
#: why non-persistence is acceptable (advisory reorder, self-healing).
TRACKER = HotSeatTracker()


def note_omlx_activity(base_url: str, model: str) -> None:
    """Record oMLX activity at the transport choke point.

    Called from ``ollama_native._omlx_request`` immediately after
    ``guard.begin(OMLX, model)`` — every oMLX chat request (streaming or not)
    passes through it via the mounted ``OllamaNativeTransport``, so this is the
    single place the placement policy needs to observe the hot seat.
    """
    TRACKER.touch(engine_key(base_url), model)


def clear_omlx_activity(base_url: str, model: str | None = None) -> None:
    """Clear tracked hot-seat state after an oMLX eviction or unload."""
    TRACKER.clear(engine_key(base_url), model)


def sync_omlx_loaded(base_url: str, loaded_models: set[str]) -> None:
    """Drop hot-seat protection when oMLX has already unloaded the tracked model."""
    TRACKER.sync_loaded(engine_key(base_url), loaded_models)


def _head_serving_model(head: Backend, workspace_id: str, model_hint: str) -> str | None:
    """The model the head backend would load for this request.

    Mirrors the dispatchers: the resolved hint (or the workspace-id model when
    the request has no hint), else ``models[0]`` (``streaming._select_streaming_backend``).
    """
    resolved = head.resolve_model(model_hint) if model_hint else head.resolve_model(workspace_id)
    if resolved is not None:
        return resolved
    return head.models[0] if head.models else None


def _serves_request(alt: Backend, workspace_id: str, model_hint: str) -> bool:
    """Whether ``alt`` can serve this request (mirrors the dispatchers' checks).

    With a hint, ``resolve_model`` answers for alias and ``live_models``
    mismatches alike. Without one, any backend with a model list can serve its
    first model, and an empty list only works via a workspace-id model.
    """
    if model_hint:
        return alt.resolve_model(model_hint) is not None
    return bool(alt.models) or alt.resolve_model(workspace_id) is not None


def _window(protect_s: object) -> float:
    """Coerce the knob; anything that is not a real number means disabled."""
    if isinstance(protect_s, bool) or not isinstance(protect_s, (int, float)):
        return 0.0
    return float(protect_s)


def _effective_head_index(
    candidates: Sequence[Backend], workspace_id: str, model_hint: str
) -> int | None:
    """Index of the candidate the dispatchers will actually serve from.

    Non-streaming skips a candidate that cannot serve the hint and streaming
    promotes the first one that can, so the first hint-capable candidate — not
    ``candidates[0]`` — is the head whose model the request would load.
    """
    for index, candidate in enumerate(candidates):
        if _serves_request(candidate, workspace_id, model_hint):
            return index
    return None


def protect_hot_seat(
    candidates: Sequence[Backend],
    workspace_id: str,
    model_hint: str,
    protect_s: float,
    *,
    tracker: HotSeatTracker | None = None,
    now: float | None = None,
) -> list[Backend]:
    """Reorder candidates so a hot oMLX seat is not deep-reset by a model swap.

    Returns the (possibly reordered) candidate list; the input is never mutated.
    Returns the input order unchanged when:

    - ``protect_s <= 0`` (policy disabled — the default), fewer than two
      candidates, or the workspace is pinned (``::model=`` synthetic id);
    - the effective head serves the exact hint as an oMLX model id;
    - the *effective* head (the first candidate that serves the workspace's
      model hint — what the dispatchers will actually use) is not on the hot
      engine, or its model is the hot one or already resident there (serving
      it keeps the cache warm and swaps nothing out);
    - no later candidate both avoids the hot engine and serves the request.

    When the effective head would swap a different model onto the hot engine,
    the first qualifying alternative takes its place and the demoted head moves
    one slot back — reordered, never dropped. Testing the literal first entry
    instead demoted a seat whose own oMLX copy was the hot one, because an
    earlier group-mate could not serve the hint at all and would have been
    skipped by both dispatchers.
    """
    protect_s = _window(protect_s)
    if protect_s <= 0 or len(candidates) < 2:
        return list(candidates)
    if "::model=" in workspace_id:
        return list(candidates)

    active = tracker if tracker is not None else TRACKER
    head_index = _effective_head_index(candidates, workspace_id, model_hint)
    if head_index is None:
        return list(candidates)
    head = candidates[head_index]
    if head.type == "omlx" and model_hint in head.models:
        return list(candidates)
    head_key = engine_key(head.url)
    hot = active.hot_model(head_key, protect_s, now=now)
    if hot is None:
        return list(candidates)
    head_model = _head_serving_model(head, workspace_id, model_hint)
    if head_model == hot:
        return list(candidates)
    if head_model in active.loaded_models(head_key):
        # The seat's own copy is resident on the engine: serving it cannot deep-reset
        # the engine's other resident, and putting its other-engine copy first would
        # trade a warm copy for a cold one (2026-11-20 auto-coding).
        return list(candidates)

    # The effective head would load a different model onto the hot engine: find
    # the first alternative that neither touches that engine nor serves a
    # different model than requested.
    for idx in range(head_index + 1, len(candidates)):
        alt = candidates[idx]
        if engine_key(alt.url) == head_key:
            continue
        if not _serves_request(alt, workspace_id, model_hint):
            continue
        out = list(candidates)
        out.pop(idx)
        out.insert(head_index, alt)
        return out
    return list(candidates)

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
    - the head candidate is not the engine with a hot seat, or the head *is*
      the hot model (serving it keeps the cache warm);
    - no later candidate both avoids the hot engine and serves the request.

    When the head would swap a different model onto the hot engine, the first
    qualifying alternative is moved to the front and the demoted head stays
    second — reordered, never dropped.
    """
    protect_s = _window(protect_s)
    if protect_s <= 0 or len(candidates) < 2:
        return list(candidates)
    if "::model=" in workspace_id:
        return list(candidates)

    active = tracker if tracker is not None else TRACKER
    head = candidates[0]
    head_key = engine_key(head.url)
    hot = active.hot_model(head_key, protect_s, now=now)
    if hot is None:
        return list(candidates)
    if _head_serving_model(head, workspace_id, model_hint) == hot:
        return list(candidates)

    # Head would load a different model onto the hot engine: find the first
    # alternative that neither touches that engine nor serves a different model
    # than requested.
    for idx, alt in enumerate(candidates[1:], start=1):
        if engine_key(alt.url) == head_key:
            continue
        if not _serves_request(alt, workspace_id, model_hint):
            continue
        rest = [c for i, c in enumerate(candidates[1:], start=1) if i != idx]
        return [alt, head, *rest]
    return list(candidates)

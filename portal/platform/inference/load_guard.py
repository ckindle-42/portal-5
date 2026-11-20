"""Host-memory admission for model loads across Ollama and oMLX.

Ollama and oMLX draw on one unified-memory pool, and each engine admits a load
from its own view. On 2026-10-07 Ollama started a 22.7 GiB load with 10 GiB
system-free while oMLX loaded a 27B model; swap ran out, jetsam could not recover
and the hardware watchdog reset the Mac
(``docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md``). The pipeline's own
``MEMORY_GATE_PCT`` reads ``vm_stat``, which its container lacks, so it saw 0 %.

Every pipeline request to either engine passes ``OllamaNativeTransport``, which
reports it here. The guard keeps four things true:

1. **What is busy is known.** In-flight requests are counted per (engine, model).
   Only idle models count as evictable (Ollama) or freeable (oMLX), so concurrent
   multi-model work never admits a load that fits only by evicting a model that
   is serving a sibling request.
2. **Cold loads are serialised, generation is not.** A load of a model that is
   not resident (either engine) takes one host-wide lock, held until the model
   shows as resident (or its request ends), not for the whole response. Seats
   load one after another and then generate concurrently. Serialising oMLX loads
   too closes the incident's race (both engines measuring the same free memory).
3. **Queue, then refuse.** An Ollama cold load that does not fit waits for
   in-flight work to drain, re-checking on every request completion and at least
   every 5 s, and frees idle oMLX models on each pass. A free it issues stays
   pending until /api/ps drops the model and oMLX's ceiling covers its bytes. It is
   refused with HTTP 507 only when the caller's wait runs out. The wait is the
   request's ``X-Portal-Load-Wait`` header (seconds; batch callers send a large
   value) or ``LOAD_GUARD_WAIT_S``. The 507 says "would exceed", which the router
   already cascades as a capacity rejection. Keeper-protected residents yield
   after ordinary idle memory; active failover sources are never evicted until
   their window expires. Busy, active-elsewhere and pinned models are never evicted.
4. **Fit can be asked in advance.** ``plan()`` (route ``POST /admin/load-plan``)
   says whether a set of models fits together right now, so batch work can run
   in fit-sized waves instead of discovering the answer as refusals.

Headroom is oMLX's ``final_ceiling`` minus its resident model memory (oMLX derives
the ceiling from host free + inactive memory), plus idle Ollama residents, minus
``LOAD_GUARD_MARGIN_GB``. ``LOAD_GUARD_CEILING_GB`` replaces that ceiling with a
fixed budget; the balanced tier's ceiling follows free memory (P5-OMLX-CEILING-001).
Ollama sizing adds per-layer KV bytes at baked ``num_ctx`` using ``OLLAMA_KV_CACHE_TYPE`` (default q8_0); missing geometry falls back to weights × ``LOAD_GUARD_FACTOR`` and observed residency can raise the estimate. An oMLX cold load is admitted only inside the engine's own
prefill-safe share of that headroom (``memory.prefill_safe_zone_ratio``, read from
``OMLX_PREFILL_SAFE_ZONE_RATIO`` or the engine's settings file): past it oMLX aborts
mid-prefill, which no fallback can recover.
Cold loads unload idle models when current headroom does not cover the incoming model; an
oMLX cold load frees idle oMLX residents first (LRU, never itself) and waits out each
accepted unload's release (200 or 202), then frees Ollama's.

Fail-open: when oMLX's status cannot be read, the load is admitted. Resident
models (the router, task-router, warm seats) never wait. ``LOAD_GUARD=0`` disables
admission (tracking stays on, it is free).

Admissions, waits, free settles, unloads, refusals and headroom are reported as
``portal5_load_guard_*`` Prometheus metrics (declared in router/metrics.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import fcntl
import hashlib
import json
import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import quote

import httpx

from portal.platform.inference.identity import OMLX_SERVER_SETTINGS
from portal.platform.inference.model_names import lookup_model, model_key
from portal.platform.inference.omlx_auth import OmlxKeyAuth, omlx_api_key
from portal.platform.inference.router.metrics import (
    _load_guard_admissions_total,
    _load_guard_ceiling_bytes,
    _load_guard_free_settle_seconds,
    _load_guard_headroom_bytes,
    _load_guard_refusals_total,
    _load_guard_unloads_total,
    _load_guard_wait_seconds,
)

logger = logging.getLogger(__name__)

_GIB = 1024**3
#: Weights on disk understate the loaded footprint when the geometry cannot size the
#: KV cache: the crash's model was ~18 GB on disk and Ollama predicted 22.7 GiB at 32K ctx.
_FACTOR = float(os.environ.get("LOAD_GUARD_FACTOR", "1.25"))
_MARGIN = float(os.environ.get("LOAD_GUARD_MARGIN_GB", "2")) * _GIB
#: A fixed model-memory budget (GiB). 0 budgets against oMLX's live ceiling, which
#: the balanced tier derives from host free memory, so a verdict moves with the host.
_CEILING = float(os.environ.get("LOAD_GUARD_CEILING_GB", "0") or 0) * _GIB
#: Default wait for a cold load (interactive traffic). Batch callers raise it per
#: request with X-Portal-Load-Wait.
_WAIT_S = float(os.environ.get("LOAD_GUARD_WAIT_S", "120"))
_MAX_WAIT_S = 3600.0
#: How long a cold load may take to show as resident before the lock is
#: released anyway (the request's own end also releases it).
_LOAD_TIMEOUT_S = 600.0
_POLL_S = 0.5
# Three 30s health polls. One timed-out /v1/models/status read must not open the gate.
_HOST_FREE_STALE_S = 90.0
_PROCESS_LOCK_DIR = Path("/tmp/portal-5-load-guard")
#: Expected settle of a guard-issued Ollama free, for a warning only: measured admin
#: unloads p50 0.78 s, p95 1.93 s, max 2.29 s (n=114, oMLX 0.7.2, 2026-10-22), doubled.
_FREE_SETTLE_EXPECTED_S = 4.6
_CTX_TAG = re.compile(r"(?:^|[-_])ctx(\d+)([km]?)", re.IGNORECASE)


def _omlx_prefill_zone(settings: Path | None = None) -> float | None:
    """oMLX's ``memory.prefill_safe_zone_ratio`` — the share of its ceiling it will
    prefill inside. Read from the pipeline env (``launch.sh up`` copies it out of the
    engine's settings) or, on a host run, from the engine's settings file. None when
    neither is readable: the guard then budgets against the raw headroom."""
    raw = os.environ.get("OMLX_PREFILL_SAFE_ZONE_RATIO", "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            logger.warning("load_guard: OMLX_PREFILL_SAFE_ZONE_RATIO=%r is not a number", raw)
        else:
            if 0 < value <= 1:
                return value
            logger.warning("load_guard: OMLX_PREFILL_SAFE_ZONE_RATIO=%r is outside (0, 1]", raw)
    try:
        memory = json.loads((settings or OMLX_SERVER_SETTINGS).read_text()).get("memory") or {}
        value = float(memory.get("prefill_safe_zone_ratio") or 0)
    except Exception:
        return None
    return value if 0 < value <= 1 else None


#: oMLX aborts a request mid-prefill once process usage passes its hard watermark, and
#: prefill needs room above the model's static estimate: on 2026-11-16 an admitted
#: 16.6 GiB seat reached 19.8 GiB of a 20.7 GiB ceiling and died after the stream had
#: started. The engine's own prefill-safe share is what that room is called.
_OMLX_PREFILL_ZONE: float | None = _omlx_prefill_zone()
#: Set inside one ``admit`` task when that admission armed a parallel-seat yield.
_ADMIT_YIELD_PIN: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "admit_yield_pin", default=False
)
#: The status read ``_headroom`` just took, so a yield decision does not read it again.
_ADMIT_OMLX_STATUS: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "admit_omlx_status", default=None
)


def _show_values(show: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}

    def add(value: Any, prefix: str = "") -> None:
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, dict):
                add(child, name)
            else:
                values[name.lower()] = child

    add(show.get("model_info"))
    for field in ("parameters", "modelfile"):
        raw = show.get(field)
        if isinstance(raw, dict):
            for key, value in raw.items():
                values[str(key).lower().replace("_", "-")] = value
        elif isinstance(raw, str):
            for line in raw.splitlines():
                parts = line.strip().split(maxsplit=2)
                if len(parts) == 3 and parts[0].lower() == "parameter":
                    values[parts[1].lower().replace("_", "-")] = parts[2].strip("\"'")
                elif len(parts) == 2:
                    values[parts[0].lower().replace("_", "-")] = parts[1].strip("\"'")

    return values


def _show_value(values: dict[str, Any], *names: str) -> Any:
    for name in names:
        for key, value in values.items():
            if key == name or key.endswith(f".{name}"):
                return value
    return None


def _show_number(values: dict[str, Any], *names: str) -> float | None:
    try:
        number = float(_show_value(values, *names))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _context_tokens(model: str, values: dict[str, Any]) -> int | None:
    baked = _show_number(values, "num-ctx", "num_ctx")
    if baked:
        return int(baked)
    match = _CTX_TAG.search(model)
    if match:
        amount = int(match.group(1))
        return amount * (
            1024
            if match.group(2).lower() == "k"
            else 1024**2
            if match.group(2).lower() == "m"
            else 1
        )
    return None


def _layer_numbers(value: Any, count: int) -> list[float] | None:
    items = value if isinstance(value, list) else [value] * count
    if len(items) != count:
        return None
    try:
        numbers = [float(item) for item in items]
    except (TypeError, ValueError):
        return None
    return numbers if all(number >= 0 for number in numbers) else None


def _layer_flags(value: Any, count: int) -> list[bool] | None:
    items = value if isinstance(value, list) else [value] * count
    if len(items) != count:
        return None
    if all(isinstance(item, bool) for item in items):
        return items
    if all(isinstance(item, str) and item.lower() in {"true", "false"} for item in items):
        return [item.lower() == "true" for item in items]
    return None


def _cache_bytes(values: dict[str, Any], *names: str) -> float:
    fallback = os.environ.get("OLLAMA_KV_CACHE_TYPE", "q8_0").lower()
    raw = next((str(values[key]).lower() for key in names if key in values), fallback)
    return {
        "f32": 4.0,
        "f16": 2.0,
        "bf16": 2.0,
        "q8_0": 1.0625,
        "q6_k": 0.8203125,
        "q5_0": 0.6875,
        "q5_1": 0.75,
        "q5_k": 0.6875,
        "q4_0": 0.5625,
        "q4_1": 0.625,
        "q4_k": 0.5625,
        "q3_k": 0.4296875,
        "q2_k": 0.328125,
    }.get(raw, 2.0)


def _sliding_layers(values: dict[str, Any], count: int) -> tuple[list[bool], int] | None:
    window = _show_number(values, "attention.sliding_window", "sliding_window")
    pattern = _show_value(values, "attention.sliding_window_pattern", "sliding_window_pattern")
    if pattern is None:
        return None if window else ([False] * count, 0)
    sliding = _layer_flags(pattern, count)
    if sliding is None or (any(sliding) and not window):
        return None
    return sliding, int(window or 0)


def _attention_lengths(
    values: dict[str, Any], count: int
) -> tuple[list[float], list[float]] | None:
    key_raw = _show_value(values, "attention.key_length", "key_length")
    value_raw = _show_value(values, "attention.value_length", "value_length")
    if key_raw is None or value_raw is None:
        width = _show_number(values, "attention.head_dim", "head_dim")
        if width is None:
            embedding = _show_number(values, "embedding_length", "hidden_size", "d_model")
            query_heads = _show_number(
                values, "attention.head_count", "n_head", "num_attention_heads"
            )
            width = embedding / query_heads if embedding and query_heads else None
        if width is None:
            return None
        key_raw = width if key_raw is None else key_raw
        value_raw = width if value_raw is None else value_raw
    key = _layer_numbers(key_raw, count)
    value = _layer_numbers(value_raw, count)
    return (key, value) if key is not None and value is not None else None


def _ollama_kv_bytes(values: dict[str, Any], context: int | None) -> float | None:
    layer_count = _show_number(values, "block_count", "n_layer", "num_hidden_layers")
    if not context or not layer_count or not layer_count.is_integer():
        return None
    count = int(layer_count)
    heads = _layer_numbers(
        _show_value(
            values, "attention.head_count_kv", "n_head_kv", "num_key_value_heads", "num_kv_heads"
        ),
        count,
    )
    sliding_geometry = _sliding_layers(values, count)
    lengths = _attention_lengths(values, count)
    if heads is None or sliding_geometry is None or lengths is None:
        return None
    sliding, window = sliding_geometry
    key, value = lengths
    key_swa = _layer_numbers(
        _show_value(values, "attention.key_length_swa", "key_length_swa"), count
    )
    value_swa = _layer_numbers(
        _show_value(values, "attention.value_length_swa", "value_length_swa"), count
    )
    if any(sliding) and (key_swa is None or value_swa is None):
        return None
    cache_k = _cache_bytes(values, "cache-type-k", "kv-cache-type", "kv_cache_type")
    cache_v = _cache_bytes(values, "cache-type-v", "kv-cache-type", "kv_cache_type")
    return sum(
        (min(context, window) if is_sliding else context)
        * layer_heads
        * (
            (key_swa[index] if is_sliding and key_swa else key[index]) * cache_k
            + (value_swa[index] if is_sliding and value_swa else value[index]) * cache_v
        )
        for index, (layer_heads, is_sliding) in enumerate(zip(heads, sliding, strict=True))
        if layer_heads
    )


def _estimate_ollama_need(weights: int, show: dict[str, Any], model: str) -> float:
    """Weights plus the KV the baked ``num_ctx`` allocates; the factor stands in for
    that KV only when the geometry cannot size it."""
    values = _show_values(show)
    kv = _ollama_kv_bytes(values, _context_tokens(model, values))
    return weights * _FACTOR if kv is None else weights + kv


OLLAMA = "ollama"
OMLX = "omlx"

_load_wait: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "portal_load_wait", default=None
)

#: Set by the wait points of the admission currently running in this context.
_admit_waited: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "portal_admit_waited", default=False
)


def set_load_wait(header: str | None) -> None:
    """Record the incoming request's ``X-Portal-Load-Wait`` (seconds) for its loads."""
    try:
        value = float(header) if header else None
    except ValueError:
        value = None
    _load_wait.set(None if value is None else max(0.0, min(value, _MAX_WAIT_S)))


def load_wait_s() -> float:
    value = _load_wait.get()
    return _WAIT_S if value is None else value


def _waited_s(deadline: float) -> float:
    """Seconds of the caller's own load wait already spent (one decimal in refusals)."""
    return load_wait_s() - max(0.0, deadline - time.monotonic())


# ── observability ─────────────────────────────────────────────────────────


def _metric(record: Callable[[], None]) -> None:
    """A failed metric write is a debug line, never an admission failure."""
    try:
        record()
    except Exception as e:
        logger.debug("load_guard: metric write failed: %s", e)


def _record_wait(engine: str, waited_on: str, seconds: float) -> None:
    _metric(
        lambda: _load_guard_wait_seconds.labels(engine=engine, waited_on=waited_on).observe(
            max(0.0, seconds)
        )
    )


def _record_settle(engine: str, seconds: float) -> None:
    _metric(
        lambda: _load_guard_free_settle_seconds.labels(engine=engine).observe(max(0.0, seconds))
    )


def _wait_stage(free_pending: bool) -> str:
    """Name what a capacity wait is about to wait on."""
    return "free_settle" if free_pending else "in_flight"


def _record_admission(engine: str, waited: bool) -> None:
    _metric(
        lambda: _load_guard_admissions_total.labels(
            engine=engine, outcome="admitted_after_wait" if waited else "admitted_immediately"
        ).inc()
    )


def _record_refusal(engine: str, exc: LoadRefusedError) -> None:
    """Bucket a refusal by the reason its raise site recorded."""
    reason = exc.reason

    def record() -> None:
        _load_guard_admissions_total.labels(engine=engine, outcome="refused").inc()
        _load_guard_refusals_total.labels(engine=engine, reason=reason).inc()

    _metric(record)


def _record_unload(engine: str, reason: str) -> None:
    _metric(lambda: _load_guard_unloads_total.labels(engine=engine, reason=reason).inc())


def _record_headroom(available: float) -> None:
    _metric(lambda: _load_guard_headroom_bytes.set(available))


def _record_ceiling(status: dict[str, Any]) -> None:
    _metric(lambda: _load_guard_ceiling_bytes.set(float(status.get("final_ceiling") or 0)))


class LoadRefusedError(Exception):
    """The cold load does not fit host memory within the caller's wait.

    ``reason`` is the low-cardinality refusal bucket the raise site records.
    """

    def __init__(self, message: str, reason: str = "projected-exceeds") -> None:
        super().__init__(message)
        self.reason = reason


#: The pipeline's guard (set by lifespan); None outside the pipeline process.
GUARD: LoadGuard | None = None

#: How long the model a request just failed over FROM stays out of eviction (P-2). On the
#: V2 closeout run an oMLX timeout failed over to an Ollama cold load, load_guard freed the
#: oMLX seat to make room, and every reload of it then got HTTP 507.
FAILOVER_PROTECT_S = float(os.environ.get("LOAD_GUARD_FAILOVER_PROTECT_S", "300"))


def protect_failover(engine: str, model: str) -> None:
    """Keep the model a request just failed over from loaded for a cool-down (P-2)."""
    if GUARD is not None and engine in (OLLAMA, OMLX) and model:
        GUARD.protect(engine, model, failover=True)
        logger.info(
            "load_guard: protecting %s:%s for %.0fs after a failover",
            engine,
            model,
            FAILOVER_PROTECT_S,
        )


def _budget_bytes(status: dict[str, Any]) -> float:
    """The ceiling to budget against: the fixed one when set, else oMLX's live one."""
    return _CEILING if _CEILING > 0 else float(status.get("final_ceiling") or 0)


def _never_fit_budget() -> float | None:
    """The budget a ``never_fit`` claim needs — only a fixed ceiling gives a stable one."""
    return _CEILING - _MARGIN if _CEILING > 0 else None


def _never_fit_basis(never_budget: float | None) -> str:
    if never_budget is not None:
        return "fixed LOAD_GUARD_CEILING_GB"
    return "not asserted: oMLX final_ceiling follows host free memory (P5-OMLX-CEILING-001)"


def _omlx_available(headroom: float) -> float:
    """oMLX headroom a cold load may use: the engine's prefill-safe share, less the margin."""
    budget = headroom * _OMLX_PREFILL_ZONE if _OMLX_PREFILL_ZONE else headroom
    return budget - _MARGIN


def _omlx_prefill_reserve(status: dict[str, Any], used: float) -> float:
    """Room left above the resident models inside oMLX's prefill-safe share; negative means
    the engine has no room to prefill in and aborts whatever it is sent."""
    return _budget_bytes(status) * (_OMLX_PREFILL_ZONE or 1.0) - _MARGIN - used


def _releasable_ollama_bytes(held: list[tuple[str, int, str]], freed: set[str]) -> float:
    """Bytes of busy or active-elsewhere residents that have not already been freed."""
    return float(
        sum(
            size
            for name, size, reason in held
            if name not in freed and reason in ("busy", "active elsewhere")
        )
    )


class _YieldCarry:
    """One Ollama admission's yield state, kept out of ``_admit_ollama``."""

    __slots__ = (
        "free_attempted",
        "last_used",
        "pending_omlx_used",
        "protected_free_attempted",
        "deferred_copy",
        "yield_models",
    )

    def __init__(self) -> None:
        self.free_attempted = False
        self.yield_models: set[str] = set()
        self.pending_omlx_used = 0.0
        self.last_used: float | None = None
        self.protected_free_attempted = False
        self.deferred_copy = False


class _Free:
    """A guard-issued free: its bytes must show as released before a load fits."""

    __slots__ = ("baseline", "size", "started")

    def __init__(self, size: float, baseline: float | None = None) -> None:
        self.baseline = baseline
        self.size = size
        self.started = time.monotonic()


class LoadGuard:
    def __init__(
        self,
        omlx_url: Callable[[], str | None],
        pinned: Callable[[], str] = lambda: os.environ.get("LLM_ROUTER_MODEL", ""),
        client: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(timeout=10.0),
        ollama_url: Callable[[], str | None] = lambda: None,
        counterpart: Callable[[str, str], str | set[str] | None] | None = None,
    ) -> None:
        self._omlx_url = omlx_url
        self._ollama_url = ollama_url
        self._counterpart = counterpart or (lambda _engine, model: model)
        self._protected: dict[tuple[str, str], float] = {}  # (engine, model) -> monotonic deadline
        self._failover_protected: dict[tuple[str, str], float] = {}
        self._pinned = pinned
        self._client = client
        self._lock = asyncio.Lock()
        self._busy: Counter[tuple[str, str]] = Counter()
        self._changed = asyncio.Event()
        self._sizes: dict[tuple[str, str], int] = {}
        self._needs: dict[tuple[str, str], float] = {}
        self._observed: dict[tuple[str, str], int] = {}
        self._last_access: dict[tuple[str, str], float] = {}
        self._host_free_reading: float | None = None
        self._host_free_read_at = 0.0

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("LOAD_GUARD", "1") != "0"

    def _counterpart_models(self, engine: str, model: str) -> set[str]:
        counterpart = self._counterpart(engine, model)
        if isinstance(counterpart, str):
            return {counterpart} if counterpart else set()
        return set(counterpart or ())

    # ── in-flight tracking ────────────────────────────────────────────────

    def begin(self, engine: str, model: str) -> Callable[[], None]:
        """Count one in-flight request; return its idempotent end()."""
        return self._begin_with_activity_lock(engine, model, self._activity_lock(engine, model))

    def has_activity(self) -> bool:
        """Whether any worker is admitting, loading, or serving an inference request."""
        if self._busy or self._lock.locked():
            return True
        paths = [_PROCESS_LOCK_DIR / "admissions.lock", _PROCESS_LOCK_DIR / "cold-load.lock"]
        try:
            paths.extend(_PROCESS_LOCK_DIR.glob("active-*.lock"))
        except OSError:
            return True
        for path in paths:
            handle = self._try_reserve_process_lock(path)
            if handle is None:
                return True
            self._release_activity_lock(handle)
        return False

    @staticmethod
    def _shared_process_lock(name: str) -> Any | None:
        handle = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = (_PROCESS_LOCK_DIR / name).open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            return handle
        except OSError as e:
            if handle is not None:
                handle.close()
            logger.warning("load_guard: could not track %s: %s", name, e)
            return None

    @staticmethod
    def _try_reserve_process_lock(path: Path) -> Any | None:
        handle = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError as e:
            if handle is not None:
                handle.close()
            if not isinstance(e, BlockingIOError):
                logger.warning("load_guard: could not inspect %s: %s", path.name, e)
            return None

    def _begin_with_activity_lock(
        self, engine: str, model: str, activity_lock: Any | None
    ) -> Callable[[], None]:
        key = (engine, model)
        self._last_access[(engine, model_key(model) if engine == OLLAMA else model)] = time.time()
        self._busy[key] += 1
        ended = False

        def end() -> None:
            nonlocal ended
            if ended:
                return
            ended = True
            self._busy[key] -= 1
            if self._busy[key] <= 0:
                del self._busy[key]
            if activity_lock is not None:
                self._release_activity_lock(activity_lock)
            # Wake every waiter, then arm a fresh event for the next change.
            event, self._changed = self._changed, asyncio.Event()
            event.set()

        return end

    @staticmethod
    def _activity_path(engine: str, model: str) -> Path:
        """One file per (engine, model): every worker's in-flight request holds it shared."""
        key = model_key(model) if engine == OLLAMA else model
        digest = hashlib.sha256(f"{engine}\0{key}".encode()).hexdigest()
        return _PROCESS_LOCK_DIR / f"active-{engine}-{digest}.lock"

    def _activity_lock(self, engine: str, model: str) -> Any | None:
        handle = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = self._activity_path(engine, model).open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            return handle
        except OSError as e:
            if handle is not None:
                handle.close()
            logger.warning("load_guard: could not track cross-worker activity: %s", e)
            return None

    def _reserve_activity(self, engine: str, model: str) -> Any | None:
        handle = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = self._activity_path(engine, model).open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if handle is not None:
                handle.close()
            return None
        except OSError as e:
            if handle is not None:
                handle.close()
            logger.warning("load_guard: could not reserve cross-worker activity: %s", e)
            return None

    @staticmethod
    def _release_activity_lock(handle: Any) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

    async def _acquire_activity(self, engine: str, model: str, deadline: float) -> Any:
        handle = None
        started: float | None = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = self._activity_path(engine, model).open("a+")
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    return handle
                except BlockingIOError:
                    _admit_waited.set(True)
                    if started is None:
                        started = time.monotonic()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LoadRefusedError(
                            f"request start for {model} would exceed its wait for a model "
                            f"operation ({_waited_s(deadline):.1f}s)",
                            "deadline",
                        ) from None
                    await asyncio.sleep(min(max(_POLL_S, 0.01), remaining))
        except LoadRefusedError as e:
            if handle is not None:
                handle.close()
            _record_refusal(engine, e)
            raise
        except OSError as e:
            if handle is not None:
                handle.close()
            refusal = LoadRefusedError(
                f"model operation coordination is unavailable for {model}: {e}",
                "coordination-unavailable",
            )
            _record_refusal(engine, refusal)
            raise refusal from None
        except BaseException:
            if handle is not None:
                handle.close()
            raise
        finally:
            if started is not None:
                _record_wait(engine, "model_operation", time.monotonic() - started)

    def _active_elsewhere(self, engine: str, model: str) -> bool:
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            with self._activity_path(engine, model).open("a+") as handle:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return False
        except OSError as e:
            logger.warning("load_guard: could not inspect cross-worker activity: %s", e)
            return True

    def _active_models(self, engine: str) -> int:
        """Models a pipeline worker is serving right now, by held activity locks."""
        try:
            paths = list(_PROCESS_LOCK_DIR.glob(f"active-{engine}-*.lock"))
        except OSError:
            return 0
        held = 0
        for path in paths:
            handle = self._try_reserve_process_lock(path)
            if handle is None:
                held += 1
            else:
                self._release_activity_lock(handle)
        return held

    def active(self, engine: str, model: str) -> bool:
        """Whether any pipeline worker is serving this model right now."""
        return bool(self.busy(engine, model)) or self._active_elsewhere(engine, model)

    def protect(
        self, engine: str, model: str, seconds: float | None = None, *, failover: bool = False
    ) -> None:
        """Order a keeper last or exclude a failed source until its deadline."""
        span = FAILOVER_PROTECT_S if seconds is None else seconds
        protected = self._failover_protected if failover else self._protected
        protected[(engine, model)] = time.monotonic() + span

    def protected(self, engine: str) -> set[str]:
        """Models currently in a keeper or failover protection window."""
        now = time.monotonic()
        return {
            model_key(m) if engine == OLLAMA else m
            for protections in (self._protected, self._failover_protected)
            for (e, m), until in protections.items()
            if e == engine and until > now
        }

    def failover_protected(self, engine: str) -> set[str]:
        now = time.monotonic()
        return {
            model_key(m) if engine == OLLAMA else m
            for (e, m), until in self._failover_protected.items()
            if e == engine and until > now
        }

    def busy(self, engine: str, model: str) -> int:
        if engine != OLLAMA:
            return self._busy.get((engine, model), 0)
        key = model_key(model)
        return sum(
            n for (e, name), n in self._busy.items() if e == engine and model_key(name) == key
        )

    def _omlx_in_flight(self) -> int:
        """oMLX requests in flight across the pipeline's workers, as a lower bound:
        this worker counts requests, a sibling's show up as its held activity locks."""
        local = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        return max(local, self._active_models(OMLX))

    async def _wait_change(self, timeout: float) -> None:
        _admit_waited.set(True)
        event = self._changed
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=max(0.0, timeout))

    # ── engine state ──────────────────────────────────────────────────────

    async def _resident(self, client: httpx.AsyncClient, base: str) -> dict[str, int]:
        models = (await client.get(f"{base}/api/ps")).json().get("models") or []
        return {m["name"]: int(m.get("size") or 0) for m in models}

    async def _need(self, client: httpx.AsyncClient, base: str, model: str) -> float:
        key = (base, model_key(model))
        if key not in self._sizes:
            tags = (await client.get(f"{base}/api/tags")).json().get("models") or []
            for t in tags:
                self._sizes[(base, model_key(str(t["name"])))] = int(t.get("size") or 0)
        if key not in self._needs:
            weights = self._sizes.get(key, 0)
            show: dict[str, Any] = {}
            if weights:
                try:
                    response = await client.post(f"{base}/api/show", json={"model": model})
                    if response.status_code == 200:
                        body = response.json()
                        show = body if isinstance(body, dict) else {}
                except Exception as e:
                    logger.debug("load_guard: /api/show unavailable for %s: %s", model, e)
            self._needs[key] = _estimate_ollama_need(weights, show, model)
        estimate = self._needs[key]
        return max(estimate, float(self._observed.get((OLLAMA, model_key(model)), 0)))

    async def _omlx_status(self, client: httpx.AsyncClient) -> dict[str, Any] | None:
        url = self._omlx_url()
        if not url:
            return None
        try:
            r = await client.get(f"{url.rstrip('/')}/v1/models/status", auth=OmlxKeyAuth())
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            logger.debug("load_guard: oMLX status read failed: %s", type(e).__name__)
            return None

    async def _headroom(self, client: httpx.AsyncClient) -> tuple[float, float] | None:
        """Current oMLX headroom, without waiting for transition state."""
        st = await self._omlx_status(client)
        _ADMIT_OMLX_STATUS.set(st if isinstance(st, dict) else None)
        if st is None:
            return None
        used = float(st.get("current_model_memory") or 0)
        _record_ceiling(st)
        return _budget_bytes(st) - used, used

    async def _omlx_used(self, client: httpx.AsyncClient) -> float | None:
        """oMLX's memory counter: what an unload actually releases."""
        status = await self._omlx_status(client)
        if status is None or status.get("current_model_memory") is None:
            return None
        return float(status["current_model_memory"])

    @staticmethod
    def _track_counter(used: float, last_used: float | None, recheck: bool) -> tuple[float, bool]:
        """Remember the counter and flag a drop since the previous pass."""
        return used, recheck or (last_used is not None and used < last_used)

    def _cached_host_free(self) -> float | None:
        reading = self._host_free_reading
        if reading is None or time.monotonic() - self._host_free_read_at > _HOST_FREE_STALE_S:
            return None
        return reading

    def _remember_host_free(self, reading: float) -> float:
        self._host_free_reading = reading
        self._host_free_read_at = time.monotonic()
        return reading

    async def host_free_bytes(self, base: str) -> float | None:
        """Memory a new load could use without waiting: oMLX's headroom plus idle
        Ollama residents. A failed status read keeps the last reading for
        ``_HOST_FREE_STALE_S``; None after that. Feeds the admission gate."""
        async with self._client() as client:
            st = await self._omlx_status(client)
            if st is None or st.get("final_ceiling") is None:
                return self._cached_host_free()
            headroom = _budget_bytes(st) - float(st.get("current_model_memory") or 0)
            try:
                resident = await self._resident(client, base)
            except Exception:
                resident = {}
            return self._remember_host_free(headroom + self._ollama_idle(resident))

    def _ollama_hold_reason(self, name: str, include_protected: bool = False) -> str | None:
        """Return why an Ollama resident is unavailable for eviction, if anything."""
        key = model_key(name)
        if key == model_key(self._pinned()):
            return "pinned"
        if key in self.failover_protected(OLLAMA):
            return "failover protected"
        if not include_protected and key in self.protected(OLLAMA):
            return "protected"
        if self.busy(OLLAMA, name):
            return "busy"
        if self._active_elsewhere(OLLAMA, name):
            return "active elsewhere"
        return None

    def _ollama_idle(
        self,
        resident: dict[str, int],
        exclude: frozenset[str] | set[str] = frozenset(),
        include_protected: bool = False,
    ) -> float:
        excluded = {model_key(name) for name in exclude}
        return float(
            sum(
                self._ollama_size(name, size)
                for name, size in resident.items()
                if model_key(name) not in excluded
                and self._ollama_hold_reason(name, include_protected) is None
            )
        )

    def _ollama_unfreeable(self, resident: dict[str, int]) -> list[tuple[str, int, str]]:
        """Residents that hold bytes and are not idle: (name, bytes, reason)."""
        held: list[tuple[str, int, str]] = []
        for name, size in resident.items():
            nbytes = self._ollama_size(name, size)
            if nbytes <= 0:
                continue
            reason = self._ollama_hold_reason(name)
            if reason is not None:
                held.append((name, nbytes, reason))
        return held

    def _ollama_size(self, name: str, size: int) -> int:
        return max(size, self._observed.get((OLLAMA, model_key(name)), 0))

    def _ollama_available(self, headroom: float, resident: dict[str, int], idle: float) -> float:
        if _CEILING > 0:
            headroom -= sum(self._ollama_size(name, size) for name, size in resident.items())
        return headroom + idle

    async def _omlx_idle_models(
        self, client: httpx.AsyncClient, exclude: frozenset[str] | set[str] = frozenset()
    ) -> tuple[str, list[dict[str, Any]]]:
        """Return idle oMLX residents, LRU first, keeper last, failover sources excluded."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return "", []
        response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
        if response.status_code != 200:
            logger.warning(
                "load_guard: oMLX status returned HTTP %d; not freeing oMLX memory",
                response.status_code,
            )
            return url, []
        st = response.json()
        served = int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0)
        if served > self._omlx_in_flight():
            logger.info("load_guard: oMLX serves requests the pipeline did not send; not freeing")
            return url, []
        login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
        if login.status_code != 200:
            return url, []
        response = await client.get(f"{url}/admin/api/models")
        if response.status_code != 200:
            logger.warning(
                "load_guard: oMLX model list returned HTTP %d; not freeing oMLX memory",
                response.status_code,
            )
            return url, []
        models = response.json()
        models = models.get("models", models) if isinstance(models, dict) else models
        protected = self.protected(OMLX)
        failover_protected = self.failover_protected(OMLX)
        idle = [
            m
            for m in models
            if m.get("loaded")
            and not m.get("pinned")
            and not m.get("is_loading")
            and m["id"] not in exclude
            and m["id"] not in failover_protected
            and not self.busy(OMLX, m["id"])
            and not self._active_elsewhere(OMLX, m["id"])
        ]
        return url, sorted(
            idle, key=lambda m: (m["id"] in protected, float(m.get("last_access") or 0))
        )

    @staticmethod
    def _has_loading(value: Any) -> bool:
        if isinstance(value, (int, float)):
            return value > 0
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "none"}
        return bool(value)

    @staticmethod
    def _loading_among(models: Any, protected: set[str]) -> bool:
        """Whether any reported model is loading and within reach of eviction."""
        return any(
            isinstance(m, dict) and m.get("is_loading") and m.get("id") not in protected
            for m in models or []
        )

    async def _omlx_loading(self, client: httpx.AsyncClient) -> bool:
        """Whether oMLX reports a load; a protected model's load is never acted on."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return False
        protected = self.protected(OMLX)
        status_loading = False
        try:
            status = await self._omlx_status(client)
            if status is None:
                return False
            status_loading = self._loading_among(status.get("models"), protected)
            response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
            if response.status_code != 200:
                return status_loading
            runtime = response.json()
            if not isinstance(runtime, dict):
                return status_loading
        except Exception:
            return status_loading
        runtime_loading = self._has_loading(runtime.get("models_loading"))
        if status_loading == runtime_loading:
            return status_loading
        try:
            login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
            if login.status_code != 200:
                return status_loading
            response = await client.get(f"{url}/admin/api/models")
            if response.status_code != 200:
                return status_loading
            models = response.json()
            models = models.get("models", models) if isinstance(models, dict) else models
            return self._loading_among(models, protected)
        except Exception:
            return status_loading

    async def _omlx_foreign_active(self, client: httpx.AsyncClient) -> bool:
        """Whether oMLX serves requests the pipeline is not tracking."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return False
        try:
            response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
            if response.status_code != 200:
                return False
            st = response.json()
            if not isinstance(st, dict):
                return False
        except Exception:
            return False
        tracked = self._omlx_in_flight()
        return int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked

    async def _free_omlx(
        self,
        client: httpx.AsyncClient,
        want: float,
        used: float,
        exclude: frozenset[str] | set[str] = frozenset(),
        last_models: set[str] | None = None,
    ) -> tuple[float, dict[str, _Free], float | None, float, list[dict[str, str]]]:
        """Unload idle oMLX models; report the drop, pendings (202s and 200s whose
        release has not reached the counter), post state, 200 bytes."""
        try:
            url, idle = await self._omlx_idle_models(client, exclude)
            protected = self.protected(OMLX)
            last_models = last_models or set()
            idle.sort(
                key=lambda m: (
                    str(m["id"]) in last_models,
                    str(m["id"]) in protected,
                    float(m.get("last_access") or 0),
                )
            )
            queued: dict[str, _Free] = {}
            unloads: list[dict[str, str]] = []
            unloaded: list[tuple[str, float]] = []  # 200s in post order
            posted = 0.0
            covered = 0.0  # accepted bytes: any accepted unload can cover the shortage
            any_post = False
            for m in idle:
                if covered >= want:
                    break
                r = await client.post(f"{url}/admin/api/models/{quote(m['id'], safe='')}/unload")
                any_post = True
                size = float(m.get("estimated_size") or m.get("actual_size") or 0)
                reason = (
                    "requested seat copy"
                    if str(m["id"]) in last_models
                    else "preferred resident"
                    if str(m["id"]) in protected
                    else "idle LRU"
                )
                if r.status_code == 200:
                    posted += size
                    covered += size
                    unloaded.append((str(m["id"]), size))
                    unloads.append({"engine": OMLX, "model": str(m["id"]), "status": "unloaded"})
                    _record_unload(OMLX, "idle_omlx")
                elif r.is_success:  # 202 and any other accepted unload: bytes land later
                    queued[m["id"]] = _Free(size)
                    covered += size
                    unloads.append({"engine": OMLX, "model": str(m["id"]), "status": "queued"})
                    _record_unload(OMLX, "queued_202")
                else:
                    logger.warning(
                        "load_guard: unload of idle oMLX model %s returned HTTP %d",
                        m["id"],
                        r.status_code,
                    )
                    unloads.append({"engine": OMLX, "model": str(m["id"]), "status": "failed"})
                    continue
                logger.info(
                    "load_guard: evicted %s on %s, %.1f GiB freed (reason=%s)",
                    m["id"],
                    OMLX,
                    size / _GIB,
                    reason,
                )
            if not any_post:
                return 0.0, queued, None, 0.0, unloads
            after = await self._omlx_used(client)
            freed = 0.0 if after is None else max(0.0, used - after)
            # A 200 whose release has not reached the counter stays pending like a 202.
            unsettled = posted - min(posted, freed)
            for name, size in reversed(unloaded):
                if unsettled <= 0:
                    break
                queued[name] = _Free(size)
                unsettled -= size
            return freed, queued, after, posted, unloads
        except Exception as e:
            logger.warning("load_guard: could not free oMLX memory: %s", e)
            return 0.0, {}, None, 0.0, []

    async def _free_ollama(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        include_protected: bool = False,
        last_models: set[str] | None = None,
        want: float | None = None,
    ) -> dict[str, _Free]:
        """Request accepted unloads and retain their pre-unload headroom records."""
        idle = [
            n
            for n, size in resident.items()
            if size and self._ollama_idle({n: size}, include_protected=include_protected) > 0
        ]
        protected = self.protected(OLLAMA)
        last_keys = {model_key(name) for name in (last_models or set())}
        idle.sort(
            key=lambda name: (
                model_key(name) in last_keys,
                model_key(name) in protected,
                self._last_access.get((OLLAMA, model_key(name)), 0.0),
            )
        )
        requested: dict[str, _Free] = {}
        covered = 0.0
        for name in idle:
            if want is not None and covered >= want:
                break
            operation_lock = self._reserve_activity(OLLAMA, name)
            if operation_lock is None:
                continue
            try:
                status = await self._omlx_status(client)
                baseline = (
                    None
                    if status is None
                    else _budget_bytes(status) - float(status.get("current_model_memory") or 0)
                )
                response = await client.post(
                    f"{base}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30.0
                )
            except Exception as e:
                logger.warning("load_guard: could not unload idle Ollama model %s: %s", name, e)
                continue
            finally:
                self._release_activity_lock(operation_lock)
            if not response.is_success:
                logger.warning(
                    "load_guard: unload of idle Ollama model %s returned HTTP %d",
                    name,
                    response.status_code,
                )
                continue
            requested[name] = _Free(float(self._ollama_size(name, resident[name])), baseline)
            covered += requested[name].size
            _record_unload(OLLAMA, "idle_ollama")
            reason = (
                "requested seat copy"
                if model_key(name) in last_keys
                else "protected idle"
                if model_key(name) in protected
                else "idle LRU"
            )
            logger.info(
                "load_guard: evicted %s on %s, %.1f GiB freed (reason=%s)",
                name,
                OLLAMA,
                requested[name].size / _GIB,
                reason,
            )
        return requested

    @staticmethod
    def _ollama_refusal(
        model: str,
        need: float,
        available: float,
        headroom: float,
        idle: float,
        quiet: bool,
        waited: float,
    ) -> LoadRefusedError:
        detail = (
            f"after waiting {waited:.1f}s" if not quiet else "with nothing in flight to wait for"
        )
        return LoadRefusedError(
            f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
            f"exceed host headroom {available / _GIB:.1f} GiB (oMLX headroom "
            f"{headroom / _GIB:.1f} + idle Ollama {idle / _GIB:.1f} - margin "
            f"{_MARGIN / _GIB:.0f}) {detail}",
            "quiet" if quiet else "projected-exceeds",
        )

    async def _wait_if_omlx_loading(
        self,
        client: httpx.AsyncClient,
        model: str,
        deadline: float,
        release: _Release,
        held: list[_Release],
    ) -> tuple[_Release, bool, float]:
        release()
        saw_loading = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 and not saw_loading:
                    break
                try:
                    loading = await asyncio.wait_for(
                        self._omlx_loading(client),
                        timeout=(
                            min(max(_POLL_S, 0.01), remaining)
                            if remaining > 0
                            else max(_POLL_S, 0.01)
                        ),
                    )
                except TimeoutError:
                    if saw_loading:
                        deadline = max(deadline, time.monotonic() + load_wait_s())
                        continue
                    break
                if not loading:
                    break
                if not saw_loading:
                    logger.info(
                        "load_guard: %s engine transition active; waiting while it progresses",
                        model,
                    )
                saw_loading = True
                deadline = max(deadline, time.monotonic() + load_wait_s())
                remaining = deadline - time.monotonic()
                started = time.monotonic()
                await self._wait_change(min(_POLL_S, remaining))
                _record_wait(OLLAMA, "engine_transition", time.monotonic() - started)
            release = await self._acquire(OLLAMA, deadline, model)
            held.append(release)
            return release, saw_loading, deadline
        except BaseException:
            release()
            raise

    async def _wait_if_ollama_capacity_may_change(
        self,
        client: httpx.AsyncClient,
        model: str,
        deadline: float,
        release: _Release,
        held: list[_Release],
        need: float,
        available: float,
        headroom: float,
        idle: float,
        used: float,
        activity_seen: bool,
        pending_change: bool,
        pending_free_names: list[str],
    ) -> tuple[_Release, bool, float]:
        remaining = deadline - time.monotonic()
        release()
        foreign_active = False
        probe_timed_out = False
        if remaining > 0:
            try:
                foreign_active = await asyncio.wait_for(
                    self._omlx_foreign_active(client),
                    timeout=min(max(_POLL_S, 0.01), remaining),
                )
            except TimeoutError:
                probe_timed_out = True
        changing = bool(self._busy) or foreign_active
        activity_seen, deadline = self._record_activity_progress(changing, activity_seen, deadline)
        resumed = await self._resume_after_activity_drains(
            changing, activity_seen, probe_timed_out, deadline, model, held
        )
        if resumed is not None:
            return resumed
        quiet = not (activity_seen or pending_change)
        remaining = deadline - time.monotonic()
        if quiet and remaining > 0:
            try:
                now = await asyncio.wait_for(self._omlx_used(client), timeout=remaining)
            except TimeoutError:
                now = None
            quiet = now is None or now >= used
            remaining = deadline - time.monotonic()
        if remaining <= 0 or quiet:
            if pending_free_names:
                raise self._free_settle_refusal(
                    model, pending_free_names, need, available, _waited_s(deadline)
                )
            raise self._ollama_refusal(
                model, need, available, headroom, idle, quiet, waited=_waited_s(deadline)
            )
        logger.info(
            "load_guard: %s needs %.1f GiB, %.1f available; waiting for engine activity",
            model,
            need / _GIB,
            available / _GIB,
        )
        started = time.monotonic()
        await self._wait_change(min(5.0, remaining, max(_POLL_S, 0.01)))
        _record_wait(OLLAMA, _wait_stage(pending_change), time.monotonic() - started)
        release = await self._acquire(OLLAMA, deadline, model)
        held.append(release)
        return release, activity_seen, deadline

    @staticmethod
    def _record_activity_progress(
        changing: bool, activity_seen: bool, deadline: float
    ) -> tuple[bool, float]:
        """Keep a progressing activity's admission budget alive until it drains."""
        if changing:
            return True, max(deadline, time.monotonic() + load_wait_s())
        return activity_seen, deadline

    async def _resume_after_activity_drains(
        self,
        changing: bool,
        activity_seen: bool,
        probe_timed_out: bool,
        deadline: float,
        model: str,
        held: list[_Release],
    ) -> tuple[_Release, bool, float] | None:
        """Reacquire and remeasure as soon as the activity holding capacity ends."""
        if changing or not activity_seen or probe_timed_out:
            return None
        release = await self._acquire(OLLAMA, deadline, model)
        held.append(release)
        return release, False, deadline

    async def _free_idle_memory(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        shortage: float,
        model: str = "",
        need: float | None = None,
    ) -> tuple[
        bool,
        dict[str, _Free],
        dict[str, _Free],
        float | None,
        float,
        list[dict[str, str]],
        bool,
    ]:
        seat_copies = self._counterpart_models(OLLAMA, model) if model else set()
        try:
            _, omlx_idle = await self._omlx_idle_models(client)
        except Exception as e:
            logger.warning("load_guard: could not list oMLX residents before eviction: %s", e)
            omlx_idle = []
        other_omlx = {str(entry["id"]) for entry in omlx_idle} - seat_copies
        omlx_freed, omlx_queued, after, synchronous, unloads = await self._free_omlx(
            client,
            shortage,
            used,
            exclude=seat_copies,
        )
        covered = omlx_freed + sum(free.size for free in omlx_queued.values())
        ollama_requested: dict[str, _Free] = {}
        if covered < shortage and idle:
            ollama_requested = await self._free_ollama(
                client,
                base,
                resident,
                last_models={model} if model else None,
                want=shortage - covered,
            )
        covered += sum(free.size for free in ollama_requested.values())
        deferred_copy = bool(seat_copies and need is not None and (omlx_queued or ollama_requested))
        if covered < shortage and seat_copies and need is not None and not deferred_copy:
            capacity = await self._headroom(client)
            if capacity is not None:
                headroom, used_after = capacity
                resident_after = await self._resident(client, base)
                idle_after = self._ollama_idle(resident_after)
                available_after = (
                    self._ollama_available(headroom, resident_after, idle_after) - _MARGIN
                )
                remaining = max(0.0, need - available_after)
                if remaining:
                    (
                        last_freed,
                        last_queued,
                        last_after,
                        last_sync,
                        last_unloads,
                    ) = await self._free_omlx(
                        client,
                        remaining,
                        used_after,
                        exclude=other_omlx,
                        last_models=seat_copies,
                    )
                    omlx_freed += last_freed
                    omlx_queued.update(last_queued)
                    if last_after is not None:
                        after = last_after
                    synchronous += last_sync
                    unloads.extend(last_unloads)
        unloads.extend(
            {"engine": OLLAMA, "model": name, "status": "requested"} for name in ollama_requested
        )
        did_free = bool(omlx_freed or omlx_queued or ollama_requested)
        return did_free, omlx_queued, ollama_requested, after, synchronous, unloads, deferred_copy

    async def _arm_parallel_yield(self, client: httpx.AsyncClient, shortage: float) -> set[str]:
        """Hold new work on busy parallel seats whose bytes cover ``shortage``."""
        from portal.platform.inference.router.parallel_seat import YIELD, seat_for_loaded_model

        status = _ADMIT_OMLX_STATUS.get()
        if status is None:
            status = await self._omlx_status(client)
        held: set[str] = set()
        if not status or shortage <= 0:
            return held
        for entry in status.get("models") or []:
            if not isinstance(entry, dict) or not entry.get("loaded"):
                continue
            model_id = str(entry.get("id") or "")
            seat = seat_for_loaded_model(model_id)
            size = float(entry.get("estimated_size") or 0)
            if seat is None or size < shortage:
                continue
            if not self.busy(OMLX, model_id) and not self._active_elsewhere(OMLX, model_id):
                continue
            YIELD.hold(seat)
            held.add(model_id)
            logger.info(
                "load_guard: chat load yields parallel seat %s (%s, %.1f GiB)",
                seat,
                model_id,
                size / _GIB,
            )
        return held

    def _parallel_yield_drained(self, models: set[str]) -> bool:
        return bool(models) and not any(
            self.busy(OMLX, model) or self._active_elsewhere(OMLX, model) for model in models
        )

    async def _free_or_yield_parallel(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        need: float,
        available: float,
        carry: _YieldCarry,
        pending_omlx: dict[str, _Free],
        pending_ollama: dict[str, _Free],
        model: str = "",
    ) -> bool:
        """Unload idle memory, or hold a busy parallel seat until it can be unloaded.

        A chat load that does not fit beside a busy parallel seat (measured
        2026-11-12: 29.8 GiB needed, 18.6 available beside the hunt) must not be
        refused while that seat keeps accepting work. New parallel requests wait;
        once the seat is idle the existing unload path frees it.
        """
        if need > available and not carry.yield_models:
            carry.yield_models = await self._arm_parallel_yield(client, need - available)
            if carry.yield_models and not _ADMIT_YIELD_PIN.get():
                from portal.platform.inference.router.parallel_seat import YIELD

                YIELD.pin()
                _ADMIT_YIELD_PIN.set(True)
        if (
            need > available
            and carry.free_attempted
            and self._parallel_yield_drained(carry.yield_models)
        ):
            carry.free_attempted = False
        if need <= available or carry.free_attempted:
            return False
        carry.free_attempted = True
        did, baseline, post, deferred_copy = await self._free_for_load(
            client,
            base,
            resident,
            idle,
            used,
            need - available,
            pending_omlx,
            pending_ollama,
            model,
            need,
        )
        carry.pending_omlx_used = baseline
        carry.last_used = post
        carry.deferred_copy = deferred_copy
        return did

    async def _free_for_load(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        shortage: float,
        pending_omlx: dict[str, _Free],
        pending_ollama: dict[str, _Free],
        model: str = "",
        need: float = 0.0,
    ) -> tuple[bool, float, float, bool]:
        """Free idle memory and fold it in; return the queued baseline and post counter."""
        (
            did_free,
            queued,
            requested,
            after,
            synchronous,
            _,
            deferred_copy,
        ) = await self._free_idle_memory(client, base, resident, idle, used, shortage, model, need)
        pending_omlx.update(queued)
        pending_ollama.update(requested)
        post = used if after is None else after
        return did_free, self._pending_baseline(used, after, synchronous), post, deferred_copy

    @staticmethod
    def _retire_ollama_frees(
        pending: dict[str, _Free], resident: dict[str, int], headroom: float
    ) -> tuple[dict[str, _Free], list[tuple[str, float]]]:
        """Retire a free once /api/ps drops it and headroom covers its bytes."""
        now = time.monotonic()
        remaining: dict[str, _Free] = {}
        settled: list[tuple[str, float]] = []
        for name, free in pending.items():
            if free.baseline is None:
                free.baseline = headroom
            baseline = free.baseline
            landed = name not in resident and (_CEILING > 0 or headroom >= baseline + free.size)
            if landed:
                settled.append((name, now - free.started))
            else:
                remaining[name] = free
        return remaining, settled

    def _settle_ollama_frees(
        self,
        model: str,
        need: float,
        available: float,
        resident: dict[str, int],
        headroom: float,
        pending: dict[str, _Free],
        deadline: float,
    ) -> dict[str, _Free]:
        """Record and log landed frees, warn past the expected settle, refuse only at the wait."""
        pending, settled = self._retire_ollama_frees(pending, resident, headroom)
        for name, elapsed in settled:
            _record_settle(OLLAMA, elapsed)
            if elapsed >= _FREE_SETTLE_EXPECTED_S:
                logger.warning(
                    "load_guard: free of %s settled in %.1fs (expected %.1fs)",
                    name,
                    elapsed,
                    _FREE_SETTLE_EXPECTED_S,
                )
            else:
                logger.info("load_guard: free of %s settled in %.1fs", name, elapsed)
        if pending and need > available and time.monotonic() >= deadline:
            raise self._free_settle_refusal(
                model, list(pending), need, available, _waited_s(deadline)
            )
        return pending

    @staticmethod
    def _free_settle_refusal(
        model: str, names: list[str], need: float, available: float, waited: float
    ) -> LoadRefusedError:
        freed = ", ".join(sorted(names))
        message = (
            f"Cannot load {model}: free of {freed} did not settle within "
            f"the {waited:.1f}s load wait (projected {need / _GIB:.1f} GiB, host "
            f"headroom {available / _GIB:.1f} GiB)"
        )
        logger.warning("load_guard: %s", message)
        return LoadRefusedError(message, "free-settle")

    @staticmethod
    def _pending_baseline(used: float, after: float | None, synchronous: float) -> float:
        """Counter the queued drops are measured from: the pre-pass value less 200 bytes."""
        if after is None:
            return used
        return used - min(synchronous, max(0.0, used - after))

    async def _pending_omlx_unloads(
        self, client: httpx.AsyncClient, models: dict[str, _Free], used: float
    ) -> tuple[dict[str, _Free], bool, float]:
        """Retire queued unloads the counter drop covers, in post order."""
        if not models:
            return {}, False, used
        now_used = await self._omlx_used(client)
        if now_used is None or now_used >= used:
            return models, False, used
        drop = used - now_used
        remaining = dict(models)
        for name, free in models.items():
            if free.size > drop:
                break
            drop -= free.size
            used -= free.size
            del remaining[name]
            _record_settle(OMLX, time.monotonic() - free.started)
        return remaining, len(remaining) < len(models), used

    # ── the cold-load lock ───────────────────────────────────────────────

    async def _acquire(self, engine: str, deadline: float, what: str) -> _Release:
        # Uncontended: take it now. wait_for with a zero timeout refuses even a
        # free lock, which would turn X-Portal-Load-Wait: 0 into "always refuse".
        if self._lock.locked():
            _admit_waited.set(True)
            started = time.monotonic()
            try:
                await asyncio.wait_for(
                    self._lock.acquire(), timeout=max(0.0, deadline - time.monotonic())
                )
            except TimeoutError:
                raise LoadRefusedError(
                    f"cold load of {what} would exceed its wait for another model load "
                    f"({_waited_s(deadline):.1f}s)",
                    "deadline",
                ) from None
            finally:
                _record_wait(engine, "in_flight", time.monotonic() - started)
        else:
            await self._lock.acquire()
        try:
            process_lock = await self._acquire_process_lock(engine, deadline, what)
        except BaseException:
            self._lock.release()
            raise
        return _Release(self._lock, process_lock)

    @staticmethod
    async def _acquire_process_lock(engine: str, deadline: float, what: str) -> Any:
        process_lock = None
        process_wait_started = None
        try:
            _PROCESS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            lock_path = _PROCESS_LOCK_DIR / "cold-load.lock"
            process_lock = lock_path.open("a+")
            while True:
                try:
                    fcntl.flock(process_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    _admit_waited.set(True)
                    if process_wait_started is None:
                        process_wait_started = time.monotonic()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        logger.warning(
                            "load_guard: process cold-load lock %s remained held for %.1fs; "
                            "refusing %s",
                            lock_path,
                            time.monotonic() - process_wait_started,
                            what,
                        )
                        raise LoadRefusedError(
                            f"cold load of {what} would exceed its wait for another model load "
                            f"({_waited_s(deadline):.1f}s)",
                            "deadline",
                        ) from None
                    await asyncio.sleep(min(max(_POLL_S, 0.01), remaining))
            return process_lock
        except OSError as e:
            if process_lock is not None:
                process_lock.close()
            raise LoadRefusedError(
                f"cold-load coordination is unavailable for {what}: {e}",
                "coordination-unavailable",
            ) from None
        except BaseException:
            if process_lock is not None:
                process_lock.close()
            raise
        finally:
            if process_wait_started is not None:
                _record_wait(engine, "in_flight", time.monotonic() - process_wait_started)

    async def _release_when_resident(
        self, engine: str, base: str, model: str, release: _Release
    ) -> None:
        """Release the lock once the model is resident; record its real footprint.
        Stops early when the request's own end already released it."""
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        try:
            async with self._client() as client:
                while time.monotonic() < deadline and not release.released:
                    try:
                        if engine == OLLAMA:
                            resident = await self._resident(client, base)
                            size = lookup_model(resident, model)
                            if size is not None:
                                key = (OLLAMA, model_key(model))
                                self._observed[key] = max(size, self._observed.get(key, 0))
                                return
                        else:
                            st = await self._omlx_status(client)
                            entry = _omlx_entry(st, model)
                            if entry is None or (
                                entry.get("loaded") and not entry.get("is_loading")
                            ):
                                return
                    except Exception:
                        pass
                    await asyncio.sleep(_POLL_S)
        finally:
            release()

    # ── admission ─────────────────────────────────────────────────────────

    async def admit(self, base: str, model: str) -> Callable[[], None] | None:
        """Admit an Ollama request. Return the lock's release callable when this is
        a cold load (also released automatically once the model is resident), None
        when no lock is needed. Raises LoadRefusedError."""
        if not self.enabled() or not model:
            return None
        deadline = time.monotonic() + load_wait_s()
        _admit_waited.set(False)
        held: list[_Release] = []
        activity = self._shared_process_lock("admissions.lock")
        try:
            release, defer_yield = await self._admit_ollama_yielding(base, model, deadline, held)
        finally:
            if activity is not None:
                self._release_activity_lock(activity)
        if release is None:
            return None
        _record_admission(OLLAMA, _admit_waited.get())
        done = (
            self._release_resident_and_yield(OLLAMA, base, model, release)
            if defer_yield
            else self._release_when_resident(OLLAMA, base, model, release)
        )
        asyncio.get_running_loop().create_task(done)
        return release

    async def _admit_ollama_yielding(
        self, base: str, model: str, deadline: float, held: list[_Release]
    ) -> tuple[_Release | None, bool]:
        """Admit, and say whether a parallel-seat pin waits until the model is resident."""
        from portal.platform.inference.router.parallel_seat import YIELD

        token = _ADMIT_YIELD_PIN.set(False)
        release: _Release | None = None
        defer = False
        try:
            try:
                release = await self._admit_ollama(base, model, deadline, held)
            except LoadRefusedError as e:
                for r in held:
                    r()
                _record_refusal(OLLAMA, e)
                raise
            except BaseException:
                for r in held:
                    r()
                raise
            defer = _ADMIT_YIELD_PIN.get() and release is not None
            return release, defer
        finally:
            pinned = _ADMIT_YIELD_PIN.get()
            _ADMIT_YIELD_PIN.reset(token)
            if pinned and not defer:
                YIELD.release()

    async def _release_resident_and_yield(
        self, engine: str, base: str, model: str, release: _Release
    ) -> None:
        """Release the cold-load lock once resident, then the parallel-seat pin."""
        from portal.platform.inference.router.parallel_seat import YIELD

        try:
            await self._release_when_resident(engine, base, model, release)
        finally:
            YIELD.release()

    async def admit_and_begin_ollama(
        self, base: str, model: str
    ) -> tuple[Callable[[], None] | None, Callable[[], None]]:
        """Admit then lease the model through request completion across workers."""
        if not self.enabled() or not model:
            return None, self.begin(OLLAMA, model)
        admission = self._shared_process_lock("admissions.lock")
        release: Callable[[], None] | None = None
        activity_lock = None
        try:
            release = await self.admit(base, model)
            while True:
                activity_lock = await self._acquire_activity(
                    OLLAMA, model, time.monotonic() + load_wait_s()
                )
                if release is not None:
                    end = self._begin_with_activity_lock(OLLAMA, model, activity_lock)
                    activity_lock = None
                    return release, end
                try:
                    async with self._client() as client:
                        resident = await self._resident(client, base)
                except Exception as e:
                    logger.warning(
                        "load_guard: could not recheck Ollama residency for %s; admitting: %s",
                        model,
                        e,
                    )
                    end = self._begin_with_activity_lock(OLLAMA, model, activity_lock)
                    activity_lock = None
                    return release, end
                if lookup_model(resident, model) is not None:
                    end = self._begin_with_activity_lock(OLLAMA, model, activity_lock)
                    activity_lock = None
                    return release, end
                self._release_activity_lock(activity_lock)
                activity_lock = None
                release = await self.admit(base, model)
        except BaseException:
            if activity_lock is not None:
                self._release_activity_lock(activity_lock)
            if release is not None:
                release()
            raise
        finally:
            if admission is not None:
                self._release_activity_lock(admission)

    async def admit_and_begin_omlx(
        self, model: str
    ) -> tuple[Callable[[], None] | None, Callable[[], None]]:
        """Keep admission visible until the oMLX request lease is installed."""
        if not self.enabled() or not model:
            return None, self.begin(OMLX, model)
        admission = self._shared_process_lock("admissions.lock")
        release: Callable[[], None] | None = None
        try:
            release = await self.admit_omlx(model)
            end = self.begin(OMLX, model)
            return release, end
        except BaseException:
            if release is not None:
                release()
            raise
        finally:
            if admission is not None:
                self._release_activity_lock(admission)

    async def _yield_protected_idle(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        need: float,
        available: float,
        pending: dict[str, _Free],
        carry: _YieldCarry | None = None,
        last_models: set[str] | None = None,
    ) -> list[str]:
        """Last resort before refusal: idle protected residents yield, but only when
        their bytes can cover the gap — protection is spent only when it buys the
        admission, and never on a model that is busy or active elsewhere. Returns
        the names attempted (empty when the gate does not pass)."""
        if carry is not None and carry.protected_free_attempted:
            return []
        names = [
            n
            for n, s in resident.items()
            if s > 0
            and self._ollama_hold_reason(n) == "protected"
            and self._ollama_hold_reason(n, include_protected=True) is None
        ]
        last_keys = {model_key(name) for name in (last_models or set())}
        names.sort(key=lambda name: model_key(name) in last_keys)
        held = sum(self._ollama_size(n, resident[n]) for n in names)
        if not names or available + held < need:
            return []
        if carry is not None:
            carry.protected_free_attempted = True
        remaining = max(0.0, need - available)
        attempted = []
        for name in names:
            requested = await self._free_ollama(
                client,
                base,
                {name: resident[name]},
                include_protected=True,
                last_models=last_models,
                want=remaining,
            )
            attempted.append(name)
            pending.update(requested)
            remaining -= sum(free.size for free in requested.values())
            if remaining <= 0:
                break
        return attempted

    async def _admit_ollama(
        self, base: str, model: str, deadline: float, held: list[_Release]
    ) -> _Release | None:
        async with self._client() as client:
            try:
                if lookup_model(await self._resident(client, base), model) is not None:
                    return None
            except Exception:
                return None  # cannot see Ollama's state: fail open
            release = await self._acquire(OLLAMA, deadline, model)
            held.append(release)
            try:
                return await self._admit_ollama_locked(client, base, model, deadline, held, release)
            except LoadRefusedError:
                release()
                raise
            except Exception as e:
                logger.warning("load_guard: measurement failed for %s, admitting: %s", model, e)
                return next((r for r in reversed(held) if not r.released), release)

    async def _admit_ollama_locked(
        self,
        client: httpx.AsyncClient,
        base: str,
        model: str,
        deadline: float,
        held: list[_Release],
        release: _Release,
    ) -> _Release | None:
        """Measure capacity and advance one Ollama cold-load admission."""
        activity_seen = False
        pending_omlx: dict[str, _Free] = {}
        pending_ollama: dict[str, _Free] = {}
        carry = _YieldCarry()
        recheck = False
        while True:
            resident = await self._resident(client, base)
            if lookup_model(resident, model) is not None:
                release()
                return None
            need = await self._need(client, base, model)
            capacity = await self._headroom(client)
            if capacity is None or not need:
                break  # unmeasurable: fail open
            headroom, used = capacity
            carry.last_used, recheck = self._track_counter(used, carry.last_used, recheck)
            idle = self._ollama_idle(resident)
            available = self._ollama_available(headroom, resident, idle) - _MARGIN
            _record_headroom(available)
            if await self._free_or_yield_parallel(
                client,
                base,
                resident,
                idle,
                used,
                need,
                available,
                carry,
                pending_omlx,
                pending_ollama,
                model,
            ):
                continue
            pending_omlx, settled, carry.pending_omlx_used = await self._pending_omlx_unloads(
                client, pending_omlx, carry.pending_omlx_used
            )
            if settled:
                recheck = False
                continue
            pending_ollama = self._settle_ollama_frees(
                model, need, available, resident, headroom, pending_ollama, deadline
            )
            if carry.deferred_copy and not pending_omlx and not pending_ollama:
                carry.free_attempted = False
                carry.deferred_copy = False
            if need <= available:
                break
            release, loading_seen, deadline = await self._wait_if_omlx_loading(
                client, model, deadline, release, held
            )
            if loading_seen:
                continue
            if not (pending_omlx or pending_ollama) and await self._yield_protected_idle(
                client, base, resident, need, available, pending_ollama, carry, {model}
            ):
                continue
            release, activity_seen, deadline = await self._wait_if_ollama_capacity_may_change(
                client,
                model,
                deadline,
                release,
                held,
                need,
                available,
                headroom,
                idle,
                used,
                activity_seen,
                bool(pending_omlx or pending_ollama or recheck),
                list(pending_omlx) + list(pending_ollama),
            )
            recheck = False
        return release

    async def _wait_for_ollama_release(self, deadline: float, models: list[str]) -> bool:
        """Wait while named Ollama residents are serving work that can free memory."""
        if not models:
            return False
        logger.info("load_guard: waiting for active Ollama model(s) to release: %s", models)
        while any(
            self.busy(OLLAMA, model) or self._active_elsewhere(OLLAMA, model) for model in models
        ):
            deadline = max(deadline, time.monotonic() + load_wait_s())
            remaining = deadline - time.monotonic()
            _admit_waited.set(True)
            started = time.monotonic()
            await self._wait_change(min(remaining, max(_POLL_S, 0.01)))
            _record_wait(OMLX, "in_flight", time.monotonic() - started)
        return True

    def _omlx_ollama_blockers(
        self,
        resident: dict[str, int],
        failed: set[str],
        pending: dict[str, _Free],
    ) -> list[tuple[str, int, str]]:
        """Bytes Ollama still holds against this load: residents and unsettled frees, with why."""
        blockers: list[tuple[str, int, str]] = []
        named: set[str] = set()
        for name, size in resident.items():
            nbytes = self._ollama_size(name, size)
            if nbytes <= 0:
                continue
            reason = self._ollama_hold_reason(name, include_protected=True)
            if reason is None and name in failed:
                reason = "unload failed"
            elif reason is None and name in pending:
                reason = "unload unsettled"
            if reason is not None:
                blockers.append((name, nbytes, reason))
                named.add(model_key(name))
        for name, free in pending.items():
            if model_key(name) not in named:
                blockers.append((name, int(free.size), "unload unsettled"))
        return blockers

    def _refuse_blocked_omlx(
        self,
        model: str,
        need: float,
        available: float,
        held: list[tuple[str, int, str]],
        deadline: float,
        omlx_held: list[tuple[str, int, str]] | None = None,
    ) -> NoReturn:
        """Refuse an oMLX cold load, naming every resident that could not be freed."""
        waited = _waited_s(deadline)
        blockers = held + list(omlx_held or [])
        if not blockers:
            raise LoadRefusedError(
                f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
                f"exceed host headroom {available / _GIB:.1f} GiB",
                "projected-exceeds",
            )
        blocked = ", ".join(
            f"{name} ({size / _GIB:.1f} GiB, {reason})" for name, size, reason in blockers
        )
        message = (
            f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
            f"exceed host headroom {available / _GIB:.1f} GiB; blocked by {blocked}; "
            f"need {need / _GIB:.1f} GiB, available {available / _GIB:.1f} GiB, "
            f"waited {waited:.1f}s"
        )
        logger.warning("load_guard: %s", message)
        raise LoadRefusedError(message, "projected-exceeds")

    async def _ollama_frees_pending(
        self,
        pending: dict[str, _Free],
        resident: dict[str, int],
        headroom: float,
        deadline: float,
    ) -> bool:
        """True when a pending free needs another pass. False when none are pending or the wait is spent."""
        if not pending:
            return False
        remaining_frees, _ = self._retire_ollama_frees(pending, resident, headroom)
        pending.clear()
        pending.update(remaining_frees)
        if not pending:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        started = time.monotonic()
        _admit_waited.set(True)
        await asyncio.sleep(min(_POLL_S, remaining))
        _record_wait(OMLX, "free_settle", time.monotonic() - started)
        return True

    async def _omlx_unloads_pending(
        self,
        client: httpx.AsyncClient,
        pending: dict[str, _Free],
        used: float,
        deadline: float,
    ) -> tuple[bool, float]:
        """True when a pending oMLX unload needs another pass; False when none or wait spent."""
        if not pending:
            return False, used
        remaining_frees, _, used = await self._pending_omlx_unloads(client, pending, used)
        if remaining_frees is not pending:  # the retire path returns the input unchanged
            pending.clear()
            pending.update(remaining_frees)
        if not pending:
            return True, used
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, used
        started = time.monotonic()
        _admit_waited.set(True)
        await asyncio.sleep(min(_POLL_S, remaining))
        _record_wait(OMLX, "free_settle", time.monotonic() - started)
        return True, used

    def _unfreed_idle_ollama(
        self,
        resident: dict[str, int],
        freed: set[str],
        include_protected: bool = False,
        last_models: set[str] | None = None,
    ) -> list[str]:
        idle = [
            name
            for name, size in resident.items()
            if name not in freed
            and size > 0
            and self._ollama_hold_reason(name, include_protected) is None
        ]
        last_keys = {model_key(name) for name in (last_models or set())}
        idle.sort(
            key=lambda name: (
                model_key(name) in last_keys,
                self._last_access.get((OLLAMA, model_key(name)), 0.0),
            )
        )
        return idle

    async def _advance_omlx_ollama_capacity(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        headroom: float,
        model: str,
        need: float,
        available: float,
        deadline: float,
        pending: dict[str, _Free],
        freed: set[str],
        failed: set[str],
        omlx_held: list[tuple[str, int, str]] | None = None,
        last_models: set[str] | None = None,
    ) -> None:
        """Free each idle resident once, or wait when busy residents can still cover the gap."""
        if await self._ollama_frees_pending(pending, resident, headroom, deadline):
            return
        idle = self._unfreed_idle_ollama(resident, freed, last_models=last_models)
        if idle:
            name = idle[0]
            requested = await self._free_ollama(
                client,
                base,
                {name: resident[name]},
                last_models=last_models,
                want=need - available,
            )
            pending.update(requested)
            if name not in requested:
                failed.add(name)
            freed.add(name)
            return
        unfreed = {n: s for n, s in resident.items() if n not in freed}
        attempted = await self._yield_protected_idle(
            client, base, unfreed, need, available, pending, last_models=last_models
        )
        if attempted:
            failed.update(name for name in attempted if name not in pending)
            freed.update(attempted)
            return
        held = self._ollama_unfreeable(resident)
        releasable = _releasable_ollama_bytes(held, freed)
        waiting_models = [
            name for name, _, reason in held if reason in ("busy", "active elsewhere")
        ]
        if (
            releasable
            and available + releasable >= need
            and await self._wait_for_ollama_release(deadline, waiting_models)
        ):
            return
        self._refuse_blocked_omlx(
            model,
            need,
            available,
            self._omlx_ollama_blockers(resident, failed, pending),
            deadline,
            omlx_held,
        )

    async def _advance_omlx_own_residents(
        self,
        client: httpx.AsyncClient,
        status: dict[str, Any],
        target: str,
        shortage: float,
        used: float,
        deadline: float,
        pending: dict[str, _Free],
        attempted: set[str],
        pending_used: float,
    ) -> tuple[bool, list[tuple[str, int, str]], float]:
        """Free this engine's own idle residents before an oMLX cold load is refused.

        LRU first, never the target itself; keeper-protected residents yield last;
        pinned, busy, active-elsewhere, loading and failover-protected residents are never freed.
        Returns (re-measure, residents still holding bytes with why, pending baseline).
        """
        waiting, pending_used = await self._omlx_unloads_pending(
            client, pending, pending_used, deadline
        )
        if waiting:
            return True, [], pending_used
        freed, queued, after, posted, unloads = await self._free_omlx(
            client, shortage, used, exclude={target} | attempted
        )
        attempted.update(str(entry["model"]) for entry in unloads)
        if queued:
            pending.update(queued)
            pending_used = self._pending_baseline(used, after, posted)
        if freed or queued:
            return True, [], pending_used
        holding = await self._omlx_resident_blockers(client, status, target, attempted, pending)
        return False, holding, pending_used

    async def _omlx_resident_blockers(
        self,
        client: httpx.AsyncClient,
        status: dict[str, Any],
        target: str,
        attempted: set[str],
        pending: dict[str, _Free],
    ) -> list[tuple[str, int, str]]:
        """Loaded oMLX residents this load could not free: (name, bytes, why)."""
        holding: list[tuple[str, int, str]] = []
        unexplained: list[tuple[str, int]] = []
        for entry in (status or {}).get("models") or []:
            name = str(entry.get("id") or "")
            size = int(entry.get("estimated_size") or 0)
            if name == target or not entry.get("loaded") or size <= 0:
                continue
            if name in pending:
                holding.append((name, size, "unload unsettled"))
            elif name in attempted:
                holding.append((name, size, "unload failed"))
            elif name in self.failover_protected(OMLX):
                holding.append((name, size, "failover protected"))
            elif self.busy(OMLX, name):
                holding.append((name, size, "busy"))
            elif self._active_elsewhere(OMLX, name):
                holding.append((name, size, "active elsewhere"))
            elif entry.get("is_loading"):
                holding.append((name, size, "loading"))
            else:
                unexplained.append((name, size))
        if unexplained and await self._omlx_foreign_active(client):
            return holding + [(name, size, "foreign traffic") for name, size in unexplained]
        return holding + [(name, size, "pinned") for name, size in unexplained]

    async def _check_omlx_ollama_capacity(
        self, client: httpx.AsyncClient, model: str, deadline: float
    ) -> None:
        base = (self._ollama_url() or "").rstrip("/")
        if not base:
            return
        pending: dict[str, _Free] = {}
        freed: set[str] = set()
        failed: set[str] = set()
        pending_omlx: dict[str, _Free] = {}
        attempted_omlx: set[str] = set()
        pending_omlx_used = 0.0
        while True:
            status = await self._omlx_status(client)
            entry = _omlx_entry(status, model)
            if status is None or entry is None or entry.get("loaded"):
                return
            need = float(entry.get("estimated_size") or 0)
            capacity = await self._headroom(client)
            if not need or capacity is None:
                return
            headroom, used = capacity
            try:
                resident = await self._resident(client, base)
            except Exception as e:
                logger.warning("load_guard: could not inspect Ollama before oMLX load: %s", e)
                return
            available = _omlx_available(self._ollama_available(headroom, resident, 0))
            _record_headroom(available)
            if need <= available:
                return
            progress, omlx_holding, pending_omlx_used = await self._advance_omlx_own_residents(
                client,
                status,
                model,
                need - available,
                used,
                deadline,
                pending_omlx,
                attempted_omlx,
                pending_omlx_used,
            )
            if progress:
                continue
            await self._advance_omlx_ollama_capacity(
                client,
                base,
                resident,
                headroom,
                model,
                need,
                available,
                deadline,
                pending,
                freed,
                failed,
                omlx_holding,
                self._counterpart_models(OMLX, model),
            )

    async def admit_omlx(self, model: str) -> Callable[[], None] | None:
        """Serialise the cold load; free idle oMLX residents, then Ollama's, when short."""
        if not self.enabled() or not model:
            return None
        deadline = time.monotonic() + load_wait_s()
        _admit_waited.set(False)
        release: _Release | None = None
        activity = self._shared_process_lock("admissions.lock")
        try:
            try:
                async with self._client() as client:
                    entry = _omlx_entry(await self._omlx_status(client), model)
                    if entry is None:
                        return None
                    if entry.get("loaded"):
                        await self._free_for_resident_omlx(client, model, deadline)
                        return None
                    release = await self._acquire(OMLX, deadline, model)
                    entry = _omlx_entry(await self._omlx_status(client), model)
                    if entry is None or entry.get("loaded"):
                        release()
                        return None
                    await self._check_omlx_ollama_capacity(client, model, deadline)
                _record_admission(OMLX, _admit_waited.get())
                asyncio.get_running_loop().create_task(
                    self._release_when_resident(OMLX, "", model, release)
                )
                return release
            except LoadRefusedError as e:
                if release is not None:
                    release()
                _record_refusal(OMLX, e)
                raise
            except BaseException:
                if release is not None:
                    release()
                raise
        finally:
            if activity is not None:
                self._release_activity_lock(activity)

    async def _free_for_resident_omlx(
        self, client: httpx.AsyncClient, model: str, deadline: float
    ) -> None:
        """Free idle memory when a resident seat is past oMLX's prefill-safe share.

        A seat already loaded still prefills inside the engine's own room: once idle
        residents of either engine have eaten that room (2026-11-19 auto-coding), oMLX
        aborts the request mid-prefill. The seat itself and anything a worker is serving
        are never freed, and nothing here refuses: the engine still gets its chance.
        """
        base = (self._ollama_url() or "").rstrip("/")
        if not base:
            return
        settle = min(deadline, time.monotonic() + _FREE_SETTLE_EXPECTED_S)
        attempted_omlx: set[str] = set()
        requested_ollama: dict[str, _Free] = {}
        first = True
        try:
            while True:
                status = await self._omlx_status(client)
                used = (status or {}).get("current_model_memory")
                if status is None or used is None:
                    return
                shortage = -_omlx_prefill_reserve(status, float(used))
                if shortage <= 0 or (not first and time.monotonic() >= settle):
                    return
                first = False
                freed, queued, _, _, unloads = await self._free_omlx(
                    client, shortage, float(used), exclude={model} | attempted_omlx
                )
                attempted_omlx.update(str(entry["model"]) for entry in unloads)
                covered = freed + sum(free.size for free in queued.values())
                progress = bool(freed or queued)
                if covered < shortage:
                    resident = await self._resident(client, base)
                    newly = await self._free_ollama(
                        client,
                        base,
                        {n: s for n, s in resident.items() if n not in requested_ollama},
                        want=shortage - covered,
                        last_models=self._counterpart_models(OMLX, model),
                    )
                    requested_ollama.update(newly)
                    progress = progress or bool(newly)
                if not progress:
                    return
                await asyncio.sleep(min(_POLL_S, max(0.0, settle - time.monotonic())))
        except Exception as e:  # best effort: the request goes to the engine either way
            logger.warning("load_guard: could not make prefill room for %s: %s", model, e)

    async def plan(self, ollama_base: str, models: list[tuple[str, str]]) -> dict[str, Any]:
        """Whether `models` ((engine, model) pairs) fit together right now.

        Pure measurement, no side effects. Counts what the set would add (models
        not yet resident), against headroom plus idle Ollama residents and idle
        oMLX models outside the set. Each row reports its footprint
        (``projected_gib``) and the delta it adds (``adds_gib``)."""
        names = {m for _, m in models}
        async with self._client() as client:
            resident = await self._resident(client, ollama_base)
            st = await self._omlx_status(client)
            headroom = (
                None
                if st is None
                else (_budget_bytes(st) - float(st.get("current_model_memory") or 0))
            )
            need = 0.0
            per_model = []
            for engine, model in models:
                if engine == OLLAMA:
                    loaded = lookup_model(resident, model) is not None
                    footprint = await self._need(client, ollama_base, model)
                else:
                    entry = _omlx_entry(st, model) or {}
                    loaded = bool(entry.get("loaded"))
                    footprint = float(entry.get("estimated_size") or 0)
                size = 0.0 if loaded else footprint
                need += size
                per_model.append(
                    {
                        "engine": engine,
                        "model": model,
                        "resident": loaded,
                        "adds_gib": size / _GIB,
                        "projected_gib": footprint / _GIB,
                    }
                )
            idle_ollama = self._ollama_idle(resident, exclude=names, include_protected=True)
            try:
                _, idle = await self._omlx_idle_models(client, exclude=names)
            except Exception:
                idle = []
            freeable_omlx = float(
                sum(float(m.get("estimated_size") or m.get("actual_size") or 0) for m in idle)
            )
        available = (
            None
            if headroom is None
            else self._ollama_available(headroom, resident, idle_ollama) + freeable_omlx - _MARGIN
        )
        busy_requests = sum(self._busy.values())
        return {
            "guard_enabled": self.enabled(),
            "busy": busy_requests > 0,
            "busy_requests": busy_requests,
            "fits": None if available is None else need <= available,
            "need_gib": need / _GIB,
            "available_gib": None if available is None else available / _GIB,
            "headroom_gib": None if headroom is None else headroom / _GIB,
            "idle_ollama_gib": idle_ollama / _GIB,
            "freeable_omlx_gib": freeable_omlx / _GIB,
            "models": per_model,
        }

    async def seat_fit(self, ollama_base: str, seats: list[dict[str, Any]]) -> dict[str, Any]:
        """Every seat's projected footprint beside the standard residents.

        ``over_budget`` is the live snapshot (the budget left when every evictable
        resident is reclaimed). ``never_fit`` is only asserted against a fixed
        ``LOAD_GUARD_CEILING_GB``: the balanced tier's ceiling follows host free
        memory, so against a live ceiling the same seat would change answer with
        the moment (P5-OMLX-CEILING-001) — that is a budget, not a verdict.
        Pure measurement, no side effects; flags seats, never changes them."""
        async with self._client() as client:
            resident = await self._resident(client, ollama_base)
            st = await self._omlx_status(client)
            headroom = (
                None
                if st is None
                else _budget_bytes(st) - float(st.get("current_model_memory") or 0)
            )
            idle_ollama = self._ollama_idle(resident, include_protected=True)
            try:
                _, idle_models = await self._omlx_idle_models(client)
            except Exception:
                idle_models = []
            freeable_omlx = float(
                sum(
                    float(m.get("estimated_size") or m.get("actual_size") or 0) for m in idle_models
                )
            )
            available = (
                None
                if headroom is None
                else self._ollama_available(headroom, resident, idle_ollama)
                + freeable_omlx
                - _MARGIN
            )
            never_budget = _never_fit_budget()
            rows = [
                await self._seat_row(
                    client, ollama_base, st, resident, seat, available, never_budget
                )
                for seat in seats
            ]
        return {
            "guard_enabled": self.enabled(),
            "budget_source": (
                "fixed LOAD_GUARD_CEILING_GB" if _CEILING > 0 else "oMLX final_ceiling (live)"
            ),
            "ceiling_gib": None if st is None else _budget_bytes(st) / _GIB,
            "headroom_gib": None if headroom is None else headroom / _GIB,
            "idle_ollama_gib": idle_ollama / _GIB,
            "freeable_omlx_gib": freeable_omlx / _GIB,
            "margin_gib": _MARGIN / _GIB,
            "available_gib": None if available is None else available / _GIB,
            "never_fit_basis": _never_fit_basis(never_budget),
            "never_fit_budget_gib": None if never_budget is None else never_budget / _GIB,
            "ollama_residents": {
                name: {
                    "gib": self._ollama_size(name, size) / _GIB,
                    "hold": self._ollama_hold_reason(name) or "idle (evictable)",
                }
                for name, size in resident.items()
            },
            "omlx_residents": {
                str(m.get("id")): float(m.get("estimated_size") or 0) / _GIB
                for m in (st or {}).get("models") or []
                if m.get("loaded")
            },
            "seats": rows,
            "never_fit": [r["seat"] for r in rows if r["never_fit"]],
            "over_budget": [r["seat"] for r in rows if r["over_budget"]],
        }

    async def _seat_row(
        self,
        client: httpx.AsyncClient,
        base: str,
        status: dict[str, Any] | None,
        resident: dict[str, int],
        seat: dict[str, Any],
        available: float | None,
        never_budget: float | None,
    ) -> dict[str, Any]:
        """One seat's projected bytes per engine, what fits now, and what never fits."""
        model = str(seat.get("model") or "")
        omlx_model = str(seat.get("omlx_model") or "")
        ollama_gib: float | None = None
        if model:
            footprint = await self._need(client, base, model)
            key = (base, model_key(model))
            if self._sizes.get(key) or self._observed.get((OLLAMA, model_key(model))):
                ollama_gib = footprint / _GIB
        entry = _omlx_entry(status, omlx_model) if omlx_model else None
        omlx_gib = float(entry.get("estimated_size") or 0) / _GIB if entry else None
        resident_now = bool(
            (model and lookup_model(resident, model) is not None) or (entry and entry.get("loaded"))
        )
        served = ollama_gib is not None or omlx_gib is not None
        fits_ollama = (
            ollama_gib is not None and available is not None and ollama_gib * _GIB <= available
        )
        fits_omlx = omlx_gib is not None and available is not None and omlx_gib * _GIB <= available
        fits = resident_now or fits_ollama or fits_omlx
        best = min(gib for gib in (ollama_gib, omlx_gib) if gib is not None) if served else None
        return {
            "seat": str(seat.get("seat", "")),
            "model": model,
            "omlx_model": omlx_model if omlx_model else None,
            "stack_down_only": bool(seat.get("stack_down_only")),
            "resident": resident_now,
            "ollama_projected_gib": ollama_gib,
            "omlx_projected_gib": omlx_gib,
            "served": served,
            "fits": bool(fits) if served else None,
            "over_budget": bool(served and available is not None and not fits),
            "never_fit": bool(
                served
                and never_budget is not None
                and best is not None
                and best * _GIB > never_budget
            ),
        }

    async def reclaim_idle_memory(self, ollama_base: str, need: float) -> list[dict[str, str]]:
        """Unload idle residents through the same path used for cold-load admission."""
        if need <= 0:
            return []
        deadline = time.monotonic() + load_wait_s()
        release = await self._acquire(OLLAMA, deadline, "job memory reclaim")
        try:
            async with self._client() as client:
                resident = await self._resident(client, ollama_base)
                capacity = await self._headroom(client)
                idle = self._ollama_idle(resident)
                if capacity is None:
                    requested = await self._free_ollama(client, ollama_base, resident)
                    return [
                        {"engine": OLLAMA, "model": name, "status": "requested"}
                        for name in requested
                    ]
                _, used = capacity
                _, _, _, _, _, unloads, _ = await self._free_idle_memory(
                    client, ollama_base, resident, idle, used, need
                )
                return unloads
        finally:
            release()


class _Release:
    """Idempotent release of the cold-load lock; knows whether it has run."""

    def __init__(self, lock: asyncio.Lock, process_lock: Any = None) -> None:
        self._lock = lock
        self._process_lock = process_lock
        self.released = False

    def __call__(self) -> None:
        if not self.released:
            self.released = True
            try:
                if self._process_lock is not None:
                    fcntl.flock(self._process_lock.fileno(), fcntl.LOCK_UN)
                    self._process_lock.close()
            finally:
                self._lock.release()


def _omlx_entry(status: dict[str, Any] | None, model: str) -> dict[str, Any] | None:
    for m in (status or {}).get("models") or []:
        if m.get("id") == model:
            return m  # type: ignore[no-any-return]
    return None

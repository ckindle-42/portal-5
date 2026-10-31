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
   already cascades as a capacity rejection.
4. **Fit can be asked in advance.** ``plan()`` (route ``POST /admin/load-plan``)
   says whether a set of models fits together right now, so batch work can run
   in fit-sized waves instead of discovering the answer as refusals.

Headroom is oMLX's ``final_ceiling`` minus its resident model memory (oMLX derives
the ceiling from host free + inactive memory), plus idle Ollama residents, minus
``LOAD_GUARD_MARGIN_GB``. ``LOAD_GUARD_CEILING_GB`` replaces that ceiling with a
fixed budget; the balanced tier's ceiling follows free memory (P5-OMLX-CEILING-001).
Ollama sizing adds per-layer KV bytes at baked ``num_ctx`` using ``OLLAMA_KV_CACHE_TYPE`` (default q8_0); missing geometry falls back to weights × ``LOAD_GUARD_FACTOR`` and observed residency can raise the estimate.
Cold loads unload idle models from the other engine when current headroom does not cover the incoming model.

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
#: Weights on disk understate the loaded footprint (KV cache, compute buffers):
#: the crash's model was ~18 GB on disk and Ollama predicted 22.7 GiB at 32K ctx.
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
    values = _show_values(show)
    base = weights * _FACTOR
    kv = _ollama_kv_bytes(values, _context_tokens(model, values))
    return base + kv if kv is not None else base


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
        GUARD.protect(engine, model)
        logger.info(
            "load_guard: protecting %s:%s for %.0fs after a failover",
            engine,
            model,
            FAILOVER_PROTECT_S,
        )


def _budget_bytes(status: dict[str, Any]) -> float:
    """The ceiling to budget against: the fixed one when set, else oMLX's live one."""
    return _CEILING if _CEILING > 0 else float(status.get("final_ceiling") or 0)


def _releasable_ollama_bytes(held: list[tuple[str, int, str]], freed: set[str]) -> float:
    """Bytes of busy or active-elsewhere residents that have not already been freed."""
    return float(
        sum(
            size
            for name, size, reason in held
            if name not in freed and reason in ("busy", "active elsewhere")
        )
    )


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
    ) -> None:
        self._omlx_url = omlx_url
        self._ollama_url = ollama_url
        self._protected: dict[tuple[str, str], float] = {}  # (engine, model) -> monotonic deadline
        self._pinned = pinned
        self._client = client
        self._lock = asyncio.Lock()
        self._busy: Counter[tuple[str, str]] = Counter()
        self._changed = asyncio.Event()
        self._sizes: dict[tuple[str, str], int] = {}
        self._needs: dict[tuple[str, str], float] = {}
        self._observed: dict[tuple[str, str], int] = {}
        self._host_free_reading: float | None = None
        self._host_free_read_at = 0.0

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("LOAD_GUARD", "1") != "0"

    # ── in-flight tracking ────────────────────────────────────────────────

    def begin(self, engine: str, model: str) -> Callable[[], None]:
        """Count one in-flight request; return its idempotent end()."""
        return self._begin_with_activity_lock(engine, model, self._activity_lock(engine, model))

    def _begin_with_activity_lock(
        self, engine: str, model: str, activity_lock: Any | None
    ) -> Callable[[], None]:
        key = (engine, model)
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
        key = model_key(model) if engine == OLLAMA else model
        digest = hashlib.sha256(f"{engine}\0{key}".encode()).hexdigest()
        return _PROCESS_LOCK_DIR / f"active-{digest}.lock"

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

    def protect(self, engine: str, model: str, seconds: float | None = None) -> None:
        """Exclude ``model`` from eviction for ``seconds`` (default FAILOVER_PROTECT_S)."""
        span = FAILOVER_PROTECT_S if seconds is None else seconds
        self._protected[(engine, model)] = time.monotonic() + span

    def protected(self, engine: str) -> set[str]:
        """The models of ``engine`` currently protected from eviction (Ollama names case-folded)."""
        now = time.monotonic()
        return {
            model_key(m) if engine == OLLAMA else m
            for (e, m), until in self._protected.items()
            if e == engine and until > now
        }

    def busy(self, engine: str, model: str) -> int:
        if engine != OLLAMA:
            return self._busy.get((engine, model), 0)
        key = model_key(model)
        return sum(
            n for (e, name), n in self._busy.items() if e == engine and model_key(name) == key
        )

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

    def _ollama_hold_reason(self, name: str) -> str | None:
        """Why this Ollama resident cannot be freed, or None when it is idle."""
        key = model_key(name)
        if key == model_key(self._pinned()):
            return "pinned"
        if key in self.protected(OLLAMA):
            return "protected"
        if self.busy(OLLAMA, name):
            return "busy"
        if self._active_elsewhere(OLLAMA, name):
            return "active elsewhere"
        return None

    def _ollama_idle(
        self, resident: dict[str, int], exclude: frozenset[str] | set[str] = frozenset()
    ) -> float:
        excluded = {model_key(name) for name in exclude}
        return float(
            sum(
                self._ollama_size(name, size)
                for name, size in resident.items()
                if model_key(name) not in excluded and self._ollama_hold_reason(name) is None
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
        """(oMLX url, its idle unpinned loaded models, least recently used first).
        Empty when a client outside the pipeline is using oMLX: its requests are
        invisible here, so no oMLX model can be known idle."""
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
        tracked = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        if int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked:
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
        idle = [
            m
            for m in models
            if m.get("loaded")
            and not m.get("pinned")
            and not m.get("is_loading")
            and m["id"] not in exclude
            and m["id"] not in self.protected(OMLX)
            and not self.busy(OMLX, m["id"])
            and not self._active_elsewhere(OMLX, m["id"])
        ]
        return url, sorted(idle, key=lambda m: float(m.get("last_access") or 0))

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
        tracked = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        return int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked

    async def _free_omlx(
        self, client: httpx.AsyncClient, want: float, used: float
    ) -> tuple[float, dict[str, _Free], float | None, float, list[dict[str, str]]]:
        """Unload idle oMLX models; report the drop, queued work, post state, 200 bytes."""
        try:
            url, idle = await self._omlx_idle_models(client)
            queued: dict[str, _Free] = {}
            unloads: list[dict[str, str]] = []
            posted = 0.0
            covered = 0.0  # 200 plus queued 202 bytes: a queued unload can cover the shortage
            any_post = False
            for m in idle:
                if covered >= want:
                    break
                r = await client.post(f"{url}/admin/api/models/{quote(m['id'], safe='')}/unload")
                any_post = True
                size = float(m.get("estimated_size") or m.get("actual_size") or 0)
                if r.status_code == 200:
                    posted += size
                    covered += size
                    unloads.append({"engine": OMLX, "model": str(m["id"]), "status": "unloaded"})
                    _record_unload(OMLX, "idle_omlx")
                    logger.info("load_guard: unloaded idle oMLX model %s", m["id"])
                elif r.status_code == 202:
                    queued[m["id"]] = _Free(size)
                    covered += size
                    unloads.append({"engine": OMLX, "model": str(m["id"]), "status": "queued"})
                    _record_unload(OMLX, "queued_202")
            if not any_post:
                return 0.0, queued, None, 0.0, unloads
            after = await self._omlx_used(client)
            freed = 0.0 if after is None else max(0.0, used - after)
            return freed, queued, after, posted, unloads
        except Exception as e:
            logger.warning("load_guard: could not free oMLX memory: %s", e)
            return 0.0, {}, None, 0.0, []

    async def _free_ollama(
        self, client: httpx.AsyncClient, base: str, resident: dict[str, int]
    ) -> dict[str, _Free]:
        """Request accepted unloads and retain their pre-unload headroom records."""
        idle = [n for n, size in resident.items() if size and self._ollama_idle({n: size}) > 0]
        requested: dict[str, _Free] = {}
        for name in idle:
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
            _record_unload(OLLAMA, "idle_ollama")
            logger.info("load_guard: unloaded idle Ollama model %s", name)
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
    ) -> tuple[_Release, bool]:
        release()
        saw_loading = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if saw_loading:
                        raise LoadRefusedError(
                            f"Cannot load {model}: engine model transition still active "
                            f"after waiting {_waited_s(deadline):.1f}s",
                            "transition-active",
                        )
                    break
                try:
                    loading = await asyncio.wait_for(self._omlx_loading(client), timeout=remaining)
                except TimeoutError:
                    if saw_loading:
                        raise LoadRefusedError(
                            f"Cannot load {model}: engine model transition still active "
                            f"after waiting {_waited_s(deadline):.1f}s",
                            "transition-active",
                        ) from None
                    break
                if not loading:
                    break
                saw_loading = True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LoadRefusedError(
                        f"Cannot load {model}: engine model transition still active "
                        f"after waiting {_waited_s(deadline):.1f}s",
                        "transition-active",
                    )
                started = time.monotonic()
                await self._wait_change(min(_POLL_S, remaining))
                _record_wait(OLLAMA, "engine_transition", time.monotonic() - started)
            release = await self._acquire(OLLAMA, deadline, model)
            held.append(release)
            return release, saw_loading
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
    ) -> tuple[_Release, bool]:
        remaining = deadline - time.monotonic()
        release()
        foreign_active = False
        if remaining > 0:
            try:
                foreign_active = await asyncio.wait_for(
                    self._omlx_foreign_active(client), timeout=remaining
                )
            except TimeoutError:
                if pending_free_names:
                    raise self._free_settle_refusal(
                        model, pending_free_names, need, available, _waited_s(deadline)
                    ) from None
                raise self._ollama_refusal(
                    model, need, available, headroom, idle, quiet=False, waited=_waited_s(deadline)
                ) from None
        changing = bool(self._busy) or foreign_active
        activity_seen = activity_seen or changing
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
        return release, activity_seen

    async def _free_idle_memory(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        shortage: float,
    ) -> tuple[
        bool,
        dict[str, _Free],
        dict[str, _Free],
        float | None,
        float,
        list[dict[str, str]],
    ]:
        omlx_freed, omlx_queued, after, synchronous, unloads = await self._free_omlx(
            client, shortage, used
        )
        if omlx_freed < shortage and idle:
            ollama_requested = await self._free_ollama(client, base, resident)
        else:
            ollama_requested = {}
        unloads.extend(
            {"engine": OLLAMA, "model": name, "status": "requested"} for name in ollama_requested
        )
        did_free = bool(omlx_freed or omlx_queued or ollama_requested)
        return did_free, omlx_queued, ollama_requested, after, synchronous, unloads

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
    ) -> tuple[bool, float, float]:
        """Free idle memory and fold it in; return the queued baseline and post counter."""
        did_free, queued, requested, after, synchronous, _ = await self._free_idle_memory(
            client, base, resident, idle, used, shortage
        )
        pending_omlx.update(queued)
        pending_ollama.update(requested)
        post = used if after is None else after
        return did_free, self._pending_baseline(used, after, synchronous), post

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
        return LoadRefusedError(
            f"Cannot load {model}: free of {freed} did not settle within "
            f"the {waited:.1f}s load wait (projected {need / _GIB:.1f} GiB, host "
            f"headroom {available / _GIB:.1f} GiB)",
            "free-settle",
        )

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
            process_lock = (_PROCESS_LOCK_DIR / "cold-load.lock").open("a+")
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
        try:
            release = await self._admit_ollama(base, model, deadline, held)
        except asyncio.CancelledError:
            # The caller gave up (client disconnect, W3): never leak the
            # host-wide cold-load lock, or every later cold load deadlocks.
            for r in held:
                r()
            raise
        except LoadRefusedError as e:
            _record_refusal(OLLAMA, e)
            raise
        if release is None:
            return None
        _record_admission(OLLAMA, _admit_waited.get())
        asyncio.get_running_loop().create_task(
            self._release_when_resident(OLLAMA, base, model, release)
        )
        return release

    async def admit_and_begin_ollama(
        self, base: str, model: str
    ) -> tuple[Callable[[], None] | None, Callable[[], None]]:
        """Admit then lease the model through request completion across workers."""
        if not self.enabled() or not model:
            return None, self.begin(OLLAMA, model)
        release = await self.admit(base, model)
        activity_lock = None
        try:
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
            free_attempted = False
            activity_seen = False
            pending_omlx: dict[str, _Free] = {}
            pending_omlx_used = 0.0
            pending_ollama: dict[str, _Free] = {}
            last_used: float | None = None
            recheck = False
            try:
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
                    last_used, recheck = self._track_counter(used, last_used, recheck)
                    idle = self._ollama_idle(resident)
                    available = self._ollama_available(headroom, resident, idle) - _MARGIN
                    _record_headroom(available)
                    if need > available and not free_attempted:
                        free_attempted = True
                        freed_or_queued, pending_omlx_used, last_used = await self._free_for_load(
                            client,
                            base,
                            resident,
                            idle,
                            used,
                            need - available,
                            pending_omlx,
                            pending_ollama,
                        )
                        if freed_or_queued:
                            continue
                    pending_omlx, settled, pending_omlx_used = await self._pending_omlx_unloads(
                        client, pending_omlx, pending_omlx_used
                    )
                    if settled:
                        recheck = False  # our own unload moved the counter
                        continue  # re-measure headroom before deciding
                    pending_ollama = self._settle_ollama_frees(
                        model, need, available, resident, headroom, pending_ollama, deadline
                    )
                    if need <= available:
                        break
                    release, loading_seen = await self._wait_if_omlx_loading(
                        client, model, deadline, release, held
                    )
                    if loading_seen:
                        continue
                    release, activity_seen = await self._wait_if_ollama_capacity_may_change(
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
            except LoadRefusedError:
                release()
                raise
            except Exception as e:
                logger.warning("load_guard: measurement failed for %s, admitting: %s", model, e)
        return release

    async def _wait_for_ollama_release(self, deadline: float) -> bool:
        """One poll for an Ollama resident to go idle. False when the deadline is already spent."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        _admit_waited.set(True)
        started = time.monotonic()
        await self._wait_change(min(remaining, max(_POLL_S, 0.01)))
        _record_wait(OMLX, "in_flight", time.monotonic() - started)
        return True

    def _refuse_blocked_omlx(
        self,
        model: str,
        need: float,
        available: float,
        held: list[tuple[str, int, str]],
        deadline: float,
    ) -> NoReturn:
        """Refuse an oMLX cold load, naming every Ollama resident that could not be freed."""
        waited = _waited_s(deadline)
        if not held:
            raise LoadRefusedError(
                f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
                f"exceed host headroom {available / _GIB:.1f} GiB",
                "projected-exceeds",
            )
        blocked = ", ".join(
            f"{name} ({size / _GIB:.1f} GiB, {reason})" for name, size, reason in held
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

    def _unfreed_idle_ollama(self, resident: dict[str, int], freed: set[str]) -> list[str]:
        return [
            name
            for name, size in resident.items()
            if name not in freed and size > 0 and self._ollama_hold_reason(name) is None
        ]

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
    ) -> None:
        """Free each idle resident once, or wait when busy residents can still cover the gap."""
        if await self._ollama_frees_pending(pending, resident, headroom, deadline):
            return
        idle = self._unfreed_idle_ollama(resident, freed)
        if idle:
            subset = {name: resident[name] for name in idle}
            pending.update(await self._free_ollama(client, base, subset))
            freed.update(idle)
            return
        held = self._ollama_unfreeable(resident)
        releasable = _releasable_ollama_bytes(held, freed)
        if (
            releasable
            and available + releasable >= need
            and await self._wait_for_ollama_release(deadline)
        ):
            return
        self._refuse_blocked_omlx(model, need, available, held, deadline)

    async def _check_omlx_ollama_capacity(
        self, client: httpx.AsyncClient, model: str, deadline: float
    ) -> None:
        base = (self._ollama_url() or "").rstrip("/")
        if not base:
            return
        pending: dict[str, _Free] = {}
        freed: set[str] = set()
        while True:
            status = await self._omlx_status(client)
            entry = _omlx_entry(status, model)
            if status is None or entry is None or entry.get("loaded"):
                return
            need = float(entry.get("estimated_size") or 0)
            capacity = await self._headroom(client)
            if not need or capacity is None:
                return
            headroom, _ = capacity
            try:
                resident = await self._resident(client, base)
            except Exception as e:
                logger.warning("load_guard: could not inspect Ollama before oMLX load: %s", e)
                return
            available = self._ollama_available(headroom, resident, 0) - _MARGIN
            _record_headroom(available)
            if need <= available:
                return
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
            )

    async def admit_omlx(self, model: str) -> Callable[[], None] | None:
        """Serialise the cold load and free idle Ollama residents when its size exceeds current headroom."""
        if not self.enabled() or not model:
            return None
        deadline = time.monotonic() + load_wait_s()
        _admit_waited.set(False)
        release: _Release | None = None
        try:
            async with self._client() as client:
                entry = _omlx_entry(await self._omlx_status(client), model)
                if entry is None or entry.get("loaded"):
                    return None
                release = await self._acquire(OMLX, deadline, model)
                entry = _omlx_entry(await self._omlx_status(client), model)
                if entry is None or entry.get("loaded"):
                    release()
                    return None
                await self._check_omlx_ollama_capacity(client, model, deadline)
        except asyncio.CancelledError:
            if release is not None:
                release()  # never leak the cold-load lock to a cancelled caller
            raise
        except LoadRefusedError as e:
            if release is not None:
                release()
            _record_refusal(OMLX, e)
            raise
        _record_admission(OMLX, _admit_waited.get())
        asyncio.get_running_loop().create_task(
            self._release_when_resident(OMLX, "", model, release)
        )
        return release

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
            idle_ollama = self._ollama_idle(resident, exclude=names)
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
                _, _, _, _, _, unloads = await self._free_idle_memory(
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

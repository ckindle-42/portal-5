"""Metrics-state persistence and lightweight per-event recorders.

Loads/saves the JSON metrics snapshot (``_STATE_FILE``), runs the periodic
save loop, and records error/persona counters. Depends only on
``portal.platform.inference.router.metrics``; never imports router_pipe.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from contextlib import suppress
from pathlib import Path

import portal.platform.inference.router.metrics as _metrics_mod
from portal.platform.inference.router.metrics import (
    _errors_total,
    _persona_usage,
)

logger = logging.getLogger(__name__)

# Persistent state file — survives pipeline restarts.
# Mounted as a Docker volume so it persists across container lifecycle.
_STATE_FILE = Path(os.environ.get("METRICS_STATE_FILE", "/app/data/metrics_state.json"))

# Basic Prometheus-compatible metrics counter
_request_count: dict[str, int] = {}

# Extended stats tracked for daily summary (aggregated from Prometheus metrics)
# These are updated on every request and read by the notification scheduler.
# _total_response_time_ms lives in portal.platform.inference.router.metrics (updated by _record_response_time)
_total_tps: float = 0.0
_request_tps_count: int = 0
_total_input_tokens: int = 0
_total_output_tokens: int = 0
_req_count_by_model: dict[str, int] = {}  # model_name -> count (plain dict for summary)
_req_count_by_error: dict[str, int] = {}  # error_type -> count (plain dict for summary)
_peak_concurrent: int = 0
_persona_usage_raw: dict[str, dict[str, int]] = {}  # persona -> {model -> count}


def _record_error(workspace: str, error_type: str) -> None:
    """Record an error to both the Prometheus counter and the daily-summary dict.

    The pipeline keeps two parallel error counts: ``_errors_total`` (a
    Prometheus ``Counter`` scraped by ``/metrics``) and
    ``_req_count_by_error`` (a plain dict diffed by the notification
    scheduler to build daily summaries). They must update together —
    every error path goes through this helper rather than mutating
    either directly.

    Args:
        workspace: Workspace id; unknown ids are accepted (the Prometheus
            label space simply grows).
        error_type: Short error category (e.g. ``"timeout"``,
            ``"backend_down"``, ``"tool_error"``). Used as both a
            Prometheus label and a dict key.
    """
    _errors_total.labels(workspace=workspace, error_type=error_type).inc()
    global _req_count_by_error
    _req_count_by_error[error_type] = _req_count_by_error.get(error_type, 0) + 1


def _record_persona(persona: str, model: str) -> None:
    """Record one persona × model usage to both the Prometheus counter and the summary dict.

    Mirror of ``_record_error`` for persona telemetry. The nested-dict
    shape ``_persona_usage_raw[persona][model] = count`` is what the
    notification daily summary consumes; storing it pre-shaped saves
    the scheduler from re-aggregating from a flat counter.

    Args:
        persona: Persona slug from the chat-completions request, or
            ``"unknown"`` when no persona was selected.
        model: Concrete model id the request was routed to (after
            ``model_hint`` resolution). Distinct from the user-facing
            workspace id.
    """
    _persona_usage.labels(persona=persona, model=model).inc()
    global _persona_usage_raw
    if persona not in _persona_usage_raw:
        _persona_usage_raw[persona] = {}
    _persona_usage_raw[persona][model] = _persona_usage_raw[persona].get(model, 0) + 1


def _load_state() -> None:
    """Restore persisted metrics state from disk (survives restarts).

    IMPORTANT: In-memory accumulator counters (_request_count, _total_tps, etc.)
    are intentionally NOT pre-loaded from disk.  The _save_state() merge adds
    each worker's in-memory delta on top of the existing file totals; if we also
    pre-loaded the file totals into memory we would double-count on every save
    cycle, compounding exponentially across workers and restarts.

    Only peak_concurrent is restored because it uses max() rather than addition
    in the merge, so loading the historical peak is safe and desirable.

    Called once from ``lifespan`` after ``BackendRegistry`` is up but
    before the first health check completes. See ``_save_state`` for
    the partner function that writes deltas back to disk.
    """
    global _peak_concurrent

    if not _STATE_FILE.exists():
        logger.info("No persisted metrics state found at %s — starting fresh", _STATE_FILE)
        return

    try:
        state = json.loads(_STATE_FILE.read_text())
        _peak_concurrent = int(state.get("peak_concurrent", 0))
        logger.info(
            "Loaded persisted metrics state: %d cumulative requests in file, peak concurrent=%d",
            sum(v for v in state.get("request_count", {}).values() if isinstance(v, int)),
            _peak_concurrent,
        )
    except Exception as e:
        logger.warning("Failed to load persisted metrics state: %s — starting fresh", e)


def _save_state() -> None:
    """Persist in-memory metric deltas to disk with delta semantics.

    Cross-worker correctness:

    1. Acquire exclusive ``fcntl.flock`` on a sidecar lockfile
       (serialises all workers; a 4-worker pipeline pays ~10ms wait
       on contention).
    2. Read the file, add this worker's in-memory delta, write
       atomically via temp file + rename so a kill mid-write can't
       leave a partial file for the next ``_load_state``.
    3. **Reset in-memory accumulators to 0** — the delta has been
       persisted. Without this reset, every subsequent save re-adds
       the same cumulative totals on top of the file, inflating
       values by ``saves_per_day × workers``.

    ``peak_concurrent`` is the only field exempt from the reset
    because it merges via ``max()`` rather than addition and
    represents an all-time peak.

    Failure handling: all exceptions are swallowed to ``logger.debug``.
    A metrics-state failure must not break a serving pipeline — if
    the disk is full or the lockfile is unwritable, request handling
    continues and only telemetry is lost. The opposite (crashing
    because metrics couldn't save) is worse.

    Called every 60s by ``_state_save_loop`` and once more from
    ``lifespan`` shutdown. See ``_load_state`` for the partner that
    reads — only ``peak_concurrent`` is read; accumulators are NOT
    pre-loaded, by design.
    """
    global _total_tps, _request_tps_count
    global _total_input_tokens, _total_output_tokens
    global _request_count, _req_count_by_model, _req_count_by_error, _persona_usage_raw
    global _peak_concurrent

    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_file = _STATE_FILE.with_suffix(".lock")
        with open(lock_file, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                # Read existing state (may have been written by another worker)
                existing: dict = {}
                if _STATE_FILE.exists():
                    with suppress(json.JSONDecodeError, OSError):
                        existing = json.loads(_STATE_FILE.read_text())

                # Merge: sum accumulators, max for peak
                merged = {
                    "request_count": dict(existing.get("request_count", {})),
                    "total_response_time_ms": float(existing.get("total_response_time_ms", 0.0))
                    + _metrics_mod._total_response_time_ms,
                    "total_tps": float(existing.get("total_tps", 0.0)) + _total_tps,
                    "request_tps_count": int(existing.get("request_tps_count", 0))
                    + _request_tps_count,
                    "total_input_tokens": int(existing.get("total_input_tokens", 0))
                    + _total_input_tokens,
                    "total_output_tokens": int(existing.get("total_output_tokens", 0))
                    + _total_output_tokens,
                    "req_count_by_model": dict(existing.get("req_count_by_model", {})),
                    "req_count_by_error": dict(existing.get("req_count_by_error", {})),
                    "peak_concurrent": max(
                        int(existing.get("peak_concurrent", 0)), _peak_concurrent
                    ),
                    "persona_usage_raw": dict(existing.get("persona_usage_raw", {})),
                }

                # Merge nested dicts
                for ws, count in _request_count.items():
                    merged["request_count"][ws] = merged["request_count"].get(ws, 0) + count
                for model, count in _req_count_by_model.items():
                    merged["req_count_by_model"][model] = (
                        merged["req_count_by_model"].get(model, 0) + count
                    )
                for err_type, count in _req_count_by_error.items():
                    merged["req_count_by_error"][err_type] = (
                        merged["req_count_by_error"].get(err_type, 0) + count
                    )
                for persona, models in _persona_usage_raw.items():
                    if persona not in merged["persona_usage_raw"]:
                        merged["persona_usage_raw"][persona] = {}
                    for model, count in models.items():
                        merged["persona_usage_raw"][persona][model] = (
                            merged["persona_usage_raw"][persona].get(model, 0) + count
                        )

                # Atomic write
                tmp = _STATE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(merged))
                tmp.rename(_STATE_FILE)

                # CRITICAL: reset in-memory accumulators after successful persist.
                # The delta is now in the file. Re-summing in-memory on the next
                # save would double-count.
                _metrics_mod._total_response_time_ms = 0.0
                _total_tps = 0.0
                _request_tps_count = 0
                _total_input_tokens = 0
                _total_output_tokens = 0
                _request_count.clear()
                _req_count_by_model.clear()
                _req_count_by_error.clear()
                _persona_usage_raw.clear()
                # peak_concurrent is NOT reset — it uses max() and represents
                # an all-time peak that should survive across save cycles.
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.debug("Failed to persist metrics state: %s", e)


async def _state_save_loop(interval: int = 60) -> None:
    """Background task: persist metrics state to disk every ``interval`` seconds.

    No internal exception handler — ``_save_state`` already swallows
    failures to ``logger.debug``, so the loop can never crash on a
    metrics issue. Handles ``asyncio.CancelledError`` implicitly via
    the missing handler: cancellation propagates and the task ends.

    Shutdown sequence is ``lifespan`` cancelling this task and then
    calling ``_save_state`` one final time. The pattern ensures
    in-flight deltas at shutdown are persisted, not lost in the
    cancelled iteration.

    Args:
        interval: Seconds between saves. The 60s default is a balance
            between persistence freshness and disk write rate —
            shortening it under 10s risks contention with the 30s
            health-check cycle's logging cadence.
    """
    while True:
        await asyncio.sleep(interval)
        _save_state()

"""Portal 5 — Notification scheduler for daily usage summaries."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
    from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None

if TYPE_CHECKING:
    from portal.platform.inference.cluster_backends import BackendRegistry
    from portal.platform.inference.notifications.dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)

# Cooldown file: prevents duplicate sends when PIPELINE_WORKERS > 1.
# All uvicorn workers share /tmp (in-memory tmpfs), so they coordinate via this file.
_COOLDOWN_FILE = Path("/tmp/.portal_daily_summary_sent")
_COOLDOWN_SECONDS = 23 * 3600  # 23 hours — staggered send on restart is fine

# Snapshot file: stores previous-day metrics so the summary shows deltas, not totals.
# Stored in /app/data (named volume) so it persists across container rebuilds.
_SNAPSHOT_FILE = Path(
    os.environ.get("DAILY_SUMMARY_SNAPSHOT_FILE", "/app/data/daily_summary_snapshot.json")
)

# Module-level references to router_pipe state (set during integration)
_request_count: dict[str, int] = {}
_startup_time: float = 0.0
_registry_ref: NotificationDispatcher | None = None
_registry_instance: BackendRegistry | None = None


def _load_aggregated_state() -> dict[str, Any]:
    """Read the merged metrics state file (aggregated across all workers).

    With PIPELINE_WORKERS > 1 each worker has its own in-memory counters.
    The state file on disk is the only place where all workers' counters are
    merged together, so the daily summary must read from it.
    """
    try:
        from portal.platform.inference.router.state import _STATE_FILE

        if _STATE_FILE.exists():
            return cast(dict[str, Any], json.loads(_STATE_FILE.read_text()))
    except (json.JSONDecodeError, OSError, ImportError):
        pass
    return {}


def _attach_to_pipeline(
    dispatcher: NotificationDispatcher,
    request_count: dict[str, int],
    startup_time: float,
    registry: BackendRegistry | None = None,
) -> None:
    """
    Called during router_pipe lifespan startup to attach scheduler
    to the pipeline's module-level metrics state.

    Note: Extended stats (TPS, response time, tokens, model usage) are read
    directly from router_pipe module at send time via getattr(), avoiding
    stale closure issues with scalar values.
    """
    global _registry_ref, _request_count, _startup_time, _registry_instance
    _registry_ref = dispatcher
    _request_count = request_count
    _startup_time = startup_time
    _registry_instance = registry
    logger.info("NotificationScheduler attached to pipeline metrics")


def _load_snapshot() -> dict[str, Any]:
    """Load previous-day metrics snapshot from disk."""
    try:
        if _SNAPSHOT_FILE.exists():
            return cast(dict[str, Any], json.loads(_SNAPSHOT_FILE.read_text()))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_snapshot(metrics: dict[str, Any]) -> None:
    """Save current metrics snapshot to disk for next-day delta computation."""
    try:
        _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT_FILE.write_text(json.dumps(metrics, default=str))
    except OSError:
        pass


def _delta(current: int | float, previous: int | float) -> int | float:
    """Compute delta, clamping to zero if counter was reset."""
    diff = current - previous
    return max(diff, 0) if isinstance(diff, (int, float)) else 0


def _delta_dict(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    """Compute per-key delta between two count dicts."""
    result: dict[str, int] = {}
    for key, val in current.items():
        d = val - previous.get(key, 0)
        if d > 0:
            result[key] = d
    return result


def _snapshot_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Copy the cumulative counters the daily summary differences against yesterday."""
    raw_samples = state.get("ttft_samples") or []
    samples: list[float] = []
    if isinstance(raw_samples, list):
        for item in raw_samples:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                continue
            samples.append(float(item))
    return {
        "request_count": state.get("request_count", {}),
        "total_response_time_ms": float(state.get("total_response_time_ms", 0.0)),
        "total_tps": float(state.get("total_tps", 0.0)),
        "request_tps_count": int(state.get("request_tps_count", 0)),
        "total_input_tokens": int(state.get("total_input_tokens", 0)),
        "total_output_tokens": int(state.get("total_output_tokens", 0)),
        "req_count_by_model": state.get("req_count_by_model", {}),
        "req_count_by_error": state.get("req_count_by_error", {}),
        "peak_concurrent": int(state.get("peak_concurrent", 0)),
        "decode_tokens": float(state.get("decode_tokens", 0.0)),
        "decode_seconds": float(state.get("decode_seconds", 0.0)),
        "answer_tokens": float(state.get("answer_tokens", 0.0)),
        "answer_seconds": float(state.get("answer_seconds", 0.0)),
        "ttft_samples": samples,
        "answer_tokens_by_model": dict(state.get("answer_tokens_by_model") or {}),
        "answer_seconds_by_model": dict(state.get("answer_seconds_by_model") or {}),
    }


def _weighted_rate(tokens: float, seconds: float) -> float:
    """Token-weighted tok/s. Zero when the day has no measured seconds."""
    if seconds <= 0:
        return 0.0
    return tokens / seconds


def _median(samples: list[float]) -> float:
    """Median of a day's TTFT samples. Even counts average the two central values."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float(ordered[mid - 1] + ordered[mid]) / 2.0


def _delta_samples(current: list[float], previous: list[float]) -> list[float]:
    """Samples appended since ``previous`` was snapshotted.

    The state file only appends. When the new list still starts with the
    previous one, the tail is the day. A replaced list (state reset) is the
    whole window.
    """
    if not current:
        return []
    if len(current) >= len(previous) and current[: len(previous)] == previous:
        return list(current[len(previous) :])
    return list(current)


def _top_models_by_answer_volume(
    tokens_by_model: dict[str, Any],
    seconds_by_model: dict[str, Any],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Highest answer-token models, each with its token-weighted answer rate."""
    rows: list[dict[str, Any]] = []
    for model, raw_tokens in tokens_by_model.items():
        try:
            tokens = float(raw_tokens)
            seconds = float(seconds_by_model.get(model, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if tokens <= 0:
            continue
        rows.append(
            {
                "model": str(model),
                "answer_tokens": int(tokens),
                "answer_tokens_per_second": _weighted_rate(tokens, seconds),
            }
        )
    rows.sort(key=lambda row: (-int(row["answer_tokens"]), str(row["model"])))
    return rows[:limit]


class NotificationScheduler:
    """
    APScheduler-based daily summary trigger.

    Fires a SummaryEvent at a configured hour (default: 09:00 UTC) each day,
    pulling request counts and backend health from the pipeline's live state.
    Gracefully degrades if APScheduler is not installed.
    """

    def __init__(self, dispatcher: NotificationDispatcher) -> None:
        self._dispatcher = dispatcher
        self._scheduler = AsyncIOScheduler() if APSCHEDULER_AVAILABLE else None
        self._enabled = APSCHEDULER_AVAILABLE and os.environ.get(
            "ALERT_SUMMARY_ENABLED", "true"
        ).lower() in ("true", "1", "yes")

    def start(self) -> None:
        if not self._enabled:
            if not APSCHEDULER_AVAILABLE:
                logger.info(
                    "NotificationScheduler: APScheduler not installed — daily summaries disabled"
                )
            else:
                logger.info("NotificationScheduler: daily summaries disabled via env")
            return

        # Initialize the baseline snapshot on startup.
        # Without this, the first daily summary computes deltas against zero,
        # showing cumulative totals since the container started instead of
        # just the previous day's activity.
        self._init_baseline_snapshot()

        hour = int(os.environ.get("ALERT_SUMMARY_HOUR", "9"))
        timezone = os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC")

        self._scheduler.add_job(  # type: ignore[union-attr]
            self._send_daily_summary,
            CronTrigger(hour=hour, minute=0, timezone=timezone),
            id="daily_summary",
            replace_existing=True,
        )
        self._scheduler.start()  # type: ignore[union-attr]
        logger.info(
            "NotificationScheduler: daily summary scheduled at %02d:00 %s",
            hour,
            timezone,
        )

    def _init_baseline_snapshot(self) -> None:
        """Capture current cumulative metrics as the baseline for delta computation.

        Called once at startup. The first daily summary will compute deltas
        from this baseline, showing only activity since the pipeline started
        (or since the last summary, if one already ran).

        Reads from the aggregated state file (merged across all workers)
        rather than per-worker in-memory counters.
        """
        if _SNAPSHOT_FILE.exists():
            logger.info(
                "NotificationScheduler: baseline snapshot already exists on disk — skipping init"
            )
            return

        try:
            state = _load_aggregated_state()
            baseline = _snapshot_from_state(state)
            _save_snapshot(baseline)
            req_count = baseline.get("request_count", {})
            logger.info(
                "NotificationScheduler: baseline snapshot initialized at startup "
                "(%d total requests across %d workspaces)",
                sum(req_count.values()) if req_count else 0,
                len(req_count),
            )
        except Exception:
            logger.warning(
                "NotificationScheduler: failed to initialize baseline snapshot", exc_info=True
            )

    def stop(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("NotificationScheduler: stopped")

    async def _send_daily_summary(self) -> None:
        """Build and dispatch a daily summary from live pipeline metrics.

        Computes deltas against the previous day's snapshot so the summary
        shows only yesterday's activity, not cumulative totals since startup.
        """
        if _registry_ref is None:
            logger.warning("NotificationScheduler: dispatcher not attached")
            return

        # Cooldown check: all uvicorn workers share /tmp, so this prevents
        # duplicate sends when PIPELINE_WORKERS > 1 (all workers fire at the
        # same cron moment; only the first to write the lockfile proceeds).
        now_ts = time.time()
        try:
            if _COOLDOWN_FILE.exists():
                last_sent = float(_COOLDOWN_FILE.read_text().strip())
                if now_ts - last_sent < _COOLDOWN_SECONDS:
                    logger.debug(
                        "Daily summary skipped: sent %.1f hours ago (cooldown active)",
                        (now_ts - last_sent) / 3600,
                    )
                    return
        except (ValueError, OSError):
            pass

        # First to acquire the lock writes its timestamp; others see it and skip.
        # Atomic-ish on POSIX: unlink+write is safe for our purposes.
        try:
            _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
            _COOLDOWN_FILE.write_text(str(int(now_ts)))
        except OSError:
            pass

        # Read current stats from the aggregated state file (merged across all
        # workers). In-memory counters are per-worker and would miss requests
        # handled by sibling workers.
        state = _load_aggregated_state()

        now = datetime.now(UTC)
        report_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # Snapshot current cumulative metrics
        healthy = 0
        total_backends = 0

        if _registry_instance is not None:
            try:
                total_backends = len(_registry_instance._backends)
                healthy = len([b for b in _registry_instance._backends.values() if b.healthy])
            except Exception:
                pass

        current_snapshot = _snapshot_from_state(state)

        # Load previous snapshot and compute deltas
        prev = _load_snapshot()

        prev_request_count: dict[str, int] = prev.get("request_count", {})
        prev_rt_ms: float = float(prev.get("total_response_time_ms", 0.0))
        prev_inp: int = int(prev.get("total_input_tokens", 0))
        prev_out: int = int(prev.get("total_output_tokens", 0))
        prev_by_model: dict[str, int] = prev.get("req_count_by_model", {})
        prev_by_error: dict[str, int] = prev.get("req_count_by_error", {})
        prev_samples = prev.get("ttft_samples") or []
        if not isinstance(prev_samples, list):
            prev_samples = []

        daily_requests = _delta_dict(current_snapshot["request_count"], prev_request_count)
        daily_total = sum(daily_requests.values())
        # Exclude bench-* workspaces from averages (cold model loads inflate response time).
        # Decode/answer/TTFT already omit bench-* at record time.
        daily_real_total = sum(v for k, v in daily_requests.items() if not k.startswith("bench-"))
        daily_rt_ms = _delta(current_snapshot["total_response_time_ms"], prev_rt_ms)
        daily_inp = _delta(current_snapshot["total_input_tokens"], prev_inp)
        daily_out = _delta(current_snapshot["total_output_tokens"], prev_out)
        daily_by_model = _delta_dict(current_snapshot["req_count_by_model"], prev_by_model)
        daily_by_error = _delta_dict(current_snapshot["req_count_by_error"], prev_by_error)
        daily_decode_tokens = float(
            _delta(current_snapshot["decode_tokens"], float(prev.get("decode_tokens", 0.0)))
        )
        daily_decode_seconds = float(
            _delta(current_snapshot["decode_seconds"], float(prev.get("decode_seconds", 0.0)))
        )
        daily_answer_tokens = float(
            _delta(current_snapshot["answer_tokens"], float(prev.get("answer_tokens", 0.0)))
        )
        daily_answer_seconds = float(
            _delta(current_snapshot["answer_seconds"], float(prev.get("answer_seconds", 0.0)))
        )
        daily_ttft = _delta_samples(current_snapshot["ttft_samples"], prev_samples)
        daily_answer_tokens_by_model = _delta_dict(
            current_snapshot["answer_tokens_by_model"],
            prev.get("answer_tokens_by_model") or {},
        )
        daily_answer_seconds_by_model = _delta_dict(
            current_snapshot["answer_seconds_by_model"],
            prev.get("answer_seconds_by_model") or {},
        )

        # Guard: if both current state AND previous snapshot are empty, the state was
        # wiped (container recreation). Skip the empty summary — save current as new
        # baseline instead so tomorrow's summary has a valid delta.
        current_total = (
            sum(current_snapshot["request_count"].values())
            if current_snapshot["request_count"]
            else 0
        )
        prev_total = sum(prev_request_count.values()) if prev_request_count else 0
        if daily_total == 0 and current_total == 0 and prev_total == 0:
            _save_snapshot(current_snapshot)
            logger.info(
                "Daily summary skipped: state file empty (likely container restart). "
                "Snapshot reset for next summary."
            )
            return

        # Guard: if previous snapshot was empty but current has data, the snapshot
        # was wiped (container restart, /tmp lost). The delta would show cumulative
        # totals, not yesterday's activity. Skip, reset snapshot.
        if prev_total == 0 and current_total > 0 and not prev:
            _save_snapshot(current_snapshot)
            logger.info(
                "Daily summary skipped: previous snapshot missing but state has %d "
                "requests (container restart detected). Snapshot reset.",
                current_total,
            )
            return

        # Read persona usage from aggregated state file
        persona_usage: dict[str, int] = {}
        try:
            persona_raw = state.get("persona_usage_raw", {})
            for persona, models in persona_raw.items():
                persona_usage[persona] = sum(models.values())
        except Exception:
            pass

        # Token-weighted rates: sum of tokens / sum of seconds over the day.
        # The deprecated unweighted mean (total_tps / request_tps_count) is not read.
        decode_tps = _weighted_rate(daily_decode_tokens, daily_decode_seconds)
        answer_tps = _weighted_rate(daily_answer_tokens, daily_answer_seconds)
        ttft_median = _median(daily_ttft)
        avg_response_ms = daily_rt_ms / daily_real_total if daily_real_total > 0 else 0.0

        # Import SummaryEvent here to avoid circular import
        from portal.platform.inference.notifications.events import SummaryEvent

        event = SummaryEvent(
            timestamp=now,
            report_date=report_date,
            total_requests=daily_total,
            requests_by_workspace=daily_requests,
            healthy_backends=healthy,
            total_backends=total_backends,
            uptime_seconds=now.timestamp() - _startup_time if _startup_time else 0.0,
            # Extended metrics. avg_tokens_per_second keeps the decode rate under the old name.
            requests_by_model=daily_by_model,
            avg_tokens_per_second=decode_tps,
            decode_tokens_per_second=decode_tps,
            answer_tokens_per_second=answer_tps,
            ttft_median_seconds=ttft_median,
            top_models_by_volume=_top_models_by_answer_volume(
                daily_answer_tokens_by_model,
                daily_answer_seconds_by_model,
            ),
            total_input_tokens=int(daily_inp),
            total_output_tokens=int(daily_out),
            avg_response_time_ms=avg_response_ms,
            # Error metrics
            errors_by_type=daily_by_error,
            total_errors=sum(daily_by_error.values()),
            peak_concurrent=current_snapshot["peak_concurrent"],
            persona_usage=persona_usage,
        )

        await _registry_ref.dispatch(event)

        # Save current snapshot for tomorrow's delta computation
        _save_snapshot(current_snapshot)

        logger.info(
            "Daily summary dispatched for %s: %d requests across %d workspaces, "
            "decode tok/s=%.1f, answer tok/s=%.1f, ttft median=%.2fs, avg response=%.0fms",
            report_date,
            daily_total,
            len(daily_requests),
            decode_tps,
            answer_tps,
            ttft_median,
            avg_response_ms,
        )

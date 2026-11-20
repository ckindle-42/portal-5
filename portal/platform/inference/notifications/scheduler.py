"""Portal 5 — Notification scheduler for daily usage summaries."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    from portal.platform.inference.notifications.events import SummaryEvent

logger = logging.getLogger(__name__)

# Cooldown file: prevents duplicate sends when PIPELINE_WORKERS > 1.
# All uvicorn workers share /tmp (in-memory tmpfs), so they coordinate via this file.
_COOLDOWN_FILE = Path("/tmp/.portal_daily_summary_sent")
_COOLDOWN_SECONDS = 23 * 3600  # 23 hours — staggered send on restart is fine

# Snapshot file: legacy fallback for metrics state without calendar-day buckets.
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

    Extended stats are read from the merged metrics state at send time.
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
    """Copy cumulative counters for the legacy delta fallback."""
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


def _summary_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC"))
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("UTC")


def _summary_date(today: bool) -> str:
    local_date = datetime.now(_summary_timezone()).date()
    if not today:
        local_date -= timedelta(days=1)
    return local_date.isoformat()


def _summary_metrics(
    state: dict[str, Any], current: dict[str, Any], previous: dict[str, Any], report_date: str
) -> dict[str, Any]:
    if state.get("daily_metrics_version") == 1:
        source = (state.get("daily_metrics") or {}).get(report_date) or {}
        metrics = dict(source) if isinstance(source, dict) else {}
        metrics["requests_by_client"] = dict(metrics.get("requests_by_client") or {})
        metrics["request_count"] = dict(metrics.get("request_count") or {})
        metrics["total_response_time_ms"] = float(metrics.get("total_response_time_ms", 0.0))
        metrics["ttft_samples"] = list(metrics.get("ttft_samples") or [])
        metrics["requests_by_model"] = dict(metrics.get("req_count_by_model") or {})
        metrics["errors_by_type"] = dict(metrics.get("req_count_by_error") or {})
        for name in (
            "total_input_tokens",
            "total_output_tokens",
            "decode_tokens",
            "decode_seconds",
            "answer_tokens",
            "answer_seconds",
        ):
            metrics[name] = float(metrics.get(name, 0.0))
        metrics["answer_tokens_by_model"] = dict(metrics.get("answer_tokens_by_model") or {})
        metrics["answer_seconds_by_model"] = dict(metrics.get("answer_seconds_by_model") or {})
        metrics["persona_usage"] = dict(metrics.get("persona_usage") or {})
        return metrics

    request_count = _delta_dict(current["request_count"], previous.get("request_count", {}))
    persona_usage = {
        persona: sum(models.values())
        for persona, models in (state.get("persona_usage_raw") or {}).items()
    }
    return {
        "request_count": request_count,
        "requests_by_client": {},
        "total_response_time_ms": _delta(
            current["total_response_time_ms"], float(previous.get("total_response_time_ms", 0.0))
        ),
        "total_input_tokens": _delta(
            current["total_input_tokens"], int(previous.get("total_input_tokens", 0))
        ),
        "total_output_tokens": _delta(
            current["total_output_tokens"], int(previous.get("total_output_tokens", 0))
        ),
        "requests_by_model": _delta_dict(
            current["req_count_by_model"], previous.get("req_count_by_model", {})
        ),
        "errors_by_type": _delta_dict(
            current["req_count_by_error"], previous.get("req_count_by_error", {})
        ),
        "decode_tokens": _delta(
            current["decode_tokens"], float(previous.get("decode_tokens", 0.0))
        ),
        "decode_seconds": _delta(
            current["decode_seconds"], float(previous.get("decode_seconds", 0.0))
        ),
        "answer_tokens": _delta(
            current["answer_tokens"], float(previous.get("answer_tokens", 0.0))
        ),
        "answer_seconds": _delta(
            current["answer_seconds"], float(previous.get("answer_seconds", 0.0))
        ),
        "ttft_samples": _delta_samples(current["ttft_samples"], previous.get("ttft_samples") or []),
        "answer_tokens_by_model": _delta_dict(
            current["answer_tokens_by_model"], previous.get("answer_tokens_by_model") or {}
        ),
        "answer_seconds_by_model": _delta_dict(
            current["answer_seconds_by_model"], previous.get("answer_seconds_by_model") or {}
        ),
        "persona_usage": persona_usage,
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


def _build_summary_event(
    state: dict[str, Any], report_date: str, now: datetime
) -> SummaryEvent | None:
    from portal.platform.inference.notifications.events import SummaryEvent

    current = _snapshot_from_state(state)
    previous = _load_snapshot()
    metrics = _summary_metrics(state, current, previous, report_date)
    daily_requests = metrics["request_count"]
    daily_total = sum(daily_requests.values())
    exact_day = state.get("daily_metrics_version") == 1
    current_total = sum(current["request_count"].values())
    previous_total = sum(previous.get("request_count", {}).values())
    if not exact_day and daily_total == 0 and current_total == 0 and previous_total == 0:
        _save_snapshot(current)
        logger.info("Daily summary skipped: no persisted metrics state")
        return None
    if not exact_day and previous_total == 0 and current_total > 0 and not previous:
        _save_snapshot(current)
        logger.info("Daily summary skipped: previous snapshot missing; initializing baseline")
        return None

    real_requests = sum(v for k, v in daily_requests.items() if not k.startswith("bench-"))
    response_ms = float(metrics["total_response_time_ms"])
    decode_tps = _weighted_rate(float(metrics["decode_tokens"]), float(metrics["decode_seconds"]))
    answer_tps = _weighted_rate(float(metrics["answer_tokens"]), float(metrics["answer_seconds"]))
    backends = getattr(_registry_instance, "_backends", {}) if _registry_instance else {}
    persona_usage = metrics["persona_usage"]
    return SummaryEvent(
        timestamp=now,
        report_date=report_date,
        total_requests=daily_total,
        requests_by_workspace=daily_requests,
        requests_by_client=metrics["requests_by_client"],
        healthy_backends=sum(1 for backend in backends.values() if backend.healthy),
        total_backends=len(backends),
        uptime_seconds=now.timestamp() - _startup_time if _startup_time else 0.0,
        requests_by_model=metrics["requests_by_model"],
        avg_tokens_per_second=decode_tps,
        decode_tokens_per_second=decode_tps,
        answer_tokens_per_second=answer_tps,
        ttft_median_seconds=_median(metrics["ttft_samples"]),
        ttft_sample_count=len(metrics["ttft_samples"]),
        top_models_by_volume=_top_models_by_answer_volume(
            metrics["answer_tokens_by_model"], metrics["answer_seconds_by_model"]
        ),
        total_input_tokens=int(metrics["total_input_tokens"]),
        total_output_tokens=int(metrics["total_output_tokens"]),
        avg_response_time_ms=response_ms / real_requests if real_requests else 0.0,
        errors_by_type=metrics["errors_by_type"],
        total_errors=sum(metrics["errors_by_type"].values()),
        peak_concurrent=current["peak_concurrent"],
        persona_usage=persona_usage,
    )


class NotificationScheduler:
    """
    APScheduler-based daily summary trigger.

    Fires a SummaryEvent at the configured local hour each day.
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

        # Keep a baseline for state files written before calendar-day buckets.
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
        """Capture current cumulative metrics for the legacy delta fallback.

        Called once at startup when no persisted snapshot exists.

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

    async def _send_daily_summary(
        self, *, force: bool = False, report_today: bool = False
    ) -> dict[str, Any] | None:
        """Build and dispatch a daily summary from live pipeline metrics.

        Reads date-bucketed metrics, with snapshots retained for older state files.
        """
        if _registry_ref is None:
            logger.warning("NotificationScheduler: dispatcher not attached")
            return {"status": "unavailable"}

        # Cooldown check: all uvicorn workers share /tmp, so this prevents
        # duplicate sends when PIPELINE_WORKERS > 1 (all workers fire at the
        # same cron moment; only the first to write the lockfile proceeds).
        now_ts = time.time()
        if not force:
            try:
                if _COOLDOWN_FILE.exists():
                    last_sent = float(_COOLDOWN_FILE.read_text().strip())
                    if now_ts - last_sent < _COOLDOWN_SECONDS:
                        logger.debug("Daily summary skipped: cooldown active")
                        return {"status": "cooldown"}
            except (ValueError, OSError):
                pass

        if not force:
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
        report_date = _summary_date(report_today)

        event = _build_summary_event(state, report_date, now)
        if event is None:
            return {"status": "uninitialized", "report_date": report_date}
        await _registry_ref.dispatch(event)
        if state.get("daily_metrics_version") != 1:
            _save_snapshot(_snapshot_from_state(state))
        logger.info(
            "Daily summary dispatched for %s: %d requests across %d workspaces",
            report_date,
            event.total_requests,
            len(event.requests_by_workspace),
        )
        return {
            "status": "dispatched",
            "report_date": report_date,
            "total_requests": event.total_requests,
            "requests_by_client": event.requests_by_client,
        }

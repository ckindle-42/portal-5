"""Public metrics interface for the tool preselector (§1.8).

The six Prometheus collectors are declared in
``portal.platform.inference.router.metrics`` (the single sole-owner
CollectorRegistry — see that module's docstring); this module re-exports
them via the ``record_*`` helper functions the rest of ``tool_preselect``
and the router call, so no other file imports the raw Counter/Histogram
objects directly.
"""

from __future__ import annotations

import logging

from portal.platform.inference.router.metrics import (
    toolpreselect_auto_disabled_total,
    toolpreselect_calls_total,
    toolpreselect_duration_seconds,
    toolpreselect_miss_total,
    toolpreselect_tools_available,
    toolpreselect_tools_selected,
)

logger = logging.getLogger(__name__)


def record_preselect_call(
    workspace_id: str,
    outcome: object,
    tools_available: int,
    tools_selected: int,
) -> None:
    """Record one preselect() call's outcome + sizing (§5.1 call site).

    ``outcome`` is a ``PreselectOutcome`` (imported lazily to avoid a
    metrics<->preselector import cycle); ``outcome.reason`` is the
    Prometheus label.

    Failure handling: bare except -> logger.debug. A metrics failure
    must never break the request path (same discipline as
    ``_record_response_time`` in router/metrics.py).
    """
    try:
        reason = getattr(outcome, "reason", "unknown")
        toolpreselect_calls_total.labels(workspace=workspace_id, outcome=reason).inc()
        toolpreselect_duration_seconds.labels(workspace=workspace_id).observe(
            getattr(outcome, "latency_ms", 0) / 1000.0
        )
        toolpreselect_tools_available.labels(workspace=workspace_id).observe(tools_available)
        toolpreselect_tools_selected.labels(workspace=workspace_id).observe(tools_selected)
        logger.debug(
            "preselect ws=%s tools_in=%d tools_out=%d outcome=%s latency_ms=%d",
            workspace_id,
            tools_available,
            tools_selected,
            reason,
            getattr(outcome, "latency_ms", 0),
        )
        if reason != "ok":
            logger.warning(
                "preselect fallback ws=%s outcome=%s tools_in=%d",
                workspace_id,
                reason,
                tools_available,
            )
    except Exception as e:
        logger.debug("record_preselect_call metrics failed: %s", e)


def record_miss(workspace_id: str) -> None:
    """A primary-model tool call fell outside the preselected set."""
    try:
        toolpreselect_miss_total.labels(workspace=workspace_id).inc()
    except Exception as e:
        logger.debug("record_miss metrics failed: %s", e)


def record_auto_disabled(workspace_id: str) -> None:
    """Self-healing auto-disable fired for this workspace."""
    try:
        toolpreselect_auto_disabled_total.labels(workspace=workspace_id).inc()
        logger.info("preselect auto-disabled ws=%s", workspace_id)
    except Exception as e:
        logger.debug("record_auto_disabled metrics failed: %s", e)

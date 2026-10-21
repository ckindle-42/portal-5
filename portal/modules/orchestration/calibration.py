"""Projection helpers for the orchestration arm's Gate C calibration hook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import Bite, TaskPlan


@dataclass(frozen=True)
class CalibrationProjection:
    pass_probability: float
    expected_seconds: float
    remaining_bites: int


def project_remaining(
    bites: tuple[Bite, ...],
    completed_ids: set[str],
    rates: dict[str, Any],
) -> CalibrationProjection:
    """Project remaining success odds and wall time from WFE seat rates."""
    probability = 1.0
    seconds = 0.0
    remaining = [bite for bite in bites if bite.bite_id not in completed_ids]
    if not remaining:
        return CalibrationProjection(1.0, 0.0, 0)
    for bite in remaining:
        seat_rates = rates.get(bite.discipline, {}).get(bite.model)
        if not isinstance(seat_rates, dict):
            raise ValueError(f"missing WFE rates for {bite.discipline}/{bite.model}")
        pass_rate = seat_rates.get("pass_probability")
        mean_seconds = seat_rates.get("mean_seconds")
        if not isinstance(pass_rate, (int, float)) or not 0 <= pass_rate <= 1:
            raise ValueError(f"invalid pass probability for {bite.discipline}/{bite.model}")
        if not isinstance(mean_seconds, (int, float)) or mean_seconds < 0:
            raise ValueError(f"invalid mean seconds for {bite.discipline}/{bite.model}")
        probability *= float(pass_rate)
        seconds += float(mean_seconds)
    return CalibrationProjection(probability, seconds, len(remaining))


def calibration_status(
    config: dict[str, Any],
    plan: TaskPlan,
    completed_ids: set[str],
) -> tuple[CalibrationProjection | None, bool]:
    """Return the projection and whether it crosses the configured pause threshold."""
    threshold = config.get("minimum_pass_probability")
    if threshold is None:
        return None, False
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("calibration.minimum_pass_probability must be null or between 0 and 1")
    projection = project_remaining(plan.bites, completed_ids, config.get("rates_by_discipline", {}))
    return projection, projection.pass_probability < threshold

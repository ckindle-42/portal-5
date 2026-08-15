"""Historical emergent-miss -> Gap adapter retained for MUT input.

The retired growth-loop consumer is gone. ``bully.mutation`` still reuses
``gaps_from_trajectory`` to turn proven non-synthetic misses into typed
mutation opportunities; ``feed_emergent_gaps`` remains a compatibility read
adapter for historical capability-graph consumers.
"""

from __future__ import annotations

import time

from portal.modules.security.core.capability_graph import CapabilityGraph, Gap
from portal.modules.security.core.trajectory_score import StepRecord, TrajectoryVerdict

# Detection reason codes that constitute a real red-only miss worth a draft.
_MISS_DETECTION = {"DETECTION_NO_HIT", "DETECTION_MISSING"}


def _step_technique(step: StepRecord) -> str:
    """Technique tag for the step. Emergent capabilities carry a technique tag;
    fall back to the capability id so the gap is still addressable."""
    return getattr(step, "technique_id", "") or f"cap:{step.capability_id}"


def gaps_from_trajectory(verdict: TrajectoryVerdict, *, trajectory_id: str) -> list[Gap]:
    """Emit a RED_ONLY Gap per landed-but-undetected step.

    Synthetic steps are excluded — a synthetic miss cannot prove a detection
    gap (mirrors the never-PROVEN invariant on the blue side).
    """
    out: list[Gap] = []
    now = time.time()
    for step in verdict.steps:
        if step.used_synthetic:
            continue
        if step.red_status != "RED_LANDED":
            continue
        if step.detection_status not in _MISS_DETECTION:
            continue
        technique = _step_technique(step)
        procedure_id = f"emergent-{trajectory_id}-{step.step_id}"
        out.append(
            Gap(
                gap_id=f"gap-{procedure_id}-{technique}",
                procedure_id=procedure_id,
                technique_id=technique,
                axes={
                    "red": step.red_status,
                    "telemetry": "TELEMETRY_OBSERVED",
                    "detection": step.detection_status,
                    "response": "RESPONSE_NOT_TESTED",
                },
                summary="RED_ONLY",
                reason_codes=[step.red_status, step.detection_status],
                created_at=now,
            )
        )
    return out


def feed_emergent_gaps(
    graph: CapabilityGraph, verdict: TrajectoryVerdict, *, trajectory_id: str
) -> list[Gap]:
    """Add gaps from a trajectory to the retained historical graph readout."""
    gaps = gaps_from_trajectory(verdict, trajectory_id=trajectory_id)
    for gap in gaps:
        graph.add_gap(gap)
    return gaps

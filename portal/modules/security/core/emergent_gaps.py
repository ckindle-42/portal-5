"""Emergent-miss -> Gap feed (DESIGN_EMERGENT_LAB_AGENT_V2 Δ4 / Slice 3.1).

Turns off-script trajectory misses (RED_LANDED but detection absent) into the
same Gap objects growth_loop already consumes. Only the gap *source* is new —
run_growth_loop / propose_draft / prove_draft / surface_for_confirm are reused
unchanged, and promotion stays confirm-only.

Wiring: run_growth_loop(graph) scans graph.gaps directly (it takes no gap-list
parameter) — the same way the scripted RED_ONLY feed already works via
update_graph_from_episode's `graph.gaps[gap_id] = gap`. feed_emergent_gaps
follows that exact idiom, so it is an additional gap *source* into the same
graph, not a change to run_growth_loop itself.
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
    """Add gaps_from_trajectory's output into `graph.gaps` — the same
    `graph.gaps[gap_id] = gap` idiom the scripted RED_ONLY feed already uses
    (capability_graph.update_graph_from_episode), so a subsequent
    `run_growth_loop(graph)` call picks these up as an additional gap source
    without run_growth_loop itself changing.
    """
    gaps = gaps_from_trajectory(verdict, trajectory_id=trajectory_id)
    for gap in gaps:
        graph.add_gap(gap)
    return gaps

"""Trajectory-grounded scoring (DESIGN_EMERGENT_LAB_AGENT_V2 Δ3).

Composes a trajectory-level verdict from per-landed-step episodes + an objective
oracle. Deterministic; no model touches it. The load-bearing invariant: a
trajectory whose objective was reached via ANY synthetic-derived step is NEVER
PROVEN — the same rule episode.py enforces per-run, lifted to the trajectory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portal.modules.security.core.objective_oracles import OBJECTIVE_CLASS_ORACLE
from portal.modules.security.core.oracles import ORACLES

TRAJECTORY_VERDICTS = ("PROVEN", "FAILED", "INDETERMINATE", "UNAVAILABLE")


@dataclass
class StepRecord:
    """One landed step within a trajectory. `used_synthetic` mirrors episode.py."""

    step_id: str
    capability_id: str
    red_status: str  # reuses episode REASON_CODES["red"]
    detection_status: str  # reuses episode REASON_CODES["detection"]
    used_synthetic: bool = False


@dataclass
class TrajectoryVerdict:
    objective_class: str
    verdict: str  # one of TRAJECTORY_VERDICTS
    objective_reached: bool  # oracle result against final observed state
    synthetic_present: bool
    landed_steps: int
    detail: str = ""
    steps: list[StepRecord] = field(default_factory=list)


def _objective_reached(objective_class: str, observations: dict) -> bool:
    """Path-independent: verified only by an objective-state oracle vs lab state."""
    oracle_id = OBJECTIVE_CLASS_ORACLE.get(objective_class)
    if oracle_id is None:
        return False  # unknown objective class => never reached (never assumed)
    oracle = ORACLES.get(oracle_id)
    if oracle is None:
        return False
    return bool(oracle.check(finding={}, lab_output="", observations=observations))


def score_trajectory(
    objective_class: str,
    steps: list[StepRecord],
    final_observations: dict,
) -> TrajectoryVerdict:
    """Deterministic trajectory verdict.

    Order of checks preserves honesty precedence:
      1. no landed steps                     -> UNAVAILABLE
      2. objective-state oracle says reached
           2a. any synthetic step present    -> INDETERMINATE (synthetic never PROVEN)
           2b. clean                          -> PROVEN
      3. landed steps but objective not reached -> FAILED
    """
    landed = [s for s in steps if s.red_status == "RED_LANDED"]
    synthetic_present = any(s.used_synthetic for s in steps)
    reached = _objective_reached(objective_class, final_observations)

    if not landed:
        verdict, detail = "UNAVAILABLE", "no landed steps"
    elif reached and synthetic_present:
        verdict, detail = "INDETERMINATE", "objective reached but a synthetic step is present"
    elif reached:
        verdict, detail = "PROVEN", "objective state verified by oracle, no synthetic steps"
    else:
        verdict, detail = "FAILED", "landed steps but objective state not reached"

    return TrajectoryVerdict(
        objective_class=objective_class,
        verdict=verdict,
        objective_reached=reached,
        synthetic_present=synthetic_present,
        landed_steps=len(landed),
        detail=detail,
        steps=list(steps),
    )

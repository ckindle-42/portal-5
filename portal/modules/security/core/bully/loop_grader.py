"""bully.loop_grader -- the reform organ, wired to the loop's contract.

This is the reintegration seam. The reform grading line (unit model, field-
role intake, pyramid-levelled behavioural matching) has until now emitted its
own vocabulary (`COUSIN_CANDIDATE`/`NOVEL_NOTABLE`/`INSUFFICIENT_VIEW`) into a
standalone script the orchestrator never called. The product is the *loop*:
a graded relation must enter the loop's own `CousinAssessment` contract so it
flows through the parts that already exist -- the discovery scoreboard, the
BIN promotion gate, the investigation arm (intent/context), the detection
handoff, and the training flywheel.

`grade_for_loop` produces a `CousinAssessment` with `relationship` in the
loop's RELATIONSHIPS vocabulary, so `orchestrator._analyzing` can call it in
place of `cousin_engine.grade` with no downstream change. The mapping is
*pyramid-aware*: the relationship is decided by the level at which the match
holds, which is the whole correction --

    L3 behavioural match, close     -> SAME       (a known behaviour, robustly)
    L3 behavioural match, partial   -> SIMILAR    (the cousin -- the product)
    behaviour seen, matches nothing -> ANOMALOUS_UNCLASSIFIED (bubble to analyst)
    only L1/L2 agreement            -> NEW / DIFFERENT (fragile; not a behaviour cousin)
    nothing observable              -> ANOMALOUS_UNCLASSIFIED with INDETERMINATE response,
                                       NOT a false DIFFERENT (Q1: instrument blindness is loud)

Crucially, `ANOMALOUS_UNCLASSIFIED` -- the concept's primary product per
scoreboard.py -- is reserved for the honest case "I see real behaviour and it
resembles something, but not closely enough to name": a bubbled unknown-but-
similar, which is exactly what the analyst must see. It is never emitted for
an extraction failure (that is INDETERMINATE) and never for pure noise (that
is DIFFERENT at L1).

Pure compute over injected data (COLD). Emits the loop contract; the caller
records it via the existing `store.record_cousin` and `DecisionEvent` path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import (
    pyramid,  # sibling module in the same package
    series_cousin,
)

ALGORITHM_VERSION = "loop-grader-v1"

# R.3c: series-alignment relation -> loop RELATIONSHIPS. Series alignment is
# WHAT decides cousinhood when a behavioural series is available (an entity's
# stitched cross-source timeline vs the known-technique library); pyramid
# match_level (grade_for_loop, above) still qualifies HOW ROBUST the match is
# when only a point signature is available (no series).
_SERIES_RELATION_MAP: dict[str, str] = {
    "EXACT": "SAME",
    "COUSIN": "SIMILAR",
    "NOVEL": "ANOMALOUS_UNCLASSIFIED",
    "NONE": "DIFFERENT",
}

# Distance bands, expressed on the SAME normalized scale as cousin_relation,
# but now conditioned on pyramid level. Recorded on every assessment; a change
# is a re-baseline.
SAME_MAX_DISTANCE = 0.15
SIMILAR_MAX_DISTANCE = 0.60
# A behavioural spine must be at least this long to count as a real choke
# point rather than a single coincidental shared class.
MIN_SPINE_FOR_BEHAVIOR = 2


@dataclass(frozen=True)
class LoopGrade:
    """Everything the loop needs, plus the pyramid evidence that justifies the
    relationship -- carried in `explanation` so the scoreboard, BIN and handoff
    can all see *why* and *how robustly* this was graded."""

    relationship: str  # a RELATIONSHIPS value
    defense_response: str  # a RESPONSES value
    composite: float  # graded distance (scoreboard's discovery axis)
    match_level: str  # pyramid level the relation holds at
    robustness: float
    anchor_id: str | None
    explanation: dict[str, Any]

    def to_assessment_kwargs(self) -> dict[str, Any]:
        """Shape for `contracts.CousinAssessment(**kwargs)` -- the loop's DTO.
        Kept as a dict so this module carries no import-time dependency on the
        contracts module's exact constructor, which the task file wires."""
        return {
            "relationship": self.relationship,
            "defense_response": self.defense_response,
            "explanation": {
                **self.explanation,
                "composite": self.composite,
                "match_level": self.match_level,
                "robustness": self.robustness,
                "anchor_id": self.anchor_id,
                "grader": ALGORITHM_VERSION,
            },
        }


def _defense_response(observable: bool, telemetry_healthy: bool) -> str:
    if not observable:
        return "INDETERMINATE"
    return "COVERED" if telemetry_healthy else "NEAR_MISS"


def grade_for_loop(
    subject_features: list[pyramid.LeveledFeature],
    best_anchor_id: str | None,
    anchor_features: list[pyramid.LeveledFeature] | None,
    *,
    distance: float | None,
    telemetry_healthy: bool = True,
    same_max: float = SAME_MAX_DISTANCE,
    similar_max: float = SIMILAR_MAX_DISTANCE,
    min_spine: int = MIN_SPINE_FOR_BEHAVIOR,
) -> LoopGrade:
    """Map a pyramid-levelled relation onto the loop's CousinAssessment vocab.

    The decision is level-first, distance-second: *where* the match holds
    determines the relationship class; *how close* it is refines SAME vs
    SIMILAR within a behavioural match.
    """
    observable = bool(subject_features)

    # Instrument blindness is loud and is NOT a discovery (Q1).
    if not observable:
        return LoopGrade(
            relationship="ANOMALOUS_UNCLASSIFIED",
            defense_response="INDETERMINATE",
            composite=0.0,
            match_level="",
            robustness=0.0,
            anchor_id=None,
            explanation={"reason": "insufficient_view:no_observable_features"},
        )

    if not anchor_features or distance is None:
        # We saw real behaviour but nothing in the library relates -- the
        # honest "I see something" the analyst must get.
        return LoopGrade(
            relationship="ANOMALOUS_UNCLASSIFIED",
            defense_response=_defense_response(True, telemetry_healthy),
            composite=1.0,
            match_level="",
            robustness=0.0,
            anchor_id=None,
            explanation={"reason": "novel:behaviour_matches_no_anchor"},
        )

    ml = pyramid.match_level(subject_features, anchor_features)
    spine = ml.behavior_overlap
    behavioural = ml.holds_at_behavior and len(spine) >= min_spine

    explanation: dict[str, Any] = {
        "match": ml.to_dict(),
        "behavioural_spine": list(spine),
        "distance": distance,
    }

    if behavioural:
        # A real behavioural choke point is shared. Distance now separates a
        # robustly-known behaviour (SAME) from the cousin (SIMILAR).
        if distance <= same_max:
            relationship = "SAME"
        elif distance <= similar_max:
            relationship = "SIMILAR"
        else:
            # behaviour matches but far in detail: still a cousin worth
            # bubbling, not silence.
            relationship = "SIMILAR"
        return LoopGrade(
            relationship=relationship,
            defense_response=_defense_response(True, telemetry_healthy),
            composite=distance,
            match_level=ml.level,
            robustness=ml.robustness,
            anchor_id=best_anchor_id,
            explanation=explanation,
        )

    # No behavioural agreement. Any agreement is L1/L2 -- fragile by
    # construction. This is NOT a behaviour cousin; it is at most NEW (if
    # there is real low-level signal) or DIFFERENT (if essentially nothing).
    if ml.level in (pyramid.L2_TOOL, pyramid.L1_EPHEMERAL) and distance <= similar_max:
        relationship = "NEW"
    else:
        relationship = "DIFFERENT"
    explanation["reason"] = f"fragile_match_at_{ml.level or 'none'}:not_a_behaviour_cousin"
    return LoopGrade(
        relationship=relationship,
        defense_response=_defense_response(True, telemetry_healthy),
        composite=distance,
        match_level=ml.level,
        robustness=ml.robustness,
        anchor_id=best_anchor_id if relationship == "NEW" else None,
        explanation=explanation,
    )


def grade_series_for_loop(
    observed: series_cousin.BehaviouralSeries,
    known_library: list[series_cousin.BehaviouralSeries],
    *,
    telemetry_healthy: bool = True,
    idf: dict[str, float] | None = None,
) -> LoopGrade:
    """Grade cousinhood by ordered sequence alignment (R.3c) rather than a
    point signature. `observed` is the behavioural series built from an
    entity's stitched cross-source timeline (correlation.py); `known_library`
    is the anchor library's technique series. Series alignment is WHAT decides
    the relationship; pyramid match_level (grade_for_loop) still qualifies
    robustness at the point-signature level when no series is available.

    A blank observed spine (R7 wall preserved) is loud, not a silent
    DIFFERENT -- mirrors grade_for_loop's Q1 treatment of instrument
    blindness.
    """
    if not observed.spine:
        return LoopGrade(
            relationship="ANOMALOUS_UNCLASSIFIED",
            defense_response="INDETERMINATE",
            composite=0.0,
            match_level="",
            robustness=0.0,
            anchor_id=None,
            explanation={"reason": "insufficient_view:no_observable_behavioural_series"},
        )

    result = series_cousin.decide_cousin(observed, known_library, idf=idf)
    relationship = _SERIES_RELATION_MAP[result.relation]
    robustness = pyramid.robustness(pyramid.L3_BEHAVIOR) if result.aligned_spine else 0.0
    return LoopGrade(
        relationship=relationship,
        defense_response=_defense_response(True, telemetry_healthy),
        composite=result.distance,
        match_level=pyramid.L3_BEHAVIOR if result.aligned_spine else "",
        robustness=robustness,
        anchor_id=result.known_series_id,
        explanation={
            "series": result.to_dict(),
            "reason": f"series_alignment:{result.relation.lower()}",
        },
    )

"""Synthetic stage traces prove event-to-queue attribution and twin-aware retrieval."""

from __future__ import annotations

from portal.modules.security.core.bully.artifact_graph import GradeableUnit
from portal.modules.security.core.review.contracts import (
    Outcome,
    Resemblance,
    ReviewConcern,
    ReviewResult,
)
from portal.modules.security.core.review.intake import EventView, IntakeResult, IntakeUnit
from portal.modules.security.core.review_eval.attribution import traces_for
from portal.modules.security.core.review_eval.truth import TruthItem


def window(event_id: str, unit_id: str) -> IntakeResult:
    unit = GradeableUnit(
        unit_id=unit_id,
        level="L2_ENTITY",
        artifact_ids=(f"artifact-{event_id}",),
        entities=("host=h1",),
        action_classes=("auth",),
        edge_kinds=(),
        span_seconds=0.0,
        structural_signature={"class_sequence": ["auth"]},
        vocabulary=("logon",),
        source_ids=("i:s",),
    )
    result = IntakeResult()
    result.events[event_id] = EventView(event_id, "i:s", 10.0, "event")
    result.units.append(IntakeUnit(unit, (event_id,), ("i:s",), ("logon",), "card"))
    return result


def concern(
    unit_id: str,
    *,
    anchor_id: str = "truth-anchor",
    priority: float = 0.01,
) -> ReviewConcern:
    return ReviewConcern(
        concern_id=f"concern-{unit_id}",
        unit_id=unit_id,
        level="L2_ENTITY",
        outcome=Outcome.COUSIN,
        channels=(),
        priority_p=priority,
        resembles=(Resemblance(anchor_id, "attack_episode", "known", 0.9, 0.01),),
    )


def truth(event_id: str) -> TruthItem:
    return TruthItem("botsv3:T1000", "known", (event_id,), ("truth-anchor",), "botsv3", "T1000")


def test_trace_reaches_raise_only_after_a_twin_aware_retrieval_within_budget() -> None:
    result = ReviewResult("r1", {}, concerns=[concern("u1", anchor_id="evidence-twin")])
    trace = traces_for(
        result,
        window("event-1", "u1"),
        [truth("event-1")],
        workload_b=1,
        twin_groups={"truth-anchor": "same-evidence", "evidence-twin": "same-evidence"},
    )[0]
    assert trace.last_stage == "raised"


def test_unmatched_anchor_is_read_but_not_raised_when_workload_budget_is_zero() -> None:
    result = ReviewResult("r1", {}, concerns=[concern("u1", anchor_id="other-anchor")])
    trace = traces_for(result, window("event-1", "u1"), [truth("event-1")], workload_b=0)[0]
    assert trace.last_stage == "read"


def test_a_dismissed_candidate_stops_at_retrieved() -> None:
    result = ReviewResult("r1", {}, suppressed=[concern("u1")])
    trace = traces_for(result, window("event-1", "u1"), [truth("event-1")], workload_b=1)[0]
    assert trace.last_stage == "retrieved"

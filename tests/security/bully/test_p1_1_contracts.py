"""P1.1 -- versioned boundary contracts.

Round-trip tests are the acceptance criterion: a DTO must serialize and
deserialize back to an equal value, closed enums must reject invalid
values, and the command envelope must carry every field FINAL_INTERFACES
requires.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import contracts as c


def test_command_envelope_carries_required_fields():
    env = c.CommandEnvelope.new(actor="operator:alice")
    assert env.command_id and env.idempotency_key and env.correlation_id
    assert env.actor == "operator:alice"
    assert env.expected_version is None


def test_decision_event_round_trips():
    ev = c.DecisionEvent(
        event_id=c.new_id("de"),
        hunt_id="hunt-1",
        iteration_id="hunt-1-i1",
        actor="system:orchestrator",
        kind="target_select",
        subject_id="cell-1",
        rationale="only eligible cell",
        data={"foo": "bar"},
    )
    restored = c.round_trip(ev)
    assert restored == ev


def test_decision_event_requires_rationale():
    with pytest.raises(ValueError):
        c.DecisionEvent(
            event_id=c.new_id("de"),
            hunt_id="h",
            iteration_id="i",
            actor="system:x",
            kind="target_select",
            subject_id="s",
            rationale="",
        )


def test_decision_event_rejects_unknown_kind():
    with pytest.raises(ValueError):
        c.DecisionEvent(
            event_id=c.new_id("de"),
            hunt_id="h",
            iteration_id="i",
            actor="system:x",
            kind="not_a_real_kind",
            subject_id="s",
            rationale="x",
        )


def test_recall_receipt_round_trips_even_when_empty():
    receipt = c.RecallReceipt(
        recall_id=c.new_id("rr"),
        hunt_id="hunt-1",
        query="lateral movement via wmi",
        filters={},
        source_health={"embed": "down"},
        projection_version="v1",
        embedding_version="v1",
        reranker_version=None,
        candidates=[],
        exclusions=[],
        selected_context=[],
    )
    restored = c.round_trip(receipt)
    assert restored == receipt


def test_decision_impact_rejects_unknown_change_kind():
    with pytest.raises(ValueError):
        c.DecisionImpact(
            impact_id=c.new_id("di"),
            recall_id="rr-1",
            consuming_decision_ref="de-1",
            before={},
            after={},
            cited_record_ids=[],
            change_kind="MADE_UP",
            explanation="x",
        )


def test_cousin_assessment_round_trips_with_nested_decomposition():
    assessment = c.CousinAssessment(
        assessment_id=c.new_id("ca"),
        subject_signature_id="sig-1",
        reference_signature_id="sig-0",
        candidate_set_id="cs-1",
        decomposition=c.Decomposition(
            behavior=0.1, telemetry=0.2, semantic=0.05, attack=0.0, context=0.15
        ),
        composite=0.1,
        relationship="SAME",
        nonsemantic_channels=3,
        vetoes=[],
        defense_response="COVERED",
        nearest_knowns=[("hr-1", 0.02)],
        confidence=0.9,
        completeness=1.0,
        algorithm_version="cousin-v1",
        thresholds_version="bully-cousin-thresholds-v1",
    )
    restored = c.round_trip(assessment)
    assert restored == assessment
    assert isinstance(restored.decomposition, c.Decomposition)
    assert restored.nearest_knowns == [("hr-1", 0.02)]


def test_cousin_assessment_similar_or_new_requires_two_nonsemantic_channels():
    with pytest.raises(ValueError):
        c.CousinAssessment(
            assessment_id=c.new_id("ca"),
            subject_signature_id="sig-1",
            reference_signature_id=None,
            candidate_set_id="cs-1",
            decomposition=c.Decomposition(None, None, 0.5, None, None),
            composite=0.5,
            relationship="SIMILAR",
            nonsemantic_channels=1,
            vetoes=[],
            defense_response="INDETERMINATE",
            nearest_knowns=[],
            confidence=0.4,
            completeness=0.2,
            algorithm_version="cousin-v1",
            thresholds_version="bully-cousin-thresholds-v1",
        )


@pytest.mark.parametrize(
    ("current", "target", "legal"),
    [
        ("DRAFT", "AUTHORIZED", True),
        ("AUTHORIZED", "DRAFT", False),  # never backward
        ("RECALL_READY", "TARGETED", True),
        ("TARGETED", "RECALL_READY", False),
        ("EXECUTING", "BLOCKED", True),  # any non-terminal -> BLOCKED
        ("CLOSED", "EXECUTING", False),  # terminal, sealed
        ("CLOSED", "BLOCKED", False),  # terminal, sealed even for recovery
        ("BLOCKED", "EXECUTING", False),  # resume is not a bare transition
        ("BLOCKED", "CANCELLED", True),
        ("CANCELLED", "DRAFT", False),
    ],
)
def test_hunt_stage_transition_legality(current, target, legal):
    assert c.is_legal_hunt_transition(current, target) is legal


def test_closed_enums_are_exactly_the_documented_sets():
    assert set(c.RELATIONSHIPS) == {"SAME", "SIMILAR", "NEW", "DIFFERENT", "ANOMALOUS_UNCLASSIFIED"}
    assert set(c.RESPONSES) == {"COVERED", "NEAR_MISS", "MISSED", "INDETERMINATE"}

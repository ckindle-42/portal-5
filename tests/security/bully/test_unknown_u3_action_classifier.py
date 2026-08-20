"""U.3 -- the verb-to-class seam, isolated (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from dataclasses import dataclass

from portal.modules.security.core.bully import artifact_graph as ag


def test_deterministic_classifier_is_the_default():
    graph = ag.build_graph([{"eventName": "AssumeRole", "user": "u1", "eventTime": 1.0}])
    artifact = next(iter(graph.artifacts.values()))
    assert artifact.action_class == "auth"


def test_deterministic_classifier_fails_on_unanticipated_vocabulary():
    """Documents the known seam rather than papering over it: a real
    escalation verb the table's author did not anticipate falls through to
    'other', not 'escalate'."""
    classifier = ag.DeterministicActionClassifier()
    assert classifier.classify("Add-LocalGroupMember") == "other"


@dataclass(frozen=True)
class _StubClassifier:
    """Injected classifier proving the seam is swappable without touching
    build_graph or anything downstream of it."""

    mapping: dict[str, str]

    def classify(self, action: str | None) -> str:
        if action is None:
            return "unknown"
        return self.mapping.get(action, "other")


def test_injected_classifier_is_used_instead_of_the_default():
    stub = _StubClassifier(mapping={"Add-LocalGroupMember": "escalate"})
    graph = ag.build_graph(
        [{"eventName": "Add-LocalGroupMember", "host": "h1", "eventTime": 1.0}],
        classifier=stub,
    )
    artifact = next(iter(graph.artifacts.values()))
    assert artifact.action_class == "escalate"


def test_injected_classifier_bridges_cross_vocabulary_shape_matching():
    """The seam's payoff: once a classifier bridges two vocabularies, the
    structural_signature of equivalent chains becomes identical even though
    every literal token still differs -- the thing the deterministic table
    alone cannot do for this pair."""
    bridge = _StubClassifier(
        mapping={
            "AttachUserPolicy": "escalate",
            "Add-LocalGroupMember": "escalate",
        }
    )
    aws_graph = ag.build_graph(
        [{"eventName": "AttachUserPolicy", "user": "u1", "eventTime": 1.0}], classifier=bridge
    )
    win_graph = ag.build_graph(
        [{"eventName": "Add-LocalGroupMember", "host": "h1", "eventTime": 1.0}], classifier=bridge
    )
    aws_unit = next(u for u in ag.enumerate_units(aws_graph) if u.level == "L1_ARTIFACT")
    win_unit = next(u for u in ag.enumerate_units(win_graph) if u.level == "L1_ARTIFACT")
    assert (
        aws_unit.structural_signature["class_sequence"]
        == win_unit.structural_signature["class_sequence"]
        == ["escalate"]
    )
    assert set(aws_unit.vocabulary).isdisjoint(set(win_unit.vocabulary))

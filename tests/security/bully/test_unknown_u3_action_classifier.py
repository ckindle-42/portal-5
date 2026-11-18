"""U.3 -- the verb-to-class seam, isolated (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag


def test_deterministic_classifier_is_the_default():
    graph = ag.build_graph(
        [{"eventName": "AssumeRole", "user": "u1", "eventTime": 1_700_000_000.0}]
    )
    artifact = next(iter(graph.artifacts.values()))
    assert artifact.action_class == "auth"


def test_deterministic_classifier_fails_on_unanticipated_vocabulary():
    """Documents the known seam rather than papering over it: a real
    escalation verb the table's author did not anticipate falls through to
    'other', not 'escalate'."""
    classifier = ag.DeterministicActionClassifier()
    assert classifier.classify("Add-LocalGroupMember") == "other"

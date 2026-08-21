"""D.3 -- the two fixes carried forward from the withdrawn
TASK_BULLY_SERIES_COMPOUNDING_V1: an analyst verdict dominates a tie when
suppressing, and the behaviour table recognises its own class names."""

from __future__ import annotations

from portal.modules.security.core.bully import compounding
from portal.modules.security.core.bully import pyramid as p
from portal.modules.security.core.bully.anchors import AnchorLibrary

_LABELS = ("auth", "enumerate", "execute", "destroy", "escalate", "collect", "c2_exfil")


def test_every_behavior_table_label_classifies_to_itself():
    for label in _LABELS:
        assert p.classify_behavior(label) == label


def test_analyst_verdict_dominates_a_tie_when_suppressing():
    """A shape ties in distance with both a BENIGN_CLOSE anchor and a
    confirmed-malicious one. The benign, analyst-confirmed match must
    dominate -- an already-closed neighbourhood must not re-escalate just
    because a same-distance malicious anchor also exists."""
    library = AnchorLibrary()
    shape = ("auth", "enumerate", "escalate")
    library.load_benign_pattern(
        source_id="analyst", record={"action_sequence": list(shape)}, recurrence_count=3
    )
    library.load_attack_episode(
        source_id="attack_data", record={"action_sequence": list(shape)}, techniques=("T1078",)
    )
    assert compounding.should_escalate_shape(shape, library) is False


def test_no_benign_match_within_radius_still_escalates():
    library = AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["auth", "enumerate", "escalate"]},
        techniques=("T1078",),
    )
    assert compounding.should_escalate_shape(("auth", "enumerate", "escalate"), library) is True


def test_far_benign_match_does_not_suppress():
    library = AnchorLibrary()
    library.load_benign_pattern(
        source_id="analyst",
        record={"action_sequence": ["collect", "collect", "collect"]},
        recurrence_count=3,
    )
    assert compounding.should_escalate_shape(("auth", "escalate", "execute"), library) is True

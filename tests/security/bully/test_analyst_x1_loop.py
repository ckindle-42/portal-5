"""X.1 -- the analyst verdict loop: fire on knowns and same-or-similar
unknowns, never on DIFFERENT; carry the class in the notification payload;
every verdict writes back with the correct outcome/tier pairing; the only
suppressor is `should_escalate` (TASK_BULLY_ANALYST_LOOP_V1)."""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import analyst_loop as al
from portal.modules.security.core.bully import compounding
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary


def _signature():
    return sig_mod.build_signature(
        {"target_host": "zeta9"},
        {
            "action_sequence": ["exotic_process_hollow", "exotic_beacon_channel"],
            "attack_mappings": [{"technique_id": "T9999"}],
            "telemetry_shape": {"source_class": "novel_sensor"},
            "context_topology": {"zone": "quarantine"},
        },
    )


def _kwargs(relationship: str, **overrides):
    base = {
        "assessment_id": "as-1",
        "entity_id": "jsmith",
        "relationship": relationship,
        "n_sources": 2,
        "source_ids": ("s1", "s2"),
        "aligned_spine": ("auth", "enumerate"),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("relationship", ["SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED"])
def test_every_notifying_class_fires(relationship):
    notified = []
    concern = al.raise_concern(notify=notified.append, **_kwargs(relationship))
    assert concern is not None
    assert len(notified) == 1


def test_different_never_fires():
    notified = []
    concern = al.raise_concern(notify=notified.append, **_kwargs("DIFFERENT"))
    assert concern is None
    assert notified == []


def test_notification_payload_carries_concern_class_distinguishing_known_from_unknown():
    notified = []
    al.raise_concern(notify=notified.append, **_kwargs("SAME"))
    al.raise_concern(notify=notified.append, **_kwargs("SIMILAR"))
    al.raise_concern(notify=notified.append, **_kwargs("ANOMALOUS_UNCLASSIFIED"))
    assert notified[0]["concern_class"] == "known_bad"
    assert notified[1]["concern_class"] == "unknown_cousin"
    assert notified[2]["concern_class"] == "unknown_cousin"


@pytest.mark.parametrize(
    "verdict,outcome,confirmed,tier",
    [
        (al.CONFIRMED, "ESCALATE", True, "ANALYST_CONFIRMED"),
        (al.BENIGN, "BENIGN_CLOSE", True, "ANALYST_CONFIRMED"),
        (al.UNSURE, "ANOMALOUS_UNCLASSIFIED", False, "SYSTEM_GENERATED"),
    ],
)
def test_all_three_verdicts_write_back_with_correct_outcome_and_tier(
    verdict, outcome, confirmed, tier
):
    lib = AnchorLibrary()
    signature = _signature()
    concern = al.raise_concern(notify=lambda _p: None, **_kwargs("SAME"))
    closed, anchor = al.record_verdict(concern, verdict, anchor_library=lib, signature=signature)
    assert closed.verdict == verdict
    assert not closed.is_open
    assert anchor is not None
    assert anchor.record["outcome"] == outcome
    assert anchor.provenance_tier == tier
    assert (anchor.label_basis == "analyst_decision") is confirmed


def test_seeded_violation_benign_without_write_back_does_not_suppress_cycle_two():
    """Seeded to fail: if BENIGN verdicts skipped write-back, should_escalate
    could never find the BENIGN_CLOSE anchor and cycle 2 would not quiet."""
    lib = AnchorLibrary()
    signature = _signature()
    from portal.modules.security.core.bully import relation as relation_mod

    concern = al.raise_concern(notify=lambda _p: None, **_kwargs("SAME"))

    # The violation: verdict recorded, but write-back deliberately skipped
    # (anchor_library/signature omitted) -- mirrors a bug where BENIGN
    # verdicts don't call compounding.write_outcome_as_anchor.
    al.record_verdict(concern, al.BENIGN)

    rel = relation_mod.relate(signature, lib)
    # Nothing was written, so should_escalate can't have anything to suppress on.
    assert compounding.should_escalate(rel, lib) is True

    # Now do it correctly -- write-back present -- and suppression appears.
    al.record_verdict(concern, al.BENIGN, anchor_library=lib, signature=signature)
    rel2 = relation_mod.relate(signature, lib)
    assert compounding.should_escalate(rel2, lib) is False


def test_should_escalate_false_is_the_only_suppression_path():
    notified = []
    concern = al.raise_concern(notify=notified.append, should_escalate=False, **_kwargs("SAME"))
    assert concern is None
    assert notified == []


def test_record_verdict_rejects_unknown_verdict():
    concern = al.raise_concern(notify=lambda _p: None, **_kwargs("SAME"))
    with pytest.raises(ValueError):
        al.record_verdict(concern, "MAYBE")


def test_open_queue_orders_unknown_cousins_first():
    known = al.raise_concern(notify=lambda _p: None, **_kwargs("SAME", n_sources=10))
    unknown = al.raise_concern(notify=lambda _p: None, **_kwargs("SIMILAR", n_sources=1))
    queue = al.open_queue([known, unknown])
    assert queue[0] is unknown
    assert queue[1] is known


def test_open_queue_excludes_closed_concerns():
    concern = al.raise_concern(notify=lambda _p: None, **_kwargs("SAME"))
    closed, _anchor = al.record_verdict(concern, al.CONFIRMED)
    assert al.open_queue([closed]) == []
    assert al.open_queue([concern]) == [concern]

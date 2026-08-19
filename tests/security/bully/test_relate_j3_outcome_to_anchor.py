"""J.3 -- outcomes become anchors, the compounding loop closes: a confirmed
finding becomes retrievable as an anchor and changes a later relation; a
benign close is written and prevents a repeat escalation."""

from __future__ import annotations

from portal.modules.security.core.bully import compounding
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary


def _novel_signature():
    return sig_mod.build_signature(
        {"target_host": "zeta9"},
        {
            "action_sequence": ["exotic_process_hollow", "exotic_beacon_channel"],
            "attack_mappings": [{"technique_id": "T9999"}],
            "telemetry_shape": {"source_class": "novel_sensor"},
            "context_topology": {"zone": "quarantine"},
        },
    )


def test_confirmed_finding_becomes_retrievable_anchor_and_changes_later_relation():
    lib = AnchorLibrary()
    signature = _novel_signature()

    before = relation_mod.relate(signature, lib)
    assert before.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert before.confidence == 0.0

    anchor = compounding.write_outcome_as_anchor(
        lib,
        signature,
        source_id="investigation",
        outcome="ESCALATE",
        analyst_confirmed=True,
    )
    assert anchor in lib.all()
    assert anchor.kind == "confirmed_finding"

    after = relation_mod.relate(signature, lib)
    assert after.verdict in ("SAME", "SIMILAR")
    assert after.confidence > before.confidence


def test_benign_close_is_written_and_prevents_repeat_escalation():
    lib = AnchorLibrary()
    signature = _novel_signature()

    compounding.write_outcome_as_anchor(
        lib,
        signature,
        source_id="investigation",
        outcome="BENIGN_CLOSE",
        analyst_confirmed=True,
    )
    rel = relation_mod.relate(signature, lib)
    assert rel.verdict in ("SAME", "SIMILAR")
    assert compounding.should_escalate(rel, lib) is False


def test_escalate_outcome_does_not_suppress_future_escalation():
    lib = AnchorLibrary()
    signature = _novel_signature()

    compounding.write_outcome_as_anchor(
        lib,
        signature,
        source_id="investigation",
        outcome="ESCALATE",
        analyst_confirmed=True,
    )
    rel = relation_mod.relate(signature, lib)
    assert compounding.should_escalate(rel, lib) is True


def test_unreviewed_outcome_still_written_back_weak_and_system_generated():
    lib = AnchorLibrary()
    signature = _novel_signature()
    anchor = compounding.write_outcome_as_anchor(
        lib,
        signature,
        source_id="observed-mode",
        outcome="BENIGN_CLOSE",
        analyst_confirmed=False,
    )
    assert anchor in lib.all()
    assert anchor.grade == "weak"
    assert anchor.provenance_tier == "SYSTEM_GENERATED"


def test_no_match_defers_to_ordinary_escalation():
    lib = AnchorLibrary()
    signature = _novel_signature()
    rel = relation_mod.relate(signature, lib)  # empty library -> ANOMALOUS
    assert compounding.should_escalate(rel, lib) is True

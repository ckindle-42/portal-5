"""Y.4 -- quarantine the poisoned anchors, guard scripted write-back.
Reproduction of D4 (TASK_BULLY_TRUTH_ACCEPTANCE_V1): X.6's scripted verdicts
wrote CONFIRMED/ESCALATE anchors on background entities, poisoning the
library. See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md."""

from __future__ import annotations

from portal.modules.security.core.bully import analyst_loop as al
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


def _concern(relationship="SAME"):
    return al.raise_concern(
        notify=lambda _p: None,
        assessment_id="as-1",
        entity_id="bg-host",
        relationship=relationship,
        n_sources=2,
        source_ids=("s1", "s2"),
        aligned_spine=("auth", "enumerate"),
    )


# ── the write-back guard ────────────────────────────────────────────────


def test_scripted_confirmed_on_background_writes_no_anchor_and_is_refused():
    lib = AnchorLibrary()
    signature = _signature()
    concern = _concern()
    closed, anchor = al.record_verdict(
        concern,
        al.CONFIRMED,
        anchor_library=lib,
        signature=signature,
        scripted=True,
        ground_truth="background",
    )
    assert closed.verdict == al.CONFIRMED  # the decision is still recorded
    assert anchor is None  # but nothing was written to the library
    assert closed.verdict_write_refused_reason is not None
    assert len(lib) == 0


def test_scripted_benign_on_implant_writes_no_anchor():
    lib = AnchorLibrary()
    signature = _signature()
    concern = _concern()
    closed, anchor = al.record_verdict(
        concern,
        al.BENIGN,
        anchor_library=lib,
        signature=signature,
        scripted=True,
        ground_truth="known_bad",
    )
    assert anchor is None
    assert closed.verdict_write_refused_reason is not None


def test_same_verdict_from_a_human_actor_writes_normally():
    """A real analyst verdict is never blocked -- a human may legitimately
    disagree with a label. The guard only applies to scripted stand-ins."""
    lib = AnchorLibrary()
    signature = _signature()
    concern = _concern()
    closed, anchor = al.record_verdict(
        concern,
        al.CONFIRMED,
        anchor_library=lib,
        signature=signature,
        scripted=False,
        ground_truth="background",
    )
    assert anchor is not None
    assert anchor.record["outcome"] == "ESCALATE"
    assert closed.verdict_write_refused_reason is None


def test_scripted_verdict_matching_truth_writes_normally():
    lib = AnchorLibrary()
    signature = _signature()
    concern = _concern()
    closed, anchor = al.record_verdict(
        concern,
        al.CONFIRMED,
        anchor_library=lib,
        signature=signature,
        scripted=True,
        ground_truth="known_bad",
    )
    assert anchor is not None
    assert closed.verdict_write_refused_reason is None


def test_unsure_never_contradicts_truth():
    lib = AnchorLibrary()
    signature = _signature()
    concern = _concern()
    closed, anchor = al.record_verdict(
        concern,
        al.UNSURE,
        anchor_library=lib,
        signature=signature,
        scripted=True,
        ground_truth="background",
    )
    assert anchor is not None
    assert closed.verdict_write_refused_reason is None


# ── quarantine ───────────────────────────────────────────────────────────


def test_quarantine_preserves_the_pre_quarantine_anchor():
    lib = AnchorLibrary()
    from portal.modules.security.core.bully import compounding

    signature = _signature()
    anchor = compounding.write_outcome_as_anchor(
        lib, signature, source_id="x6", outcome="ESCALATE", analyst_confirmed=True
    )
    quarantined = lib.quarantine(anchor.anchor_id, reason="poisoned by X.6")
    assert quarantined.quarantined is True
    assert quarantined.quarantine_reason == "poisoned by X.6"
    assert lib.get(anchor.anchor_id) is quarantined
    log = lib.quarantine_log()
    assert len(log) == 1
    assert log[0] is anchor
    assert log[0].quarantined is False  # the never-deleted pre-quarantine snapshot


def test_quarantine_poisoned_confirmed_findings_targets_only_background_escalates():
    lib = AnchorLibrary()
    from portal.modules.security.core.bully import compounding

    bad_anchor = compounding.write_outcome_as_anchor(
        lib, _signature(), source_id="x6", outcome="ESCALATE", analyst_confirmed=True
    )
    good_anchor = compounding.write_outcome_as_anchor(
        lib, _signature(), source_id="x6", outcome="ESCALATE", analyst_confirmed=True
    )
    result = lib.quarantine_poisoned_confirmed_findings(
        ground_truth_by_anchor={
            bad_anchor.anchor_id: "background",
            good_anchor.anchor_id: "known_bad",
        },
        provenance="X6",
    )
    assert result["n_quarantined"] == 1
    assert result["anchor_ids"] == [bad_anchor.anchor_id]
    assert lib.get(bad_anchor.anchor_id).quarantined is True
    assert lib.get(good_anchor.anchor_id).quarantined is False

"""T4 — the change pipeline verification suite (Phases 7).

Tier 0: invariants. Tier 1: the real CIP-003-8 -> CIP-003-9 transition. Tier 2:
planted change controls. Change-detection recall is the headline (a missed
change is a silently stale policy); cosmetic false-positive rate is reported
beside it, never averaged.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.change_pipeline import (
    draft_revisions,
    expire_mappings,
    impact_report,
    prospective_report,
)
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.register_diff import diff_standard, diff_summary

reg = Register.load()
_OLD = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-8"], edges=[])
_NEW = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-9"], edges=[])
_SCOPE = AssetScope(
    impact_present={"high", "medium", "low"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="op",
    declared_at="2026-09-03",
)


def _mk(
    part,
    text,
    *,
    vrf="Medium",
    appsys="high impact and medium impact BES Cyber Systems",
    measure="",
):
    return RegisterNode(
        id=f"X {part}",
        standard="X-1",
        version="1",
        requirement="R1",
        part=part,
        verbatim_text=text,
        measure_text=measure,
        applicable_systems=appsys,
        table_name="T",
        vrf=vrf,
        time_horizon="OP",
        lifecycle_state="EFFECTIVE",
        valid_from=None,
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="x.pdf",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )


def _diff(old_nodes, new_nodes):
    return diff_standard(
        Register(nodes=old_nodes, edges=[]), Register(nodes=new_nodes, edges=[]), "X"
    )


# ── Tier 0: invariants ────────────────────────────────────────────────────
def test_every_diff_row_carries_both_spans():
    rows = diff_standard(_OLD, _NEW, "CIP-003")
    for r in rows:
        assert isinstance(r.old_span, str) and isinstance(r.new_span, str)
        if r.change_type == "PART_ADDED":
            assert r.new_span and not r.old_span
        elif r.change_type == "PART_REMOVED":
            assert r.old_span and not r.new_span
        else:
            assert r.old_span and r.new_span


def test_a_mapping_never_inherits_a_verdict_across_a_language_change(tmp_path):
    store = MappingStore(tmp_path / "m.json")
    mp = store.propose("CIP-003-8 R1 Part 1.2.6", "OT-POL", "§1", "FULL")
    store.approve(mp.id, "sme")
    expire_mappings(store, diff_standard(_OLD, _NEW, "CIP-003"), "2024-04-01")
    # the FULL mapping is closed; its successor is NEEDS_REVIEW, not FULL
    successors = [m for m in store._rows if m.source == "successor_of_expired"]
    assert successors and all(m.coverage == "NEEDS_REVIEW" for m in successors)
    assert store._by_id(mp.id).valid_to == "2024-04-01"


def test_prospective_output_is_marked_and_never_a_today_obligation():
    pr = prospective_report(reg, _SCOPE, "2024-06-01")
    assert pr["n_future_effective"] >= 1
    assert all(r["prospective"] is True for r in pr["rows"])
    assert "MUST NOT reach" in pr["segregation"]


# ── Tier 1: the real transition ──────────────────────────────────────────
def test_cip_003_8_to_9_produces_the_known_changes():
    rows = diff_standard(_OLD, _NEW, "CIP-003")
    types = {(r.change_type, r.part_id_new) for r in rows}
    # old 1.2.6 ("CIP Exceptional Circumstances") shifted to new 1.2.7
    assert ("RENUMBERED", "CIP-003-9 R1 Part 1.2.7") in types
    # new 1.2.6 now carries "Vendor electronic remote access security controls"
    lang = next(r for r in rows if r.part_id_new == "CIP-003-9 R1 Part 1.2.6")
    assert lang.change_type == "LANGUAGE_CHANGED" and lang.sub_type == "substantive"
    assert "Vendor electronic remote access" in lang.new_span
    # the U+2010 hyphen churn on 1.1.x is cosmetic, not raised as an obligation change
    s = diff_summary(rows)
    assert s["cosmetic"] >= 5
    assert all(r.to_dict()["substantive"] or r.sub_type == "cosmetic" for r in rows)


# ── Tier 2: planted change controls ──────────────────────────────────────
def test_explicit_and_implicit_change_both_detected():
    old = [_mk("1.1", "Review the access list at least once every 15 calendar months.")]
    new = [_mk("1.1", "Review the access list at least once every 12 calendar months.")]
    rows = _diff(old, new)
    assert len(rows) == 1 and rows[0].change_type == "TIMELINE_CHANGED"


def test_modality_change_typed_as_modality_not_wording():
    old = [_mk("1.1", "The entity shall encrypt data in transit.")]
    new = [_mk("1.1", "The entity should encrypt data in transit.")]
    rows = _diff(old, new)
    assert rows[0].change_type == "LANGUAGE_CHANGED" and rows[0].sub_type == "modality"


def test_timeline_change_is_substantive():
    old = [_mk("1.1", "install the patch within 35 calendar days")]
    new = [_mk("1.1", "install the patch within 15 calendar days")]
    r = _diff(old, new)[0]
    assert r.change_type == "TIMELINE_CHANGED" and r.to_dict()["substantive"]
    assert "35" in r.detail and "15" in r.detail


def test_cosmetic_change_is_not_raised_as_an_obligation_change():
    old = [_mk("1.1", "Cyber security awareness (per CIP-004);")]
    new = [_mk("1.1", "Cyber security awareness (per CIP‐004)")]  # U+2010 + no semicolon
    rows = _diff(old, new)
    assert len(rows) == 1
    assert rows[0].sub_type == "cosmetic" and not rows[0].to_dict()["substantive"]


def test_renumber_is_paired_and_high_confidence_or_needs_review():
    old = [_mk("1.5", "Transient Cyber Assets and Removable Media malicious code risk mitigation")]
    new = [_mk("1.6", "Transient Cyber Assets and Removable Media malicious code risk mitigation")]
    r = _diff(old, new)[0]
    assert r.change_type == "RENUMBERED" and r.sub_type == "paired" and r.confidence >= 0.9
    # a low-similarity pair is not silently mispaired
    old2 = [_mk("1.5", "Physical access controls at the perimeter")]
    new2 = [_mk("1.6", "Cyber Security Incident response coordination with the ERO")]
    rows2 = _diff(old2, new2)
    assert {r.change_type for r in rows2} == {"PART_ADDED", "PART_REMOVED"}


def test_inapplicable_change_is_informational_not_work(tmp_path):
    old = [
        _mk("1.1", "old text about medium impact only", appsys="Medium Impact BES Cyber Systems")
    ]
    new = [
        _mk("1.1", "new text about medium impact only", appsys="Medium Impact BES Cyber Systems")
    ]
    high_only = AssetScope(impact_present={"high"}, declared_by="op", declared_at="x")
    ir = impact_report(
        Register(nodes=old, edges=[]),
        Register(nodes=new, edges=[]),
        "X",
        high_only,
        MappingStore(tmp_path / "m.json"),
    )
    assert ir["work_items"] == 0 and ir["informational"] == 1


def test_mapping_expiry_completeness(tmp_path):
    store = MappingStore(tmp_path / "m.json")
    # 1.2.5 changed only its trailing list conjunction (cosmetic); 1.2.6 changed
    # meaning AND was renumbered to 1.2.7. Only the 1.2.6 mapping expires.
    for pid in ("CIP-003-8 R1 Part 1.2.5", "CIP-003-8 R1 Part 1.2.6"):
        mp = store.propose(pid, "OT-POL-003", "§x", "FULL")
        store.approve(mp.id, "sme")
    res = expire_mappings(store, diff_standard(_OLD, _NEW, "CIP-003"), "2024-04-01")
    assert res["n_expired"] == 1
    assert res["n_successors_needs_review"] == 1
    assert store._by_id(store.all_for("CIP-003-8 R1 Part 1.2.5")[0].id).valid_to is None


def test_impact_report_examined_and_resolved_are_separate_numbers():
    ir = impact_report(_OLD, _NEW, "CIP-003", _SCOPE)
    assert "examined" in ir and "substantively_resolved" in ir
    assert ir["examined"] >= ir["substantively_resolved"]


# ── Phase 6 gate ─────────────────────────────────────────────────────────
def test_draft_revisions_is_specification_only_by_default():
    ir = impact_report(_OLD, _NEW, "CIP-003", _SCOPE)
    dr = draft_revisions(ir)
    assert dr["mode"] == "specification_only"
    assert all(s["drafted_replacement"] is None for s in dr["specifications"])
    assert "report to operator" in dr["recommendation"]
    with pytest.raises(NotImplementedError, match="operator's"):
        draft_revisions(ir, mode="draft_as_proposal")

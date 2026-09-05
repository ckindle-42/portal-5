"""T3 Phases 2/4/5/6 — temporal filter, intent routing, mapping store,
applicability gate, coverage by enumeration.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope, applicable, gate_presentation
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import coverage_matrix
from portal.modules.compliance.core.engine import (
    classify_intent,
    effective_parts,
    future_effective_parts,
    route,
)
from portal.modules.compliance.core.mapping_store import MappingStore

reg = Register.load()


# ── Phase 2: temporal filter ────────────────────────────────────────────────
def test_effective_filter_excludes_not_yet_and_retired():
    today = effective_parts(reg, "2026-09-03")
    # the RETIRED CIP-003-8 (kept for the T4 diff) is excluded
    assert len(today) < len(reg.nodes)
    assert not any(n.standard == "CIP-003-8" for n in today)
    assert any(n.standard == "CIP-003-9" for n in today)
    # CIP-012-2 is effective 2025-07-01 — not enforceable on 2024-01-01
    early = {n.id for n in effective_parts(reg, "2024-01-01")}
    assert not any(i.startswith("CIP-012-2") for i in early)
    assert any(i.startswith("CIP-007-6") for i in early)  # effective 2016


def test_retired_version_never_reaches_a_today_query():
    # the register holds only current versions, but the filter must be a
    # predicate on lifecycle_state, not a score
    for n in effective_parts(reg, "2026-09-03"):
        assert n.lifecycle_state == "EFFECTIVE"


def test_future_effective_is_visible_before_its_date():
    fut = future_effective_parts(reg, "2024-06-01")
    # CIP-012-2 (valid_from 2025-07-01) is "coming" as of mid-2024
    assert any(n.standard == "CIP-012-2" for n in fut)
    assert all(n.standard == "CIP-012-2" for n in fut)


# ── Phase 2: intent routing ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "q,intent",
    [
        ("what must we do today for security patch management", "today"),
        ("what's coming in the next CIP revision", "change"),
        ("run a gap analysis against CIP-007", "gaps"),
        ("explain the difference between EACMS and PACS", "freeform"),
    ],
)
def test_intent_classification(q, intent):
    assert classify_intent(q) == intent


def test_route_picks_the_node_set_for_the_intent():
    r = route("where are our gaps", reg, "2026-09-03")
    assert r["intent"] == "gaps" and r["n_nodes_in_path"] > 0
    r2 = route("explain CIP-011", reg, "2026-09-03")
    assert r2["intent"] == "freeform" and r2["n_nodes_in_path"] == 0


# ── Phase 4: mapping store ──────────────────────────────────────────────────
def test_mapping_store_propose_approve_override_rate(tmp_path):
    s = MappingStore(tmp_path / "m.json")
    m = s.propose("CIP-007-6 R2 Part 2.2", "OT-POL-007", "§4.2", "FULL", confidence=0.6)
    assert not m.is_approved
    assert s.approved_for("CIP-007-6 R2 Part 2.2") == []
    s.approve(m.id, "sme@entity", coverage="PARTIAL")  # SME corrects the proposal
    got = s.approved_for("CIP-007-6 R2 Part 2.2")
    assert len(got) == 1 and got[0].coverage == "PARTIAL"
    ov = s.override_rate()
    assert ov["n_sme_overrides"] == 1 and ov["override_rate"] == 1.0
    assert ov["labelled_examples"] == 1
    # reload persists
    assert (
        MappingStore(tmp_path / "m.json").approved_for("CIP-007-6 R2 Part 2.2")[0].coverage
        == "PARTIAL"
    )


def test_mapping_store_rejects_bad_coverage_token(tmp_path):
    s = MappingStore(tmp_path / "m.json")
    with pytest.raises(ValueError, match="coverage must be one of"):
        s.propose("X", "Y", "Z", "compliant")


# ── Phase 5: applicability gate ─────────────────────────────────────────────
def test_applicable_respects_impact_and_erc():
    node = next(n for n in reg.nodes if n.id == "CIP-007-6 R2 Part 2.2")
    full = AssetScope(
        impact_present={"high", "medium"},
        associated_present={"eacms", "pacs", "pca"},
        declared_by="op",
        declared_at="2026-09-03",
    )
    assert applicable(node.applicable_systems, full)[0]
    low_only = AssetScope(impact_present={"low"}, declared_by="op", declared_at="2026-09-03")
    ok, reason = applicable(node.applicable_systems, low_only)
    assert not ok and "scoped to" in reason


def test_undeclared_scope_fails_the_gate():
    node = reg.nodes[10]
    assert not applicable(node.applicable_systems, AssetScope())[0]


def test_gate_presentation_reports_dimensions_not_a_choice():
    g = gate_presentation()
    assert set(g["dimensions"]) == {
        "impact_present",
        "associated_present",
        "has_erc",
        "has_control_center",
    }
    assert g["recommendation"] == "report to operator; do not infer."


# ── Phase 6: coverage by enumeration ───────────────────────────────────────
_SCOPE = AssetScope(
    impact_present={"high", "medium"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="op",
    declared_at="2026-09-03",
)


def test_coverage_requires_a_declared_scope():
    with pytest.raises(ValueError, match="requires a declared AssetScope"):
        coverage_matrix(reg, AssetScope(), "2026-09-03", lambda n, side: [])


def test_coverage_matrix_examined_and_resolved_are_separate_numbers(tmp_path):
    """The Bully's GP: examined and substantively_resolved are DIFFERENT numbers
    and must not collapse. P1 (F03): a candidate-free Part is UNRESOLVED, not a
    substantively-resolved gap — the two numbers must diverge even with zero
    approved mappings, which is the exact unsafe collapse F03 named. An
    approved mapping whose own recorded coverage is FULL and whose endpoint
    resolves in the corpus IS substantively resolved; NEEDS_REVIEW never is."""
    base = coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: []).summary()
    assert base["examined"] > 0
    assert base["substantively_resolved"] == 0  # nothing is auto-resolved absent P5

    store = MappingStore(tmp_path / "m.json")
    review_ids = [
        c.requirement_id
        for c in coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: []).cells
        if c.applies
    ][:5]
    sidecar = {"POL": {}}
    for pid in review_ids:
        mp = store.propose(pid, "POL", "§x", "FULL")
        store.approve(mp.id, "sme")

    s = coverage_matrix(
        reg, _SCOPE, "2026-09-03", lambda n, side: [], store, document_sidecar=sidecar
    ).summary()
    assert s["substantively_resolved"] == 5, s


def test_coverage_full_needs_a_locatable_span_from_both_sides():
    """P1/F03: a qualified span on BOTH sides is no longer certified as FULL —
    full obligation-atom comparison is P5 work. The automated path now reports
    UNRESOLVED with a note that textual presence was found, never a resolved
    positive verdict."""

    def propose_both(node, side):
        if side in ("policy", "procedure"):
            return [
                {
                    "document_id": "D",
                    "section_id": f"{side}-{node.part}",
                    "span": "x",
                    "locatable": True,
                }
            ]
        return []

    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", propose_both)
    cov = {c.requirement_id: c.coverage for c in mx.cells if c.applies}
    assert cov and all(v == "UNRESOLVED" for v in cov.values())
    assert all(not c.substantively_resolved for c in mx.cells if c.applies)


def test_coverage_nothing_found_is_not_a_resolved_gap():
    """P1/F03: empty candidates no longer resolve to a confirmed NONE gap —
    absence is not proven by an empty top-k. Every applicable cell is
    UNRESOLVED and unresolved, and the matrix never claims a confirmed gap."""
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: [])
    s = mx.summary()
    assert s["coverage_breakdown"]["UNRESOLVED"] == s["examined"] > 0
    assert s["coverage_breakdown"]["NONE"] == 0
    assert s["substantively_resolved"] == 0
    assert len(s["unresolved_items"]) == s["examined"]
    assert s["confirmed_gaps_none"] == []


def test_approved_mapping_requires_resolved_endpoint_and_agreement(tmp_path):
    """P1/F04: an approved mapping is authoritative over MODEL judgement, but
    only once its endpoint resolves in the ingested corpus and every approved
    mapping for the Part agrees — it is never a lookup-order shortcut."""
    store = MappingStore(tmp_path / "m.json")
    node_id = next(
        n.id
        for n in effective_parts(reg, "2026-09-03")
        if n.granularity == "part"
        and not (n.standard.startswith("CIP-003") and n.requirement == "R1")
    )
    mp = store.propose(node_id, "POL", "§1", "FULL")
    store.approve(mp.id, "sme")

    def propose_says_none(node, side):
        return []  # model would say unresolved

    # endpoint NOT in the corpus sidecar -> stale/unavailable, never FULL
    mx_unresolved = coverage_matrix(
        reg, _SCOPE, "2026-09-03", propose_says_none, store, document_sidecar={}
    )
    cell = next(c for c in mx_unresolved.cells if c.requirement_id == node_id)
    assert cell.from_approved_mapping and cell.coverage == "UNRESOLVED"
    assert not cell.substantively_resolved

    # endpoint resolves -> the single, unanimous approved decision wins
    mx = coverage_matrix(
        reg, _SCOPE, "2026-09-03", propose_says_none, store, document_sidecar={"POL": {}}
    )
    cell = next(c for c in mx.cells if c.requirement_id == node_id)
    assert cell.from_approved_mapping and cell.coverage == "FULL"
    assert cell.approved_mapping_ids == [mp.id]

    # a second, CONTRADICTING approved mapping -> neither wins by lookup order
    mp2 = store.propose(node_id, "POL2", "§2", "NONE")
    store.approve(mp2.id, "sme2")
    mx2 = coverage_matrix(
        reg,
        _SCOPE,
        "2026-09-03",
        propose_says_none,
        store,
        document_sidecar={"POL": {}, "POL2": {}},
    )
    cell2 = next(c for c in mx2.cells if c.requirement_id == node_id)
    assert cell2.coverage == "NEEDS_REVIEW"
    assert not cell2.substantively_resolved

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
    assert len(today) == len(reg.nodes)  # every held version is currently effective
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


def test_coverage_matrix_examined_and_resolved_are_separate_numbers():
    """The Bully's GP: examined != substantively_resolved. A proposer that
    returns nothing locatable leaves cells NEEDS_REVIEW (examined, not resolved)."""

    def propose_lexical_only(node, side):
        # names the requirement but nothing re-locates -> not coverage
        return [
            {
                "document_id": "POL",
                "section_id": f"{side}-1",
                "span": "see policy",
                "locatable": False,
            }
        ]

    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", propose_lexical_only)
    s = mx.summary()
    assert s["examined"] > s["substantively_resolved"], s
    assert s["substantively_resolved"] == 0


def test_coverage_full_needs_a_locatable_span_from_both_sides():
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
    assert cov and all(v == "FULL" for v in cov.values())


def test_coverage_nothing_found_is_a_substantive_gap():
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: [])
    s = mx.summary()
    assert s["coverage_breakdown"]["NONE"] == s["examined"] > 0
    assert s["substantively_resolved"] == s["examined"]  # a gap is resolved
    assert len(s["full_gaps"]) == s["examined"]


def test_approved_mapping_short_circuits_and_is_authoritative(tmp_path):
    store = MappingStore(tmp_path / "m.json")
    node_id = next(n.id for n in effective_parts(reg, "2026-09-03") if n.granularity == "part")
    mp = store.propose(node_id, "POL", "§1", "FULL")
    store.approve(mp.id, "sme")

    def propose_says_none(node, side):
        return []  # model would say NONE

    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", propose_says_none, store)
    cell = next(c for c in mx.cells if c.requirement_id == node_id)
    assert cell.from_approved_mapping and cell.coverage == "FULL"  # approved row wins

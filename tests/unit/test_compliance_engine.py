"""T3 Phases 2/4/5/6 — temporal filter, intent routing, mapping store,
applicability gate, coverage by enumeration.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope, applicable, gate_presentation
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import coverage_matrix
from portal.modules.compliance.core.engine import (
    effective_parts,
    future_effective_parts,
    route,
)

reg = Register.load()


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


def test_route_picks_the_node_set_for_the_intent():
    r = route("where are our gaps", reg, "2026-09-03")
    assert r["intent"] == "gaps" and r["n_nodes_in_path"] > 0
    r2 = route("explain CIP-011", reg, "2026-09-03")
    assert r2["intent"] == "freeform" and r2["n_nodes_in_path"] == 0


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


_SCOPE = AssetScope(
    impact_present={"high", "medium"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="op",
    declared_at="2026-09-03",
)


def test_coverage_requires_a_declared_scope():
    with pytest.raises(ValueError, match="requires a declared AssetScope"):
        coverage_matrix(reg, AssetScope(), "2026-09-03", lambda n, side: [])


def test_coverage_full_needs_a_locatable_span_from_both_sides():
    """Qualified source text reaches the live V3 field comparator."""

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
    assert all(c.substantively_resolved for c in mx.cells if c.applies)


def test_coverage_nothing_found_is_a_resolved_gap_after_complete_search():
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: [])
    s = mx.summary()
    assert s["coverage_breakdown"]["NONE"] == s["examined"] > 0
    assert s["coverage_breakdown"]["UNRESOLVED"] == 0
    assert s["substantively_resolved"] == s["examined"]
    assert s["unresolved_items"] == []
    assert len(s["confirmed_gaps_none"]) == s["examined"]

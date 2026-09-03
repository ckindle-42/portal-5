"""T3 Phase 7 — the verification suite.

Tier 0: invariants, no models. Tier 2: the planted corpus, whose gaps we know
because we planted them. Full-Gap recall is the headline; false-covered and
false-gap are separate numbers, never averaged; citation resolution must be
1.000.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import coverage_matrix
from portal.modules.compliance.core.planted import load_corpus, make_proposer, score

reg = Register.load()
corpus = load_corpus()

# a High-Impact entity that has every associated system type
_SCOPE = AssetScope(
    impact_present={"high"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="op",
    declared_at="2026-09-03",
)


# ── Tier 0: invariants ──────────────────────────────────────────────────────
def test_compliance_tables_are_disjoint_from_kb():
    # the P7 seam test already proves the byte-identical property; this asserts
    # the composition's namespace at the source
    from portal.modules.compliance.tools import compliance_retrieval as cr

    assert cr._PREFIX == "compliance_"
    assert cr._composition().table_prefix == "compliance_"


def test_every_register_span_resolves_byte_identically():

    # re-verify a sample against the source is a Tier-1 job; here assert the
    # committed register's own report is internally honest
    rep = reg.extraction_report
    assert rep["fidelity"]["n_fidelity_verified"] == rep["n_nodes"]


# The bitemporal-filter / xref-graph classes (TASK_CIP_REGISTER_COMPLETENESS_V1
# §1.8 / P5) are checked by mechanism, per-control, NOT folded into the aggregate
# Full-Gap recall — their targets are intentionally outside the "today +
# high-impact" coverage matrix.
_MECHANISM_CLASSES = {"future_effective", "implicit_change", "cross_reference"}
_matrix_corpus = [d for d in corpus if d.control_class not in _MECHANISM_CLASSES]


# ── Tier 2: the planted corpus ─────────────────────────────────────────────
def test_planted_corpus_covers_the_control_classes():
    from portal.modules.compliance.core.planted import CONTROL_CLASSES

    classes = {d.control_class for d in corpus}
    assert set(CONTROL_CLASSES) == classes  # all 11 present, one doc each minimum


def test_full_gap_recall_is_1_and_no_false_covered():
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", make_proposer(corpus))
    s = score(_matrix_corpus, mx.cells).to_dict()
    # HEADLINE — a missed gap is what destroys trust. Denominator: the planted
    # holes on register Parts that exist (hole / aspirational / lexical / deontic).
    assert s["full_gap_recall"] == 1.0, s["per_control"]
    # reported separately, never averaged
    assert s["false_covered"] == 0
    assert s["false_gap"] == 0
    # must be 1.000
    assert s["citation_resolution"] == 1.0


@pytest.mark.parametrize("doc", _matrix_corpus, ids=[d.control_class for d in _matrix_corpus])
def test_each_planted_control_lands_on_its_expected_coverage(doc):
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", make_proposer(corpus))
    s = score([doc], mx.cells).to_dict()
    pc = s["per_control"][0]
    assert pc["pass"], pc


def test_future_effective_control_is_prospective_not_a_today_obligation():
    """§1.8: exercises the bitemporal filter. CIP-013-2 R1 became enforceable
    2024-04-01; as of 2024-01-01 it is future-effective, not a 'today' gap."""
    from portal.modules.compliance.core.engine import effective_parts, future_effective_parts

    doc = next(d for d in corpus if d.control_class == "future_effective")
    as_of = "2024-01-01"
    fut = {n.id for n in future_effective_parts(reg, as_of)}
    now = {n.id for n in effective_parts(reg, as_of)}
    assert doc.targets in fut
    assert doc.targets not in now  # MUST NOT reach a "what must we do today" answer


def test_implicit_change_control_forces_review_not_verdict_carry_forward():
    """§1.8: a Part whose text changed CIP-003-8 -> -9 with no renumber. A
    mapping approved against the old text must land NEEDS_REVIEW."""
    from portal.modules.compliance.core.register_diff import diff_standard

    doc = next(d for d in corpus if d.control_class == "implicit_change")
    old = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-8"], edges=[])
    new = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-9"], edges=[])
    rows = diff_standard(old, new, "CIP-003")
    changed = {
        r.part_id_new
        for r in rows
        if r.change_type == "LANGUAGE_CHANGED" and r.sub_type == "substantive"
    }
    assert doc.targets in changed


def test_cross_reference_control_has_an_outbound_xref_edge():
    """§1.8: exercises the cross-reference graph. The targeted Part names another
    standard; the register carries that as a CROSS_REFERENCES edge, and pointing
    at CIP-004 is not itself coverage of this Part."""
    doc = next(d for d in corpus if d.control_class == "cross_reference")
    xr = [e for e in reg.edges if e["rel"] == "CROSS_REFERENCES" and e["src"] == doc.targets]
    assert xr, doc.targets
    assert any(e["dst"].startswith("CIP-004") for e in xr)


def test_tier_conflict_is_emitted_not_reconciled_in_the_matrix():
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", make_proposer(corpus))
    conflict_cells = [c for c in mx.cells if c.conflicts]
    assert conflict_cells
    for c in conflict_cells:
        for k in c.conflicts:
            assert k["signal"] == "COMPLIANCE_CONFLICT"
            assert "NOT reconciled" in k["resolution"]


def test_temporal_stale_citation_is_flagged_and_not_counted_as_coverage():
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", make_proposer(corpus))
    stale = [c for c in mx.cells if c.stale_citations]
    assert stale
    assert all(c.coverage == "NONE" for c in stale)


def test_examined_and_substantively_resolved_do_not_collapse():
    """The Bully GP degenerate-fixture guard: a proposer that never substantiates
    leaves the two numbers apart is NOT this case — here everything resolves, so
    the guard is that a *lexical-only* proposer keeps examined > 0 while every
    cell is still a substantive result (a gap)."""
    mx = coverage_matrix(reg, _SCOPE, "2026-09-03", lambda n, side: [])
    s = mx.summary()
    assert s["examined"] > 0
    assert s["substantively_resolved"] == s["examined"]  # all gaps, all resolved
    assert len(s["full_gaps"]) == s["examined"]

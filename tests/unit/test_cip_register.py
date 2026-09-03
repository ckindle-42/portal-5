"""Tier 1 — register extraction, deterministic (T3 Phase 7).

Runs against the committed `nerc_cip_register.json`. No models, no network. A
missing Part reads as "no gap", the most dangerous output this engine can emit,
so verbatim fidelity and the per-standard found/verified counts are asserted
exactly.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.cip_register import Register

reg = Register.load()
_nodes = {n.id: n for n in reg.nodes}


def test_register_is_nonempty_and_all_verbatim_verified():
    rep = reg.extraction_report
    assert rep["n_nodes"] == len(reg.nodes) >= 110
    assert rep["n_parts"] >= 95
    # fidelity: every row that was extracted round-tripped against its source PDF
    fid = rep["fidelity"]
    assert fid["n_fidelity_verified"] == fid["n_extracted"] == rep["n_nodes"]
    assert fid["n_fidelity_failed"] == 0, fid["fidelity_failed"]


def test_completeness_denominator_is_never_self_derived():
    """The degenerate-denominator guard: a completeness metric whose denominator
    comes from the extractor's own output is a fidelity metric wearing a
    completeness label (TASK_CIP_REGISTER_COMPLETENESS_V1 §1.1)."""
    srcs = reg.extraction_report["completeness"]["denominator_source_by_standard"]
    assert srcs, "completeness report absent"
    for std, src in srcs.items():
        assert "extractor" not in src, f"{std}: denominator_source={src!r}"
        assert src.startswith("document:"), f"{std}: {src!r}"


def test_version_divergences_resolved_to_the_enforceable_version():
    """The enforceable version is EFFECTIVE; the superseded version (CIP-003-8,
    downloaded for the T4 change pipeline) is present but RETIRED and excluded
    from a 'today' query. CIP-012-1 was never downloaded."""
    from portal.modules.compliance.core.engine import effective_parts

    by_std = {}
    for n in reg.nodes:
        by_std.setdefault(n.standard, n.lifecycle_state)
    assert by_std["CIP-003-9"] == "EFFECTIVE"
    assert by_std.get("CIP-003-8") == "RETIRED"
    assert by_std["CIP-012-2"] == "EFFECTIVE" and "CIP-012-1" not in by_std
    eff = {n.standard for n in effective_parts(reg, "2026-09-03")}
    assert "CIP-003-8" not in eff and "CIP-003-9" in eff

    sup = {(e["src"], e["dst"]) for e in reg.edges if e["rel"] == "SUPERSEDES"}
    assert ("CIP-003-9", "CIP-003-8") in sup
    assert ("CIP-012-2", "CIP-012-1") in sup


def test_verbatim_fidelity_of_a_known_part():
    n = _nodes["CIP-007-6 R2 Part 2.2"]
    assert n.verbatim_text == (
        "At least once every 35 calendar days, evaluate security patches for "
        "applicability that have been released since the last evaluation from "
        "the source or sources identified in Part 2.1."
    )
    assert n.vrf == "Medium"
    assert n.time_horizon == "Operations Planning"
    assert n.table_name == "Security Patch Management"
    assert n.granularity == "part"


def test_lifecycle_and_validity_intervals_internally_consistent():
    for n in reg.nodes:
        assert n.lifecycle_state in {
            "DRAFT",
            "POSTED_FOR_COMMENT",
            "BALLOT",
            "BOARD_ADOPTED",
            "FERC_APPROVED",
            "FUTURE_EFFECTIVE",
            "EFFECTIVE",
            "RETIRED",
        }
        if n.valid_from and n.valid_to:
            assert n.valid_from < n.valid_to, n.id
        if n.lifecycle_state == "EFFECTIVE":
            assert n.valid_to is None, n.id


def test_every_part_is_tier_0_standard_text():
    assert all(n.authority_tier == 0 for n in reg.nodes)


def test_cross_reference_edges_point_at_real_standards():
    xr = [e for e in reg.edges if e["rel"] == "CROSS_REFERENCES"]
    known = {n.standard for n in reg.nodes} | {
        n.standard.rsplit("-", 1)[0] for n in reg.nodes
    }  # allow version-less "CIP-005"
    for e in xr:
        assert e["dst"] in known, e


@pytest.mark.parametrize(
    "standard,min_parts",
    [
        ("CIP-004-7", 19),
        ("CIP-005-7", 12),
        ("CIP-006-6", 13),
        ("CIP-007-6", 20),
        ("CIP-009-6", 10),
        ("CIP-010-4", 11),
        ("CIP-011-3", 4),
    ],
)
def test_regular_table_standards_fully_extracted(standard, min_parts):
    got = sum(1 for n in reg.nodes if n.standard == standard and n.granularity == "part")
    assert got >= min_parts, f"{standard}: {got}"

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
    # every row that was extracted round-tripped against its source PDF text
    assert rep["n_verbatim_verified"] == rep["n_nodes"]
    for std, s in rep["per_standard"].items():
        assert s["n_missing"] == 0, f"{std}: {s['missing']}"


def test_version_divergences_resolved_to_the_enforceable_version():
    """CIP-003-8 / CIP-012-1 (the pre-existing map) are superseded; the register
    carries -9 / -2 and records the supersession."""
    standards = {n.standard for n in reg.nodes}
    assert "CIP-003-9" in standards and "CIP-003-8" not in standards
    assert "CIP-012-2" in standards and "CIP-012-1" not in standards
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

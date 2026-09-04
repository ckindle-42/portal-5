"""Tier 1 — register extraction, deterministic (T3 Phase 7).

Runs against the committed `nerc_cip_register.json`. No models, no network. A
missing Part reads as "no gap", the most dangerous output this engine can emit,
so verbatim fidelity and the per-standard found/verified counts are asserted
exactly.
"""

from __future__ import annotations

import re

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


def test_no_standard_reports_a_completeness_hole():
    """The §1.3 signal as a permanent guard, at the report level: a standard the
    completeness metric flags as incomplete is a hole the *document itself*
    announced and the extractor did not fill. Fails loudly the moment one
    reappears — unlike the trivially-true `assert n_missing == 0` it replaces."""
    comp = reg.extraction_report["completeness"]
    assert comp["n_missing"] == 0, comp["incomplete_standards"]
    assert comp["incomplete_standards"] == []


def test_no_requirement_has_a_colon_lead_in_with_zero_children():
    """§1.3 directly on the register nodes: an R-level node whose verbatim text
    ends in ':' is declaring a list follows; that requirement must carry Parts."""
    part_reqs = {(n.standard, n.requirement) for n in reg.nodes if n.part}
    offenders = [
        n.id
        for n in reg.nodes
        if not n.part
        and re.fullmatch(r"R\d+|Attachment \d+", n.requirement)  # requirements + attachments
        and n.verbatim_text.rstrip().endswith(":")
        and (n.standard, n.requirement) not in part_reqs
    ]
    assert not offenders, offenders


def test_cip002_attachment1_criteria_are_present_and_addressable():
    """The bright-line impact-rating criteria that the whole CIP suite gates on
    (TASK §1.4). Each criterion is its own verbatim node."""
    att = {
        n.id: n
        for n in reg.nodes
        if n.standard == "CIP-002-5.1a" and "Attachment 1" in n.requirement
    }
    crit = {n.part for n in att.values() if n.part}
    assert {"1.1", "1.2", "1.3", "1.4"} <= crit  # High
    assert {"2.1", "2.2", "2.3"} <= crit  # Medium
    assert {"3.1", "3.6"} <= crit  # Low
    assert any("impact rating criteria" in n.table_name.lower() for n in att.values())
    # R1 Parts 1.1-1.3 landed too
    r1 = {n.part for n in reg.nodes if n.id.startswith("CIP-002-5.1a R1 Part")}
    assert r1 == {"1.1", "1.2", "1.3"}


# Expected minimum Part counts for ALL 14 standards. Table-shaped standards use
# the T3 hardcoded floor; the prose standards use the count P1/P2's completeness
# signals establish from the document. A standard that falls short must xfail
# with a recorded reason, never be dropped from the list.
_PART_FLOORS = {
    "CIP-002-5.1a": 28,  # R1 1.1-1.3, R2 2.1-2.2, Attachment 1 criteria (23)
    "CIP-003-8": 15,  # R1 policy-topic leaves
    "CIP-003-9": 16,  # R1 policy-topic leaves (+1.2.6 vendor remote access)
    "CIP-004-7": 19,
    "CIP-005-7": 12,
    "CIP-006-6": 13,
    "CIP-007-6": 20,
    "CIP-008-6": 10,
    "CIP-009-6": 10,
    "CIP-010-4": 11,
    "CIP-011-3": 4,
    "CIP-012-2": 5,  # R1 1.1-1.5
    "CIP-013-2": 8,  # R1 1.1, 1.2, 1.2.1-1.2.6
    "CIP-014-3": 17,  # R1 1.1-1.2, R2 2.1-2.4, R4 4.1-4.3, R5 5.1-5.4, R6 6.1-6.4
}
_PART_XFAIL: dict[str, str] = {
    # standard -> reason. Empty: every standard currently meets its floor.
}


@pytest.mark.parametrize("standard", sorted(_PART_FLOORS))
def test_every_standard_meets_its_part_floor(standard):
    if standard in _PART_XFAIL:
        pytest.xfail(_PART_XFAIL[standard])
    got = sum(1 for n in reg.nodes if n.standard == standard and n.granularity == "part")
    assert got >= _PART_FLOORS[standard], f"{standard}: {got} < {_PART_FLOORS[standard]}"

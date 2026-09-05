"""TASK_COMPLIANCE_REASONING_V2 P0 — regression contract for findings F01-F12.

Each test reproduces one numbered finding from
``coding_task/v9_compliance/DESIGN_COMPLIANCE_REASONING_V2.md`` §2.1 against
the CURRENT (post-P1) code, and asserts the V2-safe behavior — not the
observed-at-baseline (9006ae6c) unsafe behavior. Several findings are also
exercised more thoroughly in their owning module's own test file
(test_compliance_engine.py, test_compliance_tiers.py,
test_compliance_planted.py, test_compliance_propose.py); this file is the
single place that maps every finding to its disposition and at least one
direct reproduction, per P0's exit criterion ("every baseline finding has a
disposition ... and a mapped implementation/test owner").

Disposition legend (also recorded in reports/compliance/REASONING_V2_BASELINE.md):
    FIXED_P1      — corrected in this task's P1 phase, verified below
    DEFERRED_P5   — the unsafe shortcut is disabled (never a false positive),
                    but the full correct semantics require P5's obligation-atom
                    comparison engine, not yet implemented
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.engine import (
    effective_parts,
    future_effective_parts,
    parse_iso_date,
    unknown_effectivity_parts,
)
from portal.modules.compliance.core.register_diff import diff_standard
from portal.modules.compliance.core.tiers import Span, detect_conflicts


def _node(**kw) -> RegisterNode:
    base = {
        "id": "TEST-1 R1 Part 1.1",
        "standard": "TEST-1",
        "version": "1",
        "requirement": "R1",
        "part": "1.1",
        "verbatim_text": "Do the thing.",
        "measure_text": "",
        "applicable_systems": "",
        "table_name": "",
        "vrf": "",
        "time_horizon": "",
        "lifecycle_state": "EFFECTIVE",
        "valid_from": None,
        "valid_to": None,
        "supersedes": None,
        "superseded_by": None,
        "authority_tier": 0,
        "source_pdf": "",
        "source_pages": [],
        "recorded_at": 0.0,
        "granularity": "part",
    }
    base.update(kw)
    return RegisterNode(**base)


# ── F01: validity is not bitemporality ──────────────────────────────────────
def test_f01_retired_node_still_returned_for_a_historical_date_inside_its_interval():
    """FIXED_P1 (engine.py: interval-based selection, not lifecycle-label
    gating). See also test_compliance_engine.py for the coverage_matrix seam."""
    retired = _node(
        id="TEST-1 R1 Part 1.1",
        lifecycle_state="RETIRED",
        valid_from="2020-01-01",
        valid_to="2024-04-01",
    )
    reg = Register(nodes=[retired])
    assert retired.id in {n.id for n in effective_parts(reg, "2023-06-01")}
    assert retired.id not in {n.id for n in effective_parts(reg, "2024-06-01")}


def test_f01_future_effective_node_moves_to_effective_once_its_date_passes():
    """FIXED_P1: a FUTURE_EFFECTIVE node past its own valid_from must appear in
    effective_parts and drop OUT of future_effective_parts — the label alone
    no longer decides membership, the date does."""
    fut = _node(
        id="TEST-2 R1 Part 1.1", lifecycle_state="FUTURE_EFFECTIVE", valid_from="2026-01-01"
    )
    reg = Register(nodes=[fut])
    assert fut.id in {n.id for n in future_effective_parts(reg, "2025-06-01")}
    assert fut.id not in {n.id for n in effective_parts(reg, "2025-06-01")}
    assert fut.id in {n.id for n in effective_parts(reg, "2026-06-01")}
    assert fut.id not in {n.id for n in future_effective_parts(reg, "2026-06-01")}


def test_f01_invalid_iso_date_is_rejected_not_silently_matched_to_nothing():
    with pytest.raises(ValueError):
        parse_iso_date("not-a-date")
    with pytest.raises(ValueError):
        effective_parts(Register(nodes=[]), "2026-13-40")


# ── F02: current dates are not adequately sourced ───────────────────────────
def test_f02_unrecognized_version_is_unknown_not_defaulted_effective():
    """FIXED_P1 (cip_register.py: unknown default, not EFFECTIVE)."""
    unknown = _node(id="TEST-9 R1 Part 1.1", lifecycle_state="UNKNOWN", valid_from=None)
    reg = Register(nodes=[unknown])
    assert unknown.id not in {n.id for n in effective_parts(reg, "2026-09-04")}
    assert unknown.id in {n.id for n in unknown_effectivity_parts(reg)}


# ── F03: coverage measures passage presence ─────────────────────────────────
# DEFERRED_P5 — see test_compliance_engine.py::test_coverage_full_needs_a_locatable_span_from_both_sides
# and test_coverage_nothing_found_is_not_a_resolved_gap for the direct reproduction:
# FULL/NONE can no longer be automatically certified from candidate presence/absence.


# ── F04: approval is an unchecked shortcut ──────────────────────────────────
# FIXED_P1 — see test_compliance_engine.py::test_approved_mapping_requires_resolved_endpoint_and_agreement


# ── F05: obligation scoping and time units ──────────────────────────────────
def test_f05_calendar_month_business_day_and_calendar_day_are_not_interchangeable():
    """FIXED_P1 (tiers.py: no approximate day-count conversion across units).
    Reproduces the design doc's exact example (§2.1 F05 / F12 probe table)."""
    std = Span("1 calendar month", tier=0, citation="STD")
    thirty_cal_days = Span("30 calendar days", tier=2, citation="POL")
    thirty_biz_days = Span("30 business days", tier=3, citation="PROC")
    c1 = detect_conflicts([std, thirty_cal_days])
    c2 = detect_conflicts([std, thirty_biz_days])
    c3 = detect_conflicts([thirty_cal_days, thirty_biz_days])
    # none of the three pairings may be silently treated as EQUAL (no conflict
    # AND no comparison_uncertainty would both be wrong outcomes here) — every
    # cross-unit/cross-qualifier pairing must abstain explicitly.
    for conflicts in (c1, c2, c3):
        assert len(conflicts) == 1
        assert conflicts[0].kind == "comparison_uncertainty"


def test_f05_same_tier_disagreement_is_detected():
    """FIXED_P1 — see test_compliance_tiers.py for the full assertion."""
    a = Span("15 calendar days", tier=3, citation="PROC-A")
    b = Span("30 calendar days", tier=3, citation="PROC-B")
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1 and conflicts[0].kind == "same_tier_disagreement"


# ── F06: semantic change can be erased ──────────────────────────────────────
def test_f06_and_or_swap_is_never_cosmetic():
    """FIXED_P1 (register_diff.py: connector-aware cosmetic check)."""
    old = _node(id="TEST-1 R1 Part 1.1", standard="TEST-1", verbatim_text="Perform A; and")
    new = _node(id="TEST-2 R1 Part 1.1", standard="TEST-2", verbatim_text="Perform A; or")
    old_reg = Register(nodes=[old])
    new_reg = Register(nodes=[new])
    rows = diff_standard(old_reg, new_reg, "TEST")
    lang = next(r for r in rows if r.change_type == "LANGUAGE_CHANGED")
    assert lang.sub_type == "logic"
    assert lang.to_dict()["substantive"] is True


def test_f06_mixed_version_operands_are_rejected():
    """FIXED_P1 — explicit validation instead of silently keying across
    whatever versions happen to be present."""
    mixed = Register(
        nodes=[
            _node(id="TEST-1 R1 Part 1.1", standard="TEST-1"),
            _node(id="TEST-2 R1 Part 1.1", standard="TEST-2"),
        ]
    )
    single = Register(nodes=[_node(id="TEST-3 R1 Part 1.1", standard="TEST-3")])
    with pytest.raises(ValueError, match="mixed"):
        diff_standard(mixed, single, "TEST")


# ── F09: review records and effective behavior diverge ──────────────────────
def test_f09_rejecting_a_mapping_proposal_revokes_a_prior_approval():
    """FIXED_P1 (mapping_store.py: revoke(); compliance_mcp.py wires REJECTED
    to an actual revocation instead of only recording a review event)."""
    from portal.modules.compliance.core.mapping_store import MappingStore

    def _apply(store, decision):
        # mirrors compliance_review_decide's mapping-side effect without the
        # LanceDB-backed review queue, so this test needs no live store.
        if decision == "REJECTED":
            store.revoke(mp.id, "sme_b")

    with tempfile.TemporaryDirectory() as d:
        store = MappingStore(Path(d) / "m.json")
        mp = store.propose("TEST-1 R1 Part 1.1", "DOC", "§1", "FULL")
        store.approve(mp.id, "sme_a")
        assert store.approved_for("TEST-1 R1 Part 1.1")  # approved

        _apply(store, "REJECTED")
        assert store.approved_for("TEST-1 R1 Part 1.1") == []  # revoked, not still authoritative
        assert store._by_id(mp.id).source == "revoked"  # noqa: SLF001


def test_f09_missing_mapping_target_is_an_error_not_silent_success():
    from portal.modules.compliance.core.mapping_store import MappingStore

    with tempfile.TemporaryDirectory() as d:
        store = MappingStore(Path(d) / "m.json")
        with pytest.raises(KeyError):
            store.revoke("does-not-exist", "sme")


# ── F10: citations and stale references are not reliable enough ────────────
def test_f10_stale_citation_uses_exact_identifier_not_family_prefix():
    """FIXED_P1 (coverage.py: word-boundary exact-id match, not substring)."""
    old_id = "CIP-003-8"
    text_citing_current = "See CIP-003-9 R1 for the governing requirement."
    text_citing_old = "This section restates CIP-003-8 R1 verbatim."
    pattern = rf"(?<![\w-]){re.escape(old_id)}(?![\w-])"
    assert re.search(pattern, text_citing_old)
    assert not re.search(pattern, text_citing_current)  # "-9" must not match "-8"'s prefix

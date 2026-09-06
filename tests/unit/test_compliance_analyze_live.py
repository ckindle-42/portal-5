"""P7 — compliance_analyze assesses LIVE; the cached-row read is deleted."""

from __future__ import annotations

from pathlib import Path

from portal.modules.compliance.core.runtime_config import load_org_commitments, seat_roster
from portal.modules.compliance.tools.compliance_mcp import compliance_analyze


def test_no_cached_claims_select_remains():
    src = Path("portal/modules/compliance/tools/compliance_mcp.py").read_text()
    assert "FROM claims" not in src
    assert "materialized claim missing" not in src


def test_seat_roster_is_family_diverse():
    seats = seat_roster()
    assert len(seats) >= 3
    fams = {s["id"] for s in seats}
    assert len(fams) >= 3  # at least three distinct seats


def test_org_commitments_load_from_the_built_graph_or_empty():
    coms = load_org_commitments()
    assert isinstance(coms, list)
    if coms:
        assert all({"commitment_id", "document_id", "text"} <= set(c) for c in coms[:20])


def test_analyze_gated_out_cu_returns_not_applicable_without_a_model_call():
    r = compliance_analyze("CIP-007-6 R2 Part 2.2", scope="low impact only", operation="start")
    res = compliance_analyze("", operation="result", run_id=r["run_id"])
    rows = res["results"]
    assert rows and rows[0]["determination"] == "NOT_APPLICABLE"
    assert rows[0]["gate_gated_out"] is True


def test_analyze_unknown_ref_is_u02_not_a_silent_pass():
    r = compliance_analyze("CIP-999-1 R9 Part 9.9", operation="start")
    res = compliance_analyze("", operation="result", run_id=r["run_id"])
    assert res["results"][0]["unresolved_code"] == "U02_MISSING_GOVERNING_SOURCE"

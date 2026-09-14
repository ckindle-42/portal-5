"""P7 — compliance_analyze runs the shared service; the in-memory job dict is gone.

Hermetic: the durable run repository is a tmp_path SQLite store, both exercised
cases are short-circuited by the applicability/U02 pre-gate, so no retrieval or
model call happens.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from portal.modules.compliance.core import assessment_runs
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.runtime_config import load_org_commitments, seat_roster
from portal.modules.compliance.tools.compliance_mcp import compliance_analyze

# NERC CIP standard PDFs are fetched locally, deliberately gitignored (see
# cip_register.py's fetch_pdfs docstring) — CI never has them. The gated-out
# case below falls through to assessment_source._pdf_parent_requirement's
# raw-PDF recovery path, but the run happens on a background thread that
# converts the resulting FileNotFoundError into a FAILED run status rather
# than raising it here, so there's no exception for a generic skip-on-error
# fixture to catch.
_CIP_PDFS_PRESENT = any(
    (Path(__file__).resolve().parents[2] / "portal/modules/compliance/data/cip_pdfs").glob("*.pdf")
)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    path = tmp_path / "runs.db"
    r = Repository(path)
    # each _get_repo() call opens its own connection — the same isolation the
    # production factory provides, so the worker and the test never share one.
    monkeypatch.setattr(assessment_runs, "_REPO_FACTORY", lambda: Repository(path))
    return r


def _await(run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = assessment_runs.run_status(run_id)
        if status.get("status") in assessment_runs.TERMINAL_STATES:
            return status
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} did not finish: {assessment_runs.run_status(run_id)}")


def test_no_cached_claims_select_remains():
    src = Path("portal/modules/compliance/tools/compliance_mcp.py").read_text()
    assert "FROM claims" not in src
    assert "_ANALYSIS_JOBS" not in src


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


@pytest.mark.skipif(not _CIP_PDFS_PRESENT, reason="NERC CIP PDF corpus not fetched locally")
def test_analyze_gated_out_cu_returns_not_applicable_without_a_model_call(repo):
    r = compliance_analyze("CIP-007-6 R2 Part 2.2", scope="low impact only", operation="start")
    assert "error" not in r
    status = _await(r["run_id"])
    assert status["status"] == "COMPLETE"
    res = compliance_analyze("", operation="result", run_id=r["run_id"])
    rows = res["results"]
    assert rows and rows[0]["determination"] == "NOT_APPLICABLE"
    assert rows[0]["gate_gated_out"] is True
    assert rows[0]["assessment_id"]


def test_analyze_unknown_ref_is_u02_not_a_silent_pass(repo):
    # An explicit scope avoids assess_requirements_now's empty-scope_text
    # fallback to derive_scope(), which is LanceDB-backed (not hermetic) and
    # runs before the U02 short-circuit this test exercises — same as the
    # gated-out case above.
    r = compliance_analyze("CIP-999-1 R9 Part 9.9", scope="low impact only", operation="start")
    assert "error" not in r
    _await(r["run_id"])
    res = compliance_analyze("", operation="result", run_id=r["run_id"])
    assert res["results"][0]["unresolved_code"] == "U02_MISSING_GOVERNING_SOURCE"


def test_analyze_status_never_reruns(repo):
    r = compliance_analyze("CIP-999-1 R9 Part 9.9", scope="low impact only", operation="start")
    _await(r["run_id"])
    before = repo.run_assessment_ids(r["run_id"])
    status = compliance_analyze("", operation="status", run_id=r["run_id"])
    result = compliance_analyze("", operation="result", run_id=r["run_id"])
    assert status["status"] == "COMPLETE"
    assert result["status"] == "COMPLETE"
    assert repo.run_assessment_ids(r["run_id"]) == before

"""Workstream F — compliance_gaps async run flow (hermetic).

A gated-out Part short-circuits before retrieval/models, so this exercises the
durable run service end to end without network.
"""

from __future__ import annotations

import time

import pytest

from portal.modules.compliance.core import assessment_runs
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.tools.compliance_mcp import compliance_gaps


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
    raise AssertionError(f"run {run_id} did not finish")


def test_gaps_default_start_is_async_without_speculative_rows(repo):
    out = compliance_gaps(requirement="CIP-007-6 R2 Part 2.2", scope="low impact only")
    assert out["run_id"]
    assert out["status"] in ("QUEUED", "RUNNING")
    assert "rows" not in out
    _await(out["run_id"])
    result = compliance_gaps(operation="result", run_id=out["run_id"], generate_drafts=False)
    assert result["status"] == "COMPLETE"
    row = result["rows"][0]
    assert row["coverage"] == "NOT_APPLICABLE"
    assert row["assessment_id"]
    assert row["run_id"] == out["run_id"]


def test_gaps_status_does_not_rerun(repo):
    out = compliance_gaps(requirement="CIP-007-6 R2 Part 2.2", scope="low impact only")
    _await(out["run_id"])
    before = repo.run_assessment_ids(out["run_id"])
    compliance_gaps(operation="status", run_id=out["run_id"])
    compliance_gaps(operation="result", run_id=out["run_id"], generate_drafts=False)
    assert repo.run_assessment_ids(out["run_id"]) == before


def test_gaps_unknown_requirement_is_blocked(repo):
    out = compliance_gaps(requirement="CIP-999-1 R9 Part 9.9", scope="high impact")
    assert out.get("status") == "honest-BLOCKED" or "error" in out or out.get("n_parts") == 0


def test_coverage_matrix_context_path_projects_the_canonical_assessment(monkeypatch):
    from portal.modules.compliance.core import assessment as assessment_mod
    from portal.modules.compliance.core import assessment_runs, coverage
    from portal.modules.compliance.core.applicability import AssetScope
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.determination import (
        AssessmentRequest,
        AssessmentResult,
        CoveredCommitment,
    )

    scope = AssetScope(impact_present={"high"}, declared_by="operator:test")
    reg = Register(nodes=[n for n in Register.load().nodes if n.id == "CIP-007-6 R2 Part 2.2"])
    node = reg.nodes[0]
    request = AssessmentRequest(requirement_id=node.id, scope=scope)

    monkeypatch.setattr(assessment_runs, "build_requests_for", lambda rid, **_: [request])
    slice_row = {
        "slice_id": "cand-1",
        "ref": "proc #chunk27 p8",
        "document_id": "proc.pdf",
        "text": "operative",
        "role": "candidate",
    }

    def fake_assess(req, ctx):
        return AssessmentResult(
            assessment_id="assess-1",
            run_id="run-1",
            engine_version="test",
            input_fingerprint="fp",
            requirement_id=node.id,
            applicability="APPLIES",
            documentary_coverage="FULL",
            coverage="FULL",
            substantively_resolved=True,
            covered=[
                CoveredCommitment(
                    commitment="evaluate patches",
                    governing_slice_ids=["gov-1"],
                    internal_slice_ids=["cand-1"],
                )
            ],
            selected_source_slices=[slice_row],
        )

    monkeypatch.setattr(assessment_mod, "assess_part", fake_assess)
    matrix = coverage.coverage_matrix(reg, scope, "2026-09-12", lambda n, s: [], context=object())
    cell = matrix.cells[0]
    assert cell.assessment_id == "assess-1"
    assert cell.coverage == "FULL"
    assert cell.canonical_support[0]["slice_id"] == "cand-1"
    assert matrix.summary()["substantively_resolved"] == 1

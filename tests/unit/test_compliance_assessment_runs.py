"""Workstream F — durable asynchronous assessment runs.

Hermetic: a tmp_path repository, an injected bundle/request builder and an
injected ``assess_part``. No network, no real Ollama, no retrieval.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from portal.modules.compliance.core import assessment_runs
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.determination import (
    AssessmentRequest,
    AssessmentResult,
    GoverningBundle,
)
from portal.modules.compliance.core.repository import Repository


@pytest.fixture
def repo(tmp_path, monkeypatch):
    path = tmp_path / "runs.db"
    r = Repository(path)
    # each _get_repo() call opens its own connection — the same isolation the
    # production factory provides, so the worker and the test never share one.
    monkeypatch.setattr(assessment_runs, "_REPO_FACTORY", lambda: Repository(path))
    return r


def _scope() -> AssetScope:
    return AssetScope(
        impact_present={"high"}, associated_present={"bcs"}, declared_by="operator:test"
    )


def _bundle(part: str) -> GoverningBundle:
    return GoverningBundle(
        ref=part,
        part_text="Each Responsible Entity shall do the thing.",
        meta=[{"applicable_systems": "High Impact BES Cyber Systems"}],
    )


def _request(part: str) -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id=part,
        kb_id="kb",
        scope=_scope(),
        effective_on="2026-09-12",
    )


def _result(request: AssessmentRequest, coverage: str = "FULL") -> AssessmentResult:
    return AssessmentResult(
        assessment_id=uuid.uuid4().hex[:16],
        run_id=str(request.metadata.get("run_id", "")),
        engine_version="test-engine",
        input_fingerprint="fp",
        requirement_id=request.requirement_id,
        applicability="APPLIES",
        documentary_coverage=coverage,
        coverage=coverage,
        substantively_resolved=coverage in ("FULL", "PARTIAL", "NONE"),
    )


def _install(monkeypatch, *, block: threading.Event | None = None, calls: list[str] | None = None):
    monkeypatch.setattr(assessment_runs, "resolve_governing_bundle", lambda rid, **_: _bundle(rid))
    monkeypatch.setattr(
        assessment_runs,
        "build_requests_for",
        lambda rid, **_: [_request(rid)],
    )

    def fake_assess(request: AssessmentRequest, context) -> AssessmentResult:
        if calls is not None:
            calls.append(request.requirement_id)
        if block is not None and len(calls or []) == 1:
            block.wait(timeout=5)
        result = _result(request)
        context.repository.record_assessment(result)
        return result

    monkeypatch.setattr(assessment_runs, "assess_part", fake_assess)


def _await(repo: Repository, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = repo.get_run(run_id)
        if run and run["status"] in assessment_runs.TERMINAL_STATES:
            return run
        time.sleep(0.005)
    raise AssertionError(f"run {run_id} did not finish: {repo.get_run(run_id)}")


def test_start_returns_immediately_and_persists_under_the_run(repo, monkeypatch):
    _install(monkeypatch)
    run_id = assessment_runs.start_run(
        {"requirements": ["A", "B"], "kb_id": "kb", "scope_text": "high impact"}
    )
    assert run_id
    _await(repo, run_id)
    payload = assessment_runs.run_result(run_id)
    assert payload["status"] == "COMPLETE"
    assert [r["requirement_id"] for r in payload["results"]] == ["A", "B"]
    assert all(r["run_id"] == run_id for r in payload["results"])
    assert payload["assessment_ids"] == [r["assessment_id"] for r in payload["results"]]


def test_status_and_result_re_run_nothing(repo, monkeypatch):
    calls: list[str] = []
    _install(monkeypatch, calls=calls)
    run_id = assessment_runs.start_run(
        {"requirements": ["A"], "kb_id": "kb", "scope_text": "high impact"}
    )
    _await(repo, run_id)
    assert calls == ["A"]
    assessment_runs.run_status(run_id)
    assessment_runs.run_result(run_id)
    assessment_runs.run_status(run_id)
    assert calls == ["A"]  # no additional model work


def test_cancel_takes_effect_at_the_next_part_boundary(repo, monkeypatch):
    block = threading.Event()
    calls: list[str] = []
    _install(monkeypatch, block=block, calls=calls)
    run_id = assessment_runs.start_run(
        {"requirements": ["A", "B"], "kb_id": "kb", "scope_text": "high impact"}
    )
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.005)
    assert calls == ["A"]  # first Part is in flight (blocked)
    assert assessment_runs.cancel_run(run_id)["cancel_requested"] is True
    block.set()
    run = _await(repo, run_id)
    assert run["status"] == "CANCELLED"
    # the first Part completed, the second never started
    assert calls == ["A"]
    assert len(repo.assessments_for_run(run_id)) == 1


def test_cancelled_or_failed_run_is_not_rewritten_as_successful(repo, monkeypatch):
    _install(monkeypatch)
    run_id = assessment_runs.start_run(
        {"requirements": ["A"], "kb_id": "kb", "scope_text": "high impact"}
    )
    _await(repo, run_id)
    assessment_runs.cancel_run(run_id)  # terminal: returns unchanged
    assert repo.get_run(run_id)["status"] == "COMPLETE"


def test_restart_marks_unfinished_runs_interrupted(repo):
    run_id = repo.create_run({"requirements": ["A"]}, status="RUNNING")
    queued = repo.create_run({"requirements": ["B"]}, status="QUEUED")
    assert assessment_runs.init_store(repo) == 2
    assert repo.get_run(run_id)["status"] == "INTERRUPTED"
    assert repo.get_run(queued)["status"] == "INTERRUPTED"


def test_unknown_run_id_is_an_error(repo):
    assert "error" in assessment_runs.run_status("nope")
    assert "error" in assessment_runs.run_result("nope")
    assert "error" in assessment_runs.cancel_run("nope")


def test_acquisition_failure_is_disclosed_not_fatal(repo, monkeypatch):
    class ProposalError(RuntimeError):
        def __init__(self):
            super().__init__("rerank unavailable")
            self.stage = "rerank"

    monkeypatch.setattr(assessment_runs, "resolve_governing_bundle", lambda rid, **_: _bundle(rid))

    def boom(rid, **_):
        raise ProposalError()

    monkeypatch.setattr(assessment_runs, "build_requests_for", boom)
    run_id = assessment_runs.start_run(
        {"requirements": ["A"], "kb_id": "kb", "scope_text": "high impact"}
    )
    run = _await(repo, run_id)
    assert run["status"] == "COMPLETE"
    result = assessment_runs.run_result(run_id)["results"][0]
    assert result["coverage"] == "UNRESOLVED"
    assert result["unresolved_code"] == "U04_RETRIEVAL_INCOMPLETE"
    assert result["receipt"]["retrieval_errors"][0]["stage"] == "rerank"


def test_recovery_preserves_live_owner_and_detects_reused_pid(repo):
    import os

    from portal.modules.compliance.core.repository import process_identity

    owner = {"pid": os.getpid(), "started": process_identity(os.getpid())}
    active = repo.create_run({"worker_owner": owner}, status="RUNNING")
    stale = repo.create_run(
        {"worker_owner": {**owner, "started": "a different process birth time"}}, status="QUEUED"
    )
    assert assessment_runs.init_store(repo) == 1
    assert repo.get_run(active)["status"] == "RUNNING"
    assert repo.get_run(stale)["status"] == "INTERRUPTED"


def test_other_process_import_cannot_interrupt_owned_run(repo):
    import os
    import subprocess
    import sys

    from portal.modules.compliance.core.repository import process_identity

    run_id = repo.create_run(
        {"worker_owner": {"pid": os.getpid(), "started": process_identity(os.getpid())}},
        status="RUNNING",
    )
    # A new CLI process performs the real import-time recovery sweep.
    db_path = repo._conn.execute("PRAGMA database_list").fetchone()[2]
    subprocess.run(
        [sys.executable, "-c", "import portal.modules.compliance.core.assessment_runs"],
        env={**os.environ, "COMPLIANCE_DB_PATH": db_path},
        check=True,
        timeout=20,
    )
    assert repo.get_run(run_id)["status"] == "RUNNING"

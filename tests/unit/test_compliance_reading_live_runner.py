"""The live verifier must distinguish expected uncertainty from a broken run."""

from dataclasses import asdict

from scripts import verify_compliance_reading_acceptance as runner
from tests.unit import test_compliance_reading_acceptance as acceptance


def test_missing_kb_cannot_pass_expected_uncertainty():
    case = acceptance.CASES["15"]
    result = {
        "documentary_coverage": "UNRESOLVED",
        "coverage": "UNRESOLVED",
        "substantively_resolved": False,
        "unresolved_code": "U04_RETRIEVAL_INCOMPLETE",
        "receipt": {"retrieval_errors": [{"stage": "search", "error": "unknown KB"}]},
    }
    failed = {c["name"] for c in runner._live_checks(case, result) if not c["ok"]}
    assert {"code", "acquisition", "run_identity", "model_evidence"} <= failed


def test_setup_failure_does_not_execute_route(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("must not run against a stale KB after setup failed")

    monkeypatch.setattr(runner, "_live_case_via_gaps", unexpected)
    result = runner._execute_live_case({}, acceptance.CASES["02"], "test", "ingest failed")
    assert result == {"error": "ingest failed", "stage": "fixture_setup"}


def test_failure_retains_alignment_response(tmp_path):
    case = acceptance.CASES["24"]
    outcome = acceptance.run_case(case, acceptance.Repository(tmp_path / "trace.db"))
    result = asdict(outcome.result)
    assert result["unresolved_code"] == "U09_SEMANTIC_ALIGNMENT_UNKNOWN"
    assert result["receipt"]["alignment"]["raw"]["seats"][0]["raw"]


def test_report_receives_verified_source_text(tmp_path):
    case = acceptance.CASES["10"]
    outcome = acceptance.run_case(case, acceptance.Repository(tmp_path / "report.db"))
    # The property is unchanged by the move to the reading architecture: the
    # model must receive the VERIFIED STORED TEXT, never a reconstruction. What
    # changed is the packet shape — the reading pass gives each candidate its
    # full text inline instead of a separate source_catalog keyed by slice id.
    packet = outcome.result.receipt["explanation"]["raw"]["request"]
    by_id = {c["candidate_id"]: c for c in packet["candidates"]}
    assert by_id["L22"]["text"] == acceptance.FIXTURES["L22"]["text"]
    assert by_id["A22"]["text"] == acceptance.FIXTURES["A22"]["text"]
    # the governing side is supplied in full too, not trimmed to an atom
    assert packet["governing"]["part_text"]
    # case 10's boundary is complete, so absence would be provable here
    assert packet["allowed_boundary_proof_ids"]


def test_result_projection_uses_the_original_run_context(monkeypatch):
    from portal.modules.compliance.core import assessment_runs
    from portal.modules.compliance.tools import compliance_mcp

    original = {
        "effective_on": "2026-09-12",
        "kb_id": "fixture-original",
        "scope_text": "declared scope",
    }
    monkeypatch.setattr(
        assessment_runs, "run_result", lambda _: {"results": [], "request": original}
    )

    def capture(rows, effective_on, kb_id, max_rows, verbose, **kwargs):
        return {"date": effective_on, "kb": kb_id, "scope": kwargs["scope_text"]}

    monkeypatch.setattr(compliance_mcp, "_gaps_payload", capture)
    result = compliance_mcp.compliance_gaps(
        operation="result",
        run_id="exact-run",
        kb_id="wrong-kb",
        effective_on="2026-09-13",
        scope="wrong-scope",
    )
    assert result == {
        "date": original["effective_on"],
        "kb": original["kb_id"],
        "scope": original["scope_text"],
    }


def test_live_gap_handle_resolves_by_sources_not_model_spelling(tmp_path):
    case = acceptance.CASES["10"]
    result = asdict(acceptance.run_case(case, acceptance.Repository(tmp_path / "ids.db")).result)
    result["gaps"][0]["gap_id"] = "live-gap-7"
    checks = runner._live_checks(case, result)
    identity = next(c for c in checks if c["name"] == "gap_ids")
    assert identity["ok"]
    assert identity["detail"]["fixture_identity_map"] == {"g10": "live-gap-7"}
    result["gaps"][0]["internal_counterevidence_slice_ids"] = ["cand-A22"]
    assert not next(c for c in runner._live_checks(case, result) if c["name"] == "gap_ids")["ok"]

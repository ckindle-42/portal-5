"""Unit tests for the candidate intake pipeline.

After M6-B1, the implementation lives in bench_security.intake.
Monkeypatches must target bench_security.intake (the module where the
functions are actually defined) rather than the chain re-export shim.
"""


def test_run_candidate_intake_dry_run():
    from tests.benchmarks.bench_security.chain import run_candidate_intake

    results = run_candidate_intake(["fake/model-a", "fake/model-b"], dry_run=True)
    assert len(results) == 2
    assert all(r["queued"] for r in results)
    assert all(r["skip_reason"] is None for r in results)


def test_run_candidate_intake_pull_fail(monkeypatch):
    from tests.benchmarks.bench_security import intake as _intake
    from tests.benchmarks.bench_security.chain import run_candidate_intake

    monkeypatch.setattr(
        _intake, "_pull_model", lambda m, **kw: {"model": m, "pulled": False, "error": "404"}
    )
    results = run_candidate_intake(["fake/model-x"], skip_pull=False)
    assert results[0]["queued"] is False
    assert "pull failed" in results[0]["skip_reason"]


def test_run_candidate_intake_tps_below_floor(monkeypatch):
    from tests.benchmarks.bench_security import intake as _intake
    from tests.benchmarks.bench_security.chain import run_candidate_intake

    monkeypatch.setattr(
        _intake, "_pull_model", lambda m, **kw: {"model": m, "pulled": True, "error": None}
    )
    monkeypatch.setattr(
        _intake,
        "_tps_warmup",
        lambda m, **kw: {
            "model": m,
            "tps": 5.0,
            "below_floor": True,
            "elapsed_s": 1.0,
            "tokens": 5,
            "error": None,
        },
    )
    results = run_candidate_intake(["fake/slow-model"])
    assert results[0]["queued"] is False
    assert "below floor" in results[0]["skip_reason"]


def test_run_candidate_intake_tool_fail(monkeypatch):
    from tests.benchmarks.bench_security import intake as _intake
    from tests.benchmarks.bench_security.chain import run_candidate_intake

    monkeypatch.setattr(
        _intake, "_pull_model", lambda m, **kw: {"model": m, "pulled": True, "error": None}
    )
    monkeypatch.setattr(
        _intake,
        "_tps_warmup",
        lambda m, **kw: {
            "model": m,
            "tps": 45.0,
            "below_floor": False,
            "elapsed_s": 2.0,
            "tokens": 90,
            "error": None,
        },
    )
    monkeypatch.setattr(
        _intake,
        "_audit_tools_probe",
        lambda m, **kw: {"model": m, "outcome": "text_only", "detail": "no tool_calls"},
    )
    results = run_candidate_intake(["fake/notool-model"])
    assert results[0]["queued"] is False
    assert "tool probe" in results[0]["skip_reason"]


def test_run_candidate_intake_all_pass(monkeypatch):
    from tests.benchmarks.bench_security import intake as _intake
    from tests.benchmarks.bench_security.chain import run_candidate_intake

    monkeypatch.setattr(
        _intake, "_pull_model", lambda m, **kw: {"model": m, "pulled": True, "error": None}
    )
    monkeypatch.setattr(
        _intake,
        "_tps_warmup",
        lambda m, **kw: {
            "model": m,
            "tps": 35.0,
            "below_floor": False,
            "elapsed_s": 3.0,
            "tokens": 105,
            "error": None,
        },
    )
    monkeypatch.setattr(
        _intake,
        "_audit_tools_probe",
        lambda m, **kw: {"model": m, "outcome": "tool_call", "detail": "1 call"},
    )
    results = run_candidate_intake(["fake/good-model-a", "fake/good-model-b"])
    assert all(r["queued"] for r in results)
    assert all(r["skip_reason"] is None for r in results)


def test_tps_floor_constant():
    from tests.benchmarks.bench_security.chain import TPS_FLOOR

    assert TPS_FLOOR == 20.0


def test_pull_timeout_constant():
    from tests.benchmarks.bench_security.chain import PULL_TIMEOUT_S

    assert PULL_TIMEOUT_S == 900.0

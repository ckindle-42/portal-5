"""Offline contracts for the candidate engine-evaluation runner."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from tests.benchmarks import engine_eval_instrument as instrument
from tests.benchmarks import engine_eval_runner as runner


def test_candidate_cells_use_registry_argv_and_fixed_pipeline_backend() -> None:
    cells = runner.candidate_cells()

    assert cells
    assert {cell["seat"] for cell in cells} == {
        "daily-moe",
        "coding",
        "task-router",
        "hunt",
        "council-json",
    }
    assert all(cell["engine_kind"] == "managed" for cell in cells)
    assert all(cell["backend"] for cell in cells)
    assert all(cell["argv"] or cell["launch_error"] for cell in cells)
    assert all(cell["backend"] != "eval-openai" or cell["port"] == 11234 for cell in cells)


def test_stage3_requires_a_valid_canary_for_this_build_and_cell(tmp_path: Path) -> None:
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
    }
    path = runner.canary_receipt_path(tmp_path, "build-a", cell)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"build": "build-a", "valid": True}), encoding="utf-8")

    assert runner.require_valid_canary(tmp_path, "build-a", cell)["valid"] is True
    with pytest.raises(runner.Stage3BlockedError, match="current build"):
        runner.require_valid_canary(tmp_path, "build-b", cell)

    path.write_text(json.dumps({"build": "build-a", "valid": False}), encoding="utf-8")
    with pytest.raises(runner.Stage3BlockedError, match="canary invalid"):
        runner.require_valid_canary(tmp_path, "build-a", cell)


def test_stage3_persists_block_receipt_for_protocol_mismatch(monkeypatch, tmp_path: Path) -> None:
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
    }
    canary_path = runner.canary_receipt_path(tmp_path, "build-a", cell)
    canary_path.parent.mkdir(parents=True)
    canary_path.write_text(
        json.dumps({"build": "build-a", "valid": True, "receipt": str(canary_path)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "protocol_issues", lambda: {"quality-seat": ["unmapped plan"]})

    result = runner.run_stage3(cell, "quality-seat")
    receipt = Path(result["receipt"])

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "unmapped plan"
    assert json.loads(receipt.read_text(encoding="utf-8")) == result


def test_failed_startup_is_recorded_with_logs_and_engine_models_body(monkeypatch, tmp_path: Path):
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
        "expected_model": "Qwen3.8-27B-4bit",
        "backend": "eval-openai-rapid-mlx",
        "port": 11235,
        "base": "http://127.0.0.1:11235",
        "launch_error": None,
        "argv": ["rapid-mlx"],
    }
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: (True, "ok"))
    monkeypatch.setattr(runner.h2h, "single_flight", nullcontext)
    monkeypatch.setattr(runner.h2h, "pid_on_port", lambda _port: None)
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_a, **_kw: "vm_stat")
    stopped = []
    monkeypatch.setattr(runner.h2h, "stop_managed", lambda _cfg, engine: stopped.append(engine))

    def fail_start(_cfg, _engine, _model, _mode, *, log_paths, on_started, **_kwargs):
        log_paths[0].write_text("startup stdout", encoding="utf-8")
        log_paths[1].write_text("invalid parser value", encoding="utf-8")
        on_started()
        raise SystemExit("engine process exited during startup (exit 2)")

    monkeypatch.setattr(runner.h2h, "start_managed", fail_start)
    monkeypatch.setattr(
        runner,
        "_models_payload",
        lambda _base: (_ for _ in ()).throw(runner.CandidateHTTPError(503, "still loading")),
    )

    receipt = runner.run_cell(cell, "http://pipeline")
    payload = json.loads(Path(receipt["receipt"]).read_text(encoding="utf-8"))

    assert receipt["valid"] is False
    assert "exit 2" in receipt["failures"][0]
    assert receipt["engine_models_response"]["status"] == 503
    assert receipt["engine_models_response"]["raw"] == "still loading"
    assert Path(receipt["engine_logs"]["stdout"]).read_text() == "startup stdout"
    assert Path(receipt["engine_logs"]["stderr"]).read_text() == "invalid parser value"
    assert payload["engine_logs"]["stderr"] == receipt["engine_logs"]["stderr"]
    assert stopped == ["rapid-mlx"]


def test_canary_continues_after_an_invalid_cell(monkeypatch, tmp_path: Path):
    cells = [
        {
            "engine": "rapid-mlx",
            "mode": "plain",
            "seat": "coding",
            "workspace": "bench-engine-coding",
            "model": "m1",
        },
        {
            "engine": "mlx-serve",
            "mode": "plain",
            "seat": "hunt",
            "workspace": "bench-engine-hunt",
            "model": "m2",
        },
    ]
    seen = []
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)

    def fake_run_cell(cell, _pipeline, build):
        seen.append(cell["engine"])
        return {
            "build": build,
            "cell": {key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")},
            "valid": cell["engine"] == "mlx-serve",
            "failures": [] if cell["engine"] == "mlx-serve" else ["startup exit 2"],
            "evidence_sources": {"logs": ["stdout.log", "stderr.log"]},
        }

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)
    results, exit_code = runner.run_canary("http://pipeline")

    assert seen == ["rapid-mlx", "mlx-serve"]
    assert [row["valid"] for row in results] == [False, True]
    assert exit_code == 2


def test_quality_plan_pins_same_model_to_omlx_incumbent_and_candidate(tmp_path: Path):
    cell = next(
        item
        for item in runner.candidate_cells()
        if item["seat"] == "daily-moe" and item["mode"] == "plain"
    )

    plan_path, source, _selections, plan = runner._wfe_plan(
        cell, tmp_path, "build-a", "quality-seat", compare=True
    )
    workload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))["workloads"][cell["workspace"]]
    incumbent = workload["arms"]["incumbent"]
    challenger = workload["arms"]["challengers"][0]

    assert source == "tests/wfe/plans/engine_h2h_202611_nemotron.yaml"
    assert workload["source_workspace"] == "auto-daily"
    assert incumbent["backend"] == "eval-openai-omlx-incumbent"
    assert incumbent["model"] == cell["expected_model"]
    assert challenger["backend"] == cell["backend"]
    assert challenger["model"] == cell["expected_model"]


def test_registered_protocol_has_no_unmapped_plan_or_seat_references():
    protocol = runner.yaml.safe_load(runner.PROTOCOL.read_text(encoding="utf-8"))
    plans = {
        plan
        for workload in protocol["workloads"]
        if workload["id"] == "quality-seat"
        for plan in workload["plans"]
    }

    assert not runner.protocol_issues()
    assert protocol["status"] == "APPROVED"
    assert protocol["approved_by"] == "operator"
    assert protocol["approved_on"].isoformat() == "2026-11-13"
    assert "coding_decision_v1" not in " ".join(sorted(plans))


def test_stage3_dispatches_after_canary_and_reuses_completed_receipt(monkeypatch, tmp_path: Path):
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
        "expected_model": "Qwen3.8-27B-4bit",
        "backend": "eval-openai-rapid-mlx",
        "port": 11235,
        "base": "http://127.0.0.1:11235",
        "launch_error": None,
        "argv": ["rapid-mlx"],
    }
    build = "build-a"
    canary_path = runner.canary_receipt_path(tmp_path, build, cell)
    canary_path.parent.mkdir(parents=True)
    canary_path.write_text(json.dumps({"build": build, "valid": True}), encoding="utf-8")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner, "current_build", lambda: build)
    calls = []
    monkeypatch.setattr(
        runner,
        "_run_long_context",
        lambda *args: calls.append(args) or {"status": "PASS", "valid": True},
    )

    first = runner.run_stage3(cell, "long-context", pipeline="http://pipeline")
    second = runner.run_stage3(cell, "long-context", pipeline="http://pipeline")

    assert first["status"] == "PASS"
    assert second == first
    assert len(calls) == 1


def test_stage0_prints_before_and_after_residency(monkeypatch, capsys) -> None:
    evidence = instrument.golden_evidence()
    evidence["residency"] = {
        "before": {"ollama": {}, "omlx": {}, "rapid-mlx": {"model": 123}},
        "after": {"ollama": {}, "omlx": {}, "rapid-mlx": {"model": 123}},
    }
    monkeypatch.setattr(instrument, "collect_stage0", lambda _spec, _pipeline: evidence)

    assert instrument.stage0(["--engine", "ollama", "--seat", "daily-moe"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["residency"] == evidence["residency"]


def test_raw_candidate_receipts_require_portal_data_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PORTAL_DATA_ROOT", raising=False)
    with pytest.raises(runner.Stage3BlockedError, match="PORTAL_DATA_ROOT"):
        runner.data_root()

    monkeypatch.setenv("PORTAL_DATA_ROOT", str(tmp_path))
    assert runner.data_root() == tmp_path

"""Offline contracts for the candidate engine-evaluation runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    cell = {"engine": "rapid-mlx", "mode": "plain", "seat": "coding"}
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
    cell = {"engine": "rapid-mlx", "mode": "plain", "seat": "coding"}
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

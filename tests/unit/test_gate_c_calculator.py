"""Tests for gate_c_calculator.py against real arm receipts and fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_c_calculator import (  # noqa: E402
    compute_gate_c_threshold,
    extract_discipline_rates,
    load_receipts,
    wilson_lower_bound,
)
from orchestration_acceptance import _bite, _run_task  # noqa: E402
from orchestration_fake_pipeline import finish_response  # noqa: E402


def _write_config(path: Path, *, criteria: dict[str, Any] | None = None) -> Path:
    config = {
        "disciplines": {
            "test_fixing": {
                "pass_criteria": criteria
                or {
                    "minimum_bite_pass_rate": 0.8,
                    "minimum_fast_pass_rate": 0.8,
                    "minimum_deep_pass_rate": 0.9,
                }
            }
        }
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _row(
    bite_id: str,
    *,
    state: str | None = "passed",
    status: str | None = None,
    discipline: str | None = "test_fixing",
    seat: str | None = "fast",
) -> dict[str, Any]:
    row: dict[str, Any] = {"bite_id": bite_id}
    if state is not None:
        row["state"] = state
    if status is not None:
        row["status"] = status
    if discipline is not None:
        row["discipline"] = discipline
    if seat is not None:
        row["model"] = seat
    return row


def test_wilson_lower_bound_basic():
    """Standard Wilson values stay correct."""
    assert 0.7 < wilson_lower_bound(10, 10) < 1.0
    assert 0.1 < wilson_lower_bound(5, 10) < 0.5
    assert wilson_lower_bound(0, 10) == 0.0
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0.88 < wilson_lower_bound(95, 100) < 0.96


def test_wilson_lower_bound_edge_cases():
    """Single-sample boundaries remain finite."""
    assert wilson_lower_bound(1, 1) > 0.0
    assert wilson_lower_bound(0, 1) == 0.0


def test_extract_discipline_rates():
    """Extraction counts final rows per discipline and seat."""
    receipts = [
        {
            "results": [
                _row("b1"),
                _row("b2"),
                _row("b3", state="blocked", seat="deep"),
            ]
        },
        {
            "results": [
                _row("b4", discipline="detection_engineering"),
                _row("b5", discipline="detection_engineering", seat="deep"),
            ]
        },
    ]

    rates = extract_discipline_rates(receipts)

    assert rates["test_fixing"]["fast"] == (2, 2)
    assert rates["test_fixing"]["deep"] == (0, 1)
    assert rates["detection_engineering"]["fast"] == (1, 1)
    assert rates["detection_engineering"]["deep"] == (1, 1)


def test_extract_ignores_non_final_states():
    """Waiting, paused and in-flight rows never count as failures."""
    receipts = [
        {
            "results": [
                _row("b1", state="waiting", status="PASS"),
                _row("b2", state="paused_for_replan", status="FAIL"),
                _row("b3", state="running", status="PASS"),
                _row("b4", state="passed"),
            ]
        }
    ]

    rates = extract_discipline_rates(receipts)

    assert rates == {"test_fixing": {"fast": (1, 1)}}


def test_extract_joins_plan_when_rows_lack_identity():
    """An ArmService receipt without discipline/model joins its plan.json."""
    receipts = [
        {
            "results": [_row("b1", discipline=None, seat=None)],
            "plan": {
                "bites": [
                    {"bite_id": "b1", "discipline": "test_fixing", "model": "deep"},
                ]
            },
        }
    ]

    rates = extract_discipline_rates(receipts)

    assert rates == {"test_fixing": {"deep": (1, 1)}}


def test_extract_rejects_unknown_seat():
    """A model tag is not silently attributed to Fast."""
    receipts = [{"results": [_row("b1", seat="Qwen3.8-27B-oQ4e-mtp")]}]
    with pytest.raises(ValueError, match="unknown seat"):
        extract_discipline_rates(receipts)


def test_extract_requires_results_list():
    """Malformed results fail loudly instead of yielding empty rates."""
    with pytest.raises(ValueError, match="receipt.results must be a list"):
        extract_discipline_rates([{"results": {"bite_id": "b1"}}])


def test_compute_threshold_is_task_level_and_criteria_derived(tmp_path: Path):
    """The floor is the product of fixed criteria over the task's bites."""
    config = _write_config(tmp_path / "arm.yaml")
    receipts = [
        {
            "results": [_row("f1"), _row("d1", seat="deep")],
            "plan": {
                "bites": [
                    {"bite_id": "f1", "discipline": "test_fixing", "model": "fast"},
                    {"bite_id": "d1", "discipline": "test_fixing", "model": "deep"},
                ]
            },
        }
    ]

    threshold, details = compute_gate_c_threshold(receipts, minimum_samples=1, config_path=config)

    assert threshold == pytest.approx(0.8 * 0.9)
    assert details["threshold_domain"] == "task-level projected pass probability"
    assert details["pass_criteria_met"] is True
    assert details["rates_by_discipline"]["test_fixing"]["fast"]["pass_probability"] == 1.0


def test_compute_requires_minimum_samples(tmp_path: Path):
    """One observation is not enough evidence, even at 1/1."""
    config = _write_config(tmp_path / "arm.yaml")
    receipts = [{"results": [_row("b1")]}]
    with pytest.raises(ValueError, match="insufficient evidence"):
        compute_gate_c_threshold(receipts, minimum_samples=5, config_path=config)


def test_compute_zero_of_one_cannot_produce_a_zero_threshold(tmp_path: Path):
    """A failing cell lowers the observed rate and blocks criteria, never the floor to 0."""
    config = _write_config(tmp_path / "arm.yaml")
    receipts = [{"results": [_row("b1", state="blocked")]}]

    threshold, details = compute_gate_c_threshold(receipts, minimum_samples=1, config_path=config)

    assert threshold == pytest.approx(0.8)
    assert details["pass_criteria_met"] is False
    assert details["pass_criteria"]["test_fixing"]["observed"]["fast_pass_rate"] == 0.0


def test_compute_ignores_partial_receipt_rows(tmp_path: Path):
    """A receipt with only non-final rows contributes no evidence and no task shape."""
    config = _write_config(tmp_path / "arm.yaml")
    receipts = [{"results": [_row("b1", state="waiting")]}]
    with pytest.raises(ValueError, match="No final per-bite results"):
        compute_gate_c_threshold(receipts, minimum_samples=1, config_path=config)


def test_compute_requires_pre_written_criteria(tmp_path: Path):
    """A discipline without fixed pass_criteria cannot derive an independent floor."""
    config = _write_config(tmp_path / "arm.yaml")
    receipts = [
        {
            "results": [
                _row("b1", discipline="offline-rig"),
                _row("b2", discipline="offline-rig"),
            ]
        }
    ]
    with pytest.raises(ValueError, match="no pre-written pass_criteria"):
        compute_gate_c_threshold(receipts, minimum_samples=1, config_path=config)


def test_compute_consumes_a_real_arm_receipt(tmp_path: Path):
    """End-to-end: ArmService.submit -> load_receipts -> threshold + pasteable rates."""
    root = tmp_path / "tasks"
    bites = [_bite(f"f{index}", discipline="test_fixing") for index in range(5)]
    bites += [_bite(f"d{index}", discipline="test_fixing", model="deep") for index in range(5)]
    responses = [("fast", finish_response({"answer": "right"})) for _ in range(5)]
    responses += [("deep", finish_response({"answer": "right"})) for _ in range(5)]
    receipt, _ = _run_task(root, "real", responses, bites)
    assert receipt["status"] == "PASS"

    receipts = load_receipts([root / "real"])
    assert receipts[0]["plan"]["task_id"] == "real"
    threshold, details = compute_gate_c_threshold(receipts, minimum_samples=5)

    assert threshold == pytest.approx(0.8**5 * 0.9**5)
    rates = details["rates_by_discipline"]["test_fixing"]
    assert rates["fast"]["samples"] == 5 and rates["deep"]["samples"] == 5
    assert rates["fast"]["mean_seconds_source"] == "checks.json"
    assert details["pass_criteria_met"] is True
    assert details["per_discipline_seat"]["test_fixing/fast"]["wilson_lower"] > 0


def test_load_receipts_attaches_plan_and_elapsed(tmp_path: Path):
    """Directory loading joins plan.json and checks.json time evidence."""
    task_dir = tmp_path / "task1"
    attempt = task_dir / "bites" / "b1" / "attempts" / "01"
    attempt.mkdir(parents=True)
    (task_dir / "plan.json").write_text(
        json.dumps(
            {
                "task_id": "t1",
                "goal": "g",
                "bites": [{"bite_id": "b1", "discipline": "test_fixing", "model": "fast"}],
            }
        )
    )
    (task_dir / "receipt.json").write_text(
        json.dumps({"task_id": "t1", "results": [{"bite_id": "b1", "state": "passed"}]})
    )
    (attempt / "checks.json").write_text(json.dumps({"elapsed_seconds": 2.5}))

    receipts = load_receipts([tmp_path])

    assert len(receipts) == 1
    assert receipts[0]["plan"]["task_id"] == "t1"
    assert receipts[0]["results"][0]["elapsed_seconds"] == 2.5


def test_load_receipts_missing_file_warns(tmp_path: Path, capsys: pytest.CaptureFixture):
    """A missing path is skipped with a warning, not treated as invalid JSON."""
    from gate_c_calculator import load_receipts as load

    assert load([tmp_path / "missing.json"]) == []
    assert "not found" in capsys.readouterr().err


def test_cli_outputs_threshold_only(tmp_path: Path, capsys: pytest.CaptureFixture):
    """The default CLI output is just the value for shell capture."""
    from gate_c_calculator import main

    config = _write_config(tmp_path / "arm.yaml")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"results": [_row("b1"), _row("b2")]}))
    sys.argv = [
        "gate_c_calculator.py",
        "--minimum-samples",
        "1",
        "--config",
        str(config),
        str(receipt),
    ]
    assert main() == 0
    output = capsys.readouterr().out.strip()
    assert float(output) == pytest.approx(0.64)


def test_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--json carries rates, task floors and criteria status."""
    from gate_c_calculator import main

    config = _write_config(tmp_path / "arm.yaml")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"results": [_row("b1"), _row("b2")]}))
    sys.argv = [
        "gate_c_calculator.py",
        "--json",
        "--minimum-samples",
        "1",
        "--config",
        str(config),
        str(receipt),
    ]
    assert main() == 0
    data = json.loads(capsys.readouterr().out)

    assert data["threshold"] == pytest.approx(0.64)
    assert "rates_by_discipline" in data
    assert "pass_criteria" in data
    assert data["per_discipline_seat"]["test_fixing/fast"]["total"] == 2


def test_cli_confidence_levels(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Higher confidence lowers the evidence bound, not the criteria floor."""
    from gate_c_calculator import main

    config = _write_config(tmp_path / "arm.yaml")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"results": [_row(f"b{index}") for index in range(4)]}))

    outputs = []
    for confidence in ("0.90", "0.95", "0.99"):
        sys.argv = [
            "gate_c_calculator.py",
            "--json",
            "--minimum-samples",
            "1",
            "--config",
            str(config),
            "--confidence",
            confidence,
            str(receipt),
        ]
        assert main() == 0
        outputs.append(
            json.loads(capsys.readouterr().out)["per_discipline_seat"]["test_fixing/fast"][
                "wilson_lower"
            ]
        )

    assert outputs[0] > outputs[1] > outputs[2]


def test_cli_missing_receipt(tmp_path: Path):
    """A missing path reports "no files" (exit 2), distinct from invalid JSON (exit 3)."""
    from gate_c_calculator import main

    sys.argv = ["gate_c_calculator.py", str(tmp_path / "nonexistent.json")]
    assert main() == 2


def test_cli_invalid_json(tmp_path: Path):
    """Invalid JSON exits 3."""
    from gate_c_calculator import main

    receipt = tmp_path / "bad.json"
    receipt.write_text("not json")
    sys.argv = ["gate_c_calculator.py", str(receipt)]
    assert main() == 3


def test_cli_missing_config(tmp_path: Path):
    """A missing arm config is a policy error (exit 3), not a traceback."""
    from gate_c_calculator import main

    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"results": [_row("b1")]}))
    sys.argv = [
        "gate_c_calculator.py",
        "--minimum-samples",
        "1",
        "--config",
        str(tmp_path / "missing.yaml"),
        str(receipt),
    ]
    assert main() == 3


def test_cli_does_not_write_config(tmp_path: Path, capsys: pytest.CaptureFixture):
    """The calculator is read-only, including the arm config."""
    from gate_c_calculator import main

    config = _write_config(tmp_path / "arm.yaml")
    before = config.read_bytes()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"results": [_row("b1")]}))
    sys.argv = [
        "gate_c_calculator.py",
        "--minimum-samples",
        "1",
        "--config",
        str(config),
        str(receipt),
    ]
    assert main() == 0
    capsys.readouterr()

    assert config.read_bytes() == before

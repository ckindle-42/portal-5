"""The analyst proof driver preserves ids and terminates on partial or missing jobs."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.hunt_bed import owui_proof


def test_driver_persists_partial_terminal_receipt(monkeypatch, tmp_path: Path) -> None:
    hunt_dir = tmp_path / "hunts"
    out_dir = tmp_path / "receipts"
    hunt_dir.mkdir()
    job_id = "hunt-0123456789ab"
    (hunt_dir / f"{job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": "PARTIAL",
                "coverage_complete": False,
                "coverage_reason": "term coverage unknown",
                "progress": {"phase": "partial", "query_count": 7},
            }
        )
    )
    prompts = []

    def ask(prompt: str, _key: str, _model: str) -> str:
        prompts.append(prompt)
        return f"Started {job_id}" if len(prompts) == 1 else "partial evidence"

    monkeypatch.setattr(owui_proof, "ask", ask)
    monkeypatch.setattr(owui_proof, "HUNTS", hunt_dir)
    monkeypatch.setenv("OWUI_API_KEY", "test")
    monkeypatch.setattr(
        "sys.argv",
        [
            "owui_proof.py",
            "--index",
            "test-index",
            "--out",
            str(out_dir),
            "--poll-s",
            "0.01",
        ],
    )

    result = owui_proof.main()

    receipt = json.loads((out_dir / "test-index.json").read_text())
    assert result == 2
    assert receipt["job_id"] == job_id
    assert receipt["job_status"] == "PARTIAL"
    assert receipt["coverage_complete"] is False
    assert receipt["status_samples"][-1]["status"] == "PARTIAL"
    assert len(prompts) == 3
    assert all(job_id in prompt for prompt in prompts[1:])


def test_driver_does_not_repeat_start_when_id_is_malformed(monkeypatch, tmp_path: Path) -> None:
    prompts = []
    monkeypatch.setattr(
        owui_proof,
        "ask",
        lambda prompt, _key, _model: prompts.append(prompt) or "hunt-0123456789abg",
    )
    monkeypatch.setattr(owui_proof, "HUNTS", tmp_path / "hunts")
    monkeypatch.setenv("OWUI_API_KEY", "test")
    out_dir = tmp_path / "receipts"
    monkeypatch.setattr(
        "sys.argv",
        ["owui_proof.py", "--index", "test-index", "--out", str(out_dir)],
    )

    result = owui_proof.main()

    receipt = json.loads((out_dir / "test-index.json").read_text())
    assert result == 4
    assert len(prompts) == 1
    assert receipt["job_status"] == "START_ID_UNKNOWN"
    assert "job_id" not in receipt


def test_driver_times_out_when_status_file_never_appears(monkeypatch, tmp_path: Path) -> None:
    prompts = []
    job_id = "hunt-0123456789ab"
    monkeypatch.setattr(
        owui_proof,
        "ask",
        lambda prompt, _key, _model: prompts.append(prompt) or f"Started {job_id}",
    )
    monkeypatch.setattr(owui_proof, "HUNTS", tmp_path / "hunts")
    monkeypatch.setenv("OWUI_API_KEY", "test")
    out_dir = tmp_path / "receipts"
    monkeypatch.setattr(
        "sys.argv",
        [
            "owui_proof.py",
            "--index",
            "test-index",
            "--out",
            str(out_dir),
            "--job-timeout-s",
            "0.02",
            "--poll-s",
            "0.01",
        ],
    )

    result = owui_proof.main()

    receipt = json.loads((out_dir / "test-index.json").read_text())
    assert result == 3
    assert receipt["job_id"] == job_id
    assert receipt["job_status"] == "SUPERVISION_TIMEOUT"
    assert len(prompts) == 1

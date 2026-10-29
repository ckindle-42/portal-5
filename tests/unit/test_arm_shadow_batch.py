"""Offline tests for scripts/arm_shadow_batch.py (the Spark n>=20 shadow sample).

No Pipeline: the dry run materializes the WFE suite's seed fixtures and the summary gate
is exercised against a fabricated shadow_comparisons.jsonl.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "arm_shadow_batch.py"

_SPEC = importlib.util.spec_from_file_location("arm_shadow_batch", SCRIPT_PATH)
batch = importlib.util.module_from_spec(_SPEC)
sys.modules["arm_shadow_batch"] = batch
_SPEC.loader.exec_module(batch)


def _comparison(agree: bool) -> dict:
    return {"shadow_verdict": agree, "incumbent_verdict": agree, "agree": agree}


def test_dry_run_materializes_seeds_and_names_unique_tasks(tmp_path: Path, capsys) -> None:
    code = batch.main(["--dry-run", "--repeat", "3", "--tasks-dir", str(tmp_path / "tasks")])

    assert code == 0
    plans = json.loads(capsys.readouterr().out)
    cases = batch._cases(batch.DEFAULT_SUITE)
    assert len(plans) == len(cases) * 3
    assert len({plan["task_id"] for plan in plans}) == len(plans)
    for plan in plans:
        bite_ids = [bite["bite_id"] for bite in plan["bites"]]
        assert bite_ids == ["inspect", "repair", "final_review"]
        assert plan["bites"][0]["model"] == "fast"
    sources = sorted((tmp_path / "tasks" / "_shadow_sources").iterdir())
    assert sources
    assert all(
        (source / "clamp.py").is_file() or (source / "percent.py").is_file() for source in sources
    )


def test_a_shadow_sample_below_the_floor_fails_the_run(tmp_path: Path, capsys) -> None:
    task_dir = tmp_path / "tasks" / "shadow-a"
    task_dir.mkdir(parents=True)
    (task_dir / "shadow_comparisons.jsonl").write_text(
        json.dumps(_comparison(True)) + "\n", encoding="utf-8"
    )

    code = batch.main(
        [
            "--summary-only",
            "--repeat",
            "1",
            "--tasks-dir",
            str(tmp_path / "tasks"),
            "--workdir",
            str(tmp_path / "sources"),
            "--minimum-compared",
            "20",
            "--wait-seconds",
            "0",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert out["shadow"]["compared"] == 1
    assert code == 1


def test_a_shadow_sample_at_the_floor_passes(tmp_path: Path, capsys) -> None:
    task_dir = tmp_path / "tasks" / "shadow-a"
    task_dir.mkdir(parents=True)
    rows = [_comparison(True), _comparison(False), {"shadow_verdict": None, "error": "boom"}]
    (task_dir / "shadow_comparisons.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )

    code = batch.main(
        [
            "--summary-only",
            "--repeat",
            "1",
            "--tasks-dir",
            str(tmp_path / "tasks"),
            "--workdir",
            str(tmp_path / "sources"),
            "--minimum-compared",
            "2",
            "--wait-seconds",
            "0",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert out["shadow"]["compared"] == 2
    assert out["shadow"]["errors"] == 1
    assert code == 0


def test_a_missing_seat_digest_fails_before_any_submission(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("PORTAL_ARM_FAST_DIGEST", raising=False)
    monkeypatch.delenv("PORTAL_ARM_DEEP_DIGEST", raising=False)

    code = batch.main(
        [
            "--repeat",
            "1",
            "--tasks-dir",
            str(tmp_path / "tasks"),
            "--workdir",
            str(tmp_path / "sources"),
        ]
    )

    assert code == 2
    assert "PORTAL_ARM_FAST_DIGEST" in capsys.readouterr().err
    assert not any((tmp_path / "tasks").glob("shadow-*"))

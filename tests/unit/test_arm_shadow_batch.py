"""Offline tests for scripts/arm_shadow_batch.py (the Spark n>=20 shadow sample).

No Pipeline: the dry run materializes the WFE suite's seed fixtures and the summary gate
is exercised against a fabricated shadow_comparisons.jsonl.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from portal.modules.orchestration import service as arm_service

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


def _hide_digest_sources(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PORTAL_ARM_FAST_DIGEST", raising=False)
    monkeypatch.delenv("PORTAL_ARM_DEEP_DIGEST", raising=False)
    monkeypatch.setattr(arm_service, "ARM_DIGESTS_ENV", tmp_path / "missing.env")
    monkeypatch.setattr(arm_service, "_fetch_ollama_tags", lambda: {})


def test_a_missing_seat_digest_fails_before_any_submission(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _hide_digest_sources(monkeypatch, tmp_path)

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


def test_ollama_tags_supply_digests_when_the_env_var_is_unset(tmp_path: Path, monkeypatch) -> None:
    _hide_digest_sources(monkeypatch, tmp_path)
    config = batch.load_arm_config(batch.DEFAULT_CONFIG)
    models = config["load_plan_models"]
    monkeypatch.setattr(
        arm_service,
        "_fetch_ollama_tags",
        lambda: {
            "models": [
                {"name": models["fast"]["model"], "digest": "sha256:fast"},
                {"name": models["deep"]["model"], "digest": "sha256:deep"},
            ]
        },
    )

    engines = batch._engines(config, "http://127.0.0.1:9099", "")

    assert engines["fast"].model_digest == "sha256:fast"
    assert engines["deep"].model_digest == "sha256:deep"


def test_arm_digests_env_file_covers_a_seat_the_tags_omit(tmp_path: Path, monkeypatch) -> None:
    _hide_digest_sources(monkeypatch, tmp_path)
    env_file = tmp_path / "arm_digests.env"
    env_file.write_text(
        "PORTAL_ARM_FAST_DIGEST=sha256:filefast\nPORTAL_ARM_DEEP_DIGEST=sha256:filedeep\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(arm_service, "ARM_DIGESTS_ENV", env_file)

    engines = batch._engines(
        batch.load_arm_config(batch.DEFAULT_CONFIG), "http://127.0.0.1:9099", ""
    )

    assert engines["fast"].model_digest == "sha256:filefast"
    assert engines["deep"].model_digest == "sha256:filedeep"


def test_the_env_var_overrides_tags_and_the_env_file(tmp_path: Path, monkeypatch) -> None:
    _hide_digest_sources(monkeypatch, tmp_path)
    monkeypatch.setenv("PORTAL_ARM_FAST_DIGEST", "env-fast")
    monkeypatch.setenv("PORTAL_ARM_DEEP_DIGEST", "env-deep")
    monkeypatch.setattr(
        arm_service,
        "_fetch_ollama_tags",
        lambda: {"models": [{"name": "gemma4:26b-a4b-it-qat-ctx32k", "digest": "sha256:nope"}]},
    )

    engines = batch._engines(
        batch.load_arm_config(batch.DEFAULT_CONFIG), "http://127.0.0.1:9099", ""
    )

    assert engines["fast"].model_digest == "env-fast"
    assert engines["deep"].model_digest == "env-deep"

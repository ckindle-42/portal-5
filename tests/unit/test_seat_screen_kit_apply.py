"""Tests for the coder-seat kit dry-run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from scripts.seat_screen import kit_apply


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "config/personas").mkdir(parents=True)
    (repo / "config/portal.yaml").write_text(
        "workspaces:\n  auto-coding:\n    name: coding\n  auto-spl:\n    name: spl\n"
    )
    (repo / "config/backends.yaml").write_text(
        "backends:\n"
        "  id: ollama-coding\n"
        "  models:\n"
        "  id: omlx-coding\n"
        "  models:\n"
        "    hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M: Qwen3.8-27B-oQ4e-mtp\n"
    )
    return repo


def test_apply_dry_run_renders_temp_config_and_runs_config_audit(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    original_portal = (repo / "config/portal.yaml").read_bytes()
    calls: list[list[str]] = []
    applied_seats: set[str] = set()

    def audit(
        command: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd != repo
        portal = (cwd / "config/portal.yaml").read_text()
        backends = (cwd / "config/backends.yaml").read_text()
        workspaces = yaml.safe_load(portal)["workspaces"]
        for workspace_id in ("auto-coding", "auto-spl"):
            applied_seats.add(workspace_id)
            applied_seats.update(
                f"{workspace_id}::{variant_id}"
                for variant_id in workspaces[workspace_id].get("variants", {})
            )
        assert "kit-qwen38-27b:" in portal
        assert "Qwen3.8-27B-Uncensored-MLX-4bit" in backends
        assert (cwd / "config/personas/kitqwen3827b.yaml").is_file()
        workspace_arg = command.index("--workspace")
        assert set(command[workspace_arg + 1 :]) == applied_seats
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "WFE config audit passed", "")

    monkeypatch.setattr(kit_apply.subprocess, "run", audit)
    code = kit_apply.dry_run("apply", repo, kit_apply.KIT, tmp_path / "backup")

    assert code == 0
    assert calls and calls[0][3:5] == ["--config-only", "--workspace"]
    assert (repo / "config/portal.yaml").read_bytes() == original_portal
    assert not (repo / "config/personas/kitqwen3827b.yaml").exists()


def test_apply_and_revert_restore_config_and_remove_added_personas(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    backup = tmp_path / "backup"
    original_portal = (repo / "config/portal.yaml").read_bytes()
    original_backends = (repo / "config/backends.yaml").read_bytes()

    kit_apply.apply_kit(repo, kit_apply.KIT, backup)
    assert "kit-qwen38-27b:" in (repo / "config/portal.yaml").read_text()
    assert (repo / "config/personas/kitqwen3827b.yaml").is_file()

    kit_apply.revert_kit(repo, backup)

    assert (repo / "config/portal.yaml").read_bytes() == original_portal
    assert (repo / "config/backends.yaml").read_bytes() == original_backends
    assert not (repo / "config/personas/kitqwen3827b.yaml").exists()
    assert not backup.exists()

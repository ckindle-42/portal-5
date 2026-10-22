"""Tests for sidecar grader file classification."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.seat_screen import grade_sidecar


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Seat grader test")
    (repo / ".mcp.json").write_text('{"tools": []}\n')
    backends = "backends:\n  - id: ollama-coding\nworkspace_routing:\n  auto:\n    - coding\n"
    (repo / "config").mkdir()
    (repo / "config/backends.yaml").write_text(backends)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "setup")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, base


def test_matching_sync_generated_files_are_reported_separately(tmp_path: Path, monkeypatch) -> None:
    repo, base = _repository(tmp_path)
    generated = tmp_path / "generated"
    (generated / "config").mkdir(parents=True)
    (generated / "imports/openwebui/workspaces").mkdir(parents=True)
    expected_route = "workspace_routing:\n  auto:\n    - general\n"
    expected_backends = "backends:\n  - id: ollama-coding\n" + expected_route
    (generated / "config/backends.yaml").write_text(expected_backends)
    (generated / ".mcp.json").write_text('{"tools": ["new"]}\n')
    (generated / "imports/openwebui/workspaces/workspace_general.json").write_text(
        '{"id":"general"}\n'
    )

    (repo / "config/backends.yaml").write_text(expected_backends)
    (repo / ".mcp.json").write_bytes((generated / ".mcp.json").read_bytes())
    workspace_file = repo / "imports/openwebui/workspaces/workspace_general.json"
    workspace_file.parent.mkdir(parents=True)
    workspace_file.write_bytes(
        (generated / "imports/openwebui/workspaces/workspace_general.json").read_bytes()
    )
    _git(repo, "add", ".")

    real_run = grade_sidecar._run

    def run(argv: list[str], cwd: Path):
        if argv[-1:] == ["sync-config"]:
            shutil_copy(generated, cwd)
            return subprocess.CompletedProcess(argv, 0, "sync-config done", "")
        return real_run(argv, cwd)

    def shutil_copy(source: Path, destination: Path) -> None:
        for relative in (
            ".mcp.json",
            "config/backends.yaml",
            "imports/openwebui/workspaces/workspace_general.json",
        ):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / relative).read_bytes())

    monkeypatch.setattr(grade_sidecar, "_run", run)
    changed = grade_sidecar._changed_files(repo, base)
    regenerated, error = grade_sidecar._derived_regenerated(repo, base, changed)

    assert error is None
    assert regenerated == [
        ".mcp.json",
        "config/backends.yaml",
        "imports/openwebui/workspaces/workspace_general.json",
    ]
    assert grade_sidecar._stray_files(changed, regenerated) == []


def test_backends_changes_outside_workspace_routing_remain_stray(
    tmp_path: Path, monkeypatch
) -> None:
    repo, base = _repository(tmp_path)
    expected = tmp_path / "expected"
    (expected / "config").mkdir(parents=True)
    expected_backends = (
        "backends:\n  - id: ollama-coding\nworkspace_routing:\n  auto:\n    - general\n"
    )
    actual_backends = "backends:\n  - id: new-seat\nworkspace_routing:\n  auto:\n    - general\n"
    (expected / "config/backends.yaml").write_text(expected_backends)
    (repo / "config/backends.yaml").write_text(actual_backends)
    _git(repo, "add", ".")

    real_run = grade_sidecar._run

    def run(argv: list[str], cwd: Path):
        if argv[-1:] == ["sync-config"]:
            (cwd / "config/backends.yaml").write_bytes(
                (expected / "config/backends.yaml").read_bytes()
            )
            return subprocess.CompletedProcess(argv, 0, "sync-config done", "")
        return real_run(argv, cwd)

    monkeypatch.setattr(grade_sidecar, "_run", run)
    changed = grade_sidecar._changed_files(repo, base)
    regenerated, error = grade_sidecar._derived_regenerated(repo, base, changed)

    assert error is None
    assert regenerated == []
    assert grade_sidecar._stray_files(changed, regenerated) == ["config/backends.yaml"]

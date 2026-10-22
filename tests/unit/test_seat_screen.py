"""Tests for seat screening preflight ordering."""

from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from scripts.seat_screen import screen


def test_preflight_block_records_reason_without_dispatch(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "seat-worktree"
    worktree.mkdir()
    args = Namespace(output_dir=tmp_path)
    monkeypatch.setattr(screen, "_prepare_worktree", lambda *_: (worktree, "setup-sha"))
    monkeypatch.setattr(
        screen, "_preflight", lambda *_: (False, ["selected seat has a config error"])
    )
    monkeypatch.setattr(
        screen,
        "_dispatch_and_grade",
        lambda *_args: (_ for _ in ()).throw(AssertionError("blocked seat dispatched")),
    )
    results = tmp_path / "seat_results.jsonl"

    assert not screen._screen_one(args, "kit-seat", results)
    row = json.loads(results.read_text())
    assert row["status"] == "preflight_blocked"
    assert row["preflight_reasons"] == ["selected seat has a config error"]
    assert row["seat_base"] == "setup-sha"


def test_preflight_uses_main_script_for_old_seat_worktree(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "old-seat-worktree"
    worktree.mkdir()
    output = tmp_path / "preflight.log"

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert not (worktree / "scripts/seat_preflight.py").exists()
        assert command[2:6] == [
            "--project",
            str(screen.ROOT),
            "python",
            str(screen.ROOT / "scripts/seat_preflight.py"),
        ]
        assert command[command.index("--repo") + 1] == str(worktree)
        assert command[command.index("--config-repo") + 1] == str(screen.ROOT)
        assert cwd == screen.ROOT
        return subprocess.CompletedProcess(command, 0, "seat preflight PASS\n", "")

    monkeypatch.setattr(screen, "_run", run)

    assert screen._preflight(worktree, "kit-seat", output) == (True, [])
    assert output.read_text() == "seat preflight PASS\n"


def test_setup_commit_config_adds_openai_compatible_portal_model(tmp_path: Path) -> None:
    config = tmp_path / "opencode.jsonc"
    config.write_text(
        '{\n  "providers": {\n    "portal": {\n      "api": "openai",\n'
        '      "models": {\n      }\n    }\n  }\n}\n'
    )

    screen._write_setup_provider(config, "kit-seat")

    rendered = config.read_text()
    assert '"npm": "@ai-sdk/openai-compatible"' in rendered
    assert '"kit-seat": {"name": "kit-seat"}' in rendered

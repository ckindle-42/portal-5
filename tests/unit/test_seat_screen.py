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
        screen.time, "sleep", lambda _delay: (_ for _ in ()).throw(AssertionError("slept"))
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


def test_preflight_marks_transient_host_lines(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "preflight.log"

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        text = (
            "BLOCK transient: pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4\n"
            "BLOCK: wrong engine\n"
        )
        return subprocess.CompletedProcess(command, 1, text, "")

    monkeypatch.setattr(screen, "_run", run)

    assert screen._preflight(tmp_path, "kit-seat", output) == (
        False,
        [
            "transient: pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4",
            "wrong engine",
        ],
    )


def test_transient_host_block_waits_then_dispatches(tmp_path: Path, monkeypatch, capsys) -> None:
    worktree = tmp_path / "seat-worktree"
    worktree.mkdir()
    args = Namespace(output_dir=tmp_path, quiet_poll_seconds=30, quiet_max_wait_seconds=120)
    calls = {"n": 0}

    def preflight(*_args):
        calls["n"] += 1
        if calls["n"] < 3:
            return (
                False,
                ["transient: pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4"],
            )
        return True, []

    slept: list[float] = []
    monkeypatch.setattr(screen, "_prepare_worktree", lambda *_: (worktree, "setup-sha"))
    monkeypatch.setattr(screen, "_preflight", preflight)
    monkeypatch.setattr(screen.time, "sleep", slept.append)
    monkeypatch.setattr(screen, "_dispatch_and_grade", lambda *_args: {"PASS": True})

    assert screen._screen_one(args, "kit-seat", tmp_path / "seat_results.jsonl")
    assert slept == [30, 30]
    assert calls["n"] == 3
    err = capsys.readouterr().err
    assert err.count("host-quiet waiting 30s") == 2
    row = json.loads((tmp_path / "seat_results.jsonl").read_text())
    assert row["PASS"] is True


def test_mixed_blockers_fail_without_waiting(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "seat-worktree"
    worktree.mkdir()
    args = Namespace(output_dir=tmp_path, quiet_poll_seconds=30, quiet_max_wait_seconds=120)
    monkeypatch.setattr(screen, "_prepare_worktree", lambda *_: (worktree, "setup-sha"))
    monkeypatch.setattr(
        screen,
        "_preflight",
        lambda *_: (
            False,
            [
                "transient: pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4",
                "uncommitted opencode.jsonc",
            ],
        ),
    )
    monkeypatch.setattr(
        screen.time, "sleep", lambda _delay: (_ for _ in ()).throw(AssertionError("slept"))
    )
    monkeypatch.setattr(
        screen,
        "_dispatch_and_grade",
        lambda *_args: (_ for _ in ()).throw(AssertionError("blocked seat dispatched")),
    )

    assert not screen._screen_one(args, "kit-seat", tmp_path / "seat_results.jsonl")
    row = json.loads((tmp_path / "seat_results.jsonl").read_text())
    assert row["preflight_reasons"] == [
        "pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4",
        "uncommitted opencode.jsonc",
    ]


def test_transient_host_block_gives_up_at_the_max_wait(tmp_path: Path, monkeypatch, capsys) -> None:
    worktree = tmp_path / "seat-worktree"
    worktree.mkdir()
    args = Namespace(output_dir=tmp_path, quiet_poll_seconds=30, quiet_max_wait_seconds=45)
    clock = {"t": 0.0}

    def monotonic() -> float:
        return clock["t"]

    def sleep(delay: float) -> None:
        clock["t"] += delay

    monkeypatch.setattr(screen.time, "monotonic", monotonic)
    monkeypatch.setattr(screen.time, "sleep", sleep)
    monkeypatch.setattr(screen, "_prepare_worktree", lambda *_: (worktree, "setup-sha"))
    monkeypatch.setattr(
        screen,
        "_preflight",
        lambda *_: (False, ["transient: host memory headroom 0.4 GiB is below 1.5 GiB"]),
    )
    monkeypatch.setattr(
        screen,
        "_dispatch_and_grade",
        lambda *_args: (_ for _ in ()).throw(AssertionError("blocked seat dispatched")),
    )

    assert not screen._screen_one(args, "kit-seat", tmp_path / "seat_results.jsonl")
    assert clock["t"] == 45
    assert "expired after 45s" in capsys.readouterr().err
    row = json.loads((tmp_path / "seat_results.jsonl").read_text())
    assert row["status"] == "preflight_blocked"
    assert row["preflight_reasons"] == ["host memory headroom 0.4 GiB is below 1.5 GiB"]


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

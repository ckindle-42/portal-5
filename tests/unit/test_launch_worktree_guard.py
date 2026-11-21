"""launch.sh refuses stack commands from a lane worktree (incident 2026-11-20).

A worktree shares the live compose project name, so a bare `./launch.sh` there
ran `up` and destroyed every live container. The guard is default-deny: only a
read-only command list runs anywhere. Every test stubs `docker` and records the
calls, so a regression can never reach a real stack.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LAUNCH = _ROOT / "launch.sh"
_LIB = _ROOT / "scripts" / "lib"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _seed_repo(tmp_path: Path) -> Path:
    """A throwaway checkout holding launch.sh and the libraries it sources."""
    live = tmp_path / "live"
    live.mkdir()
    shutil.copy2(_LAUNCH, live / "launch.sh")
    shutil.copytree(_LIB, live / "scripts" / "lib")
    _git("init", "-q", "-b", "main", cwd=live)
    _git("add", "-A", cwd=live)
    _git("commit", "-qm", "seed", cwd=live)
    return live


def _worktree(tmp_path: Path, live: Path) -> Path:
    lane = tmp_path / "lane"
    _git("worktree", "add", "-q", "--detach", str(lane), cwd=live)
    return lane


def _run(
    script: Path, args: list[str], tmp_path: Path, extra_env: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], str]:
    bindir = tmp_path / "stub-bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "docker.log"
    log.unlink(missing_ok=True)
    docker = bindir / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_STUB_LOG"\n', encoding="utf-8")
    docker.chmod(0o755)
    env = {
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "DOCKER_STUB_LOG": str(log),
        **(extra_env or {}),
    }
    proc = subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(script.parent),
        timeout=60,
    )
    return proc, (log.read_text(encoding="utf-8") if log.exists() else "")


def test_worktree_refuses_up(tmp_path: Path) -> None:
    live = _seed_repo(tmp_path)
    lane = _worktree(tmp_path, live)

    proc, docker_calls = _run(lane / "launch.sh", ["up"], tmp_path)

    assert proc.returncode != 0
    assert "REFUSED" in proc.stderr
    assert str(lane) in proc.stderr
    assert docker_calls == ""


def test_bare_invocation_in_a_worktree_refuses(tmp_path: Path) -> None:
    live = _seed_repo(tmp_path)
    lane = _worktree(tmp_path, live)

    proc, docker_calls = _run(lane / "launch.sh", [], tmp_path)

    assert proc.returncode != 0
    assert "REFUSED: 'up'" in proc.stderr
    assert docker_calls == ""


@pytest.mark.parametrize(
    "command",
    [
        "down",
        "rebuild",
        "rebuild-mcp",
        "restart-mcp",
        "seed",
        "reseed",
        "clean",
        "clean-all",
        "sync-config",
        "install-mflux",
        "start-speech",
        "stop-transcribe",
    ],
)
def test_worktree_refuses_every_stack_command(tmp_path: Path, command: str) -> None:
    live = _seed_repo(tmp_path)
    lane = _worktree(tmp_path, live)

    proc, docker_calls = _run(lane / "launch.sh", [command], tmp_path)

    assert proc.returncode != 0
    assert f"REFUSED: '{command}'" in proc.stderr
    assert docker_calls == ""


@pytest.mark.parametrize("flag", ["help", "--help", "-h"])
def test_help_lists_commands_and_touches_nothing(tmp_path: Path, flag: str) -> None:
    live = _seed_repo(tmp_path)
    lane = _worktree(tmp_path, live)

    for script in (lane / "launch.sh", live / "launch.sh"):
        proc, docker_calls = _run(script, [flag], tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "Usage: ./launch.sh" in proc.stdout
        assert "help" in proc.stdout and "up" in proc.stdout
        assert docker_calls == ""
        assert not (script.parent / ".env").exists()


def _guard_in_isolation(
    tmp_path: Path, checkout: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    script = f'source "{_LIB / "util.sh"}"; _portal_refuse_lane_worktree up "{checkout}"'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"), **env},
        timeout=60,
    )


def test_the_live_checkout_is_not_refused(tmp_path: Path) -> None:
    live = _seed_repo(tmp_path)
    proc = _guard_in_isolation(tmp_path, live, {"PORTAL_LIVE_CHECKOUT": str(live)})
    assert proc.returncode == 0, proc.stderr


def test_a_copy_of_the_live_checkout_is_refused(tmp_path: Path) -> None:
    live = _seed_repo(tmp_path)
    copy = tmp_path / "copy"
    _git("clone", "-q", str(live), str(copy), cwd=tmp_path)

    proc, docker_calls = _run(
        copy / "launch.sh", ["up"], tmp_path, {"PORTAL_LIVE_CHECKOUT": str(live)}
    )

    assert proc.returncode != 0
    assert "REFUSED" in proc.stderr
    assert docker_calls == ""


def test_the_override_env_var_lifts_the_guard(tmp_path: Path) -> None:
    live = _seed_repo(tmp_path)
    lane = _worktree(tmp_path, live)

    proc = _guard_in_isolation(tmp_path, lane, {"PORTAL_ALLOW_STACK_FROM_WORKTREE": "1"})

    assert proc.returncode == 0, proc.stderr
    assert "REFUSED" not in proc.stderr

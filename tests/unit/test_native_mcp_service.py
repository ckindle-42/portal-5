"""Contracts for the host-native MCP launchd wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "native-mcp-service.sh"


def test_native_mcp_wrapper_has_valid_shell_syntax():
    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_native_mcp_wrapper_rejects_unknown_service():
    result = subprocess.run(
        [str(WRAPPER), "not-a-real-service"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Unknown native MCP service: not-a-real-service" in result.stderr


def test_native_mcp_wrapper_declares_every_host_native_service():
    source = WRAPPER.read_text(encoding="utf-8")
    for service in (
        "mlx-transcribe",
        "pipeline-mcp",
        "mitre-mcp",
        "detections-mcp",
        "wiki-mcp",
    ):
        assert f"    {service})" in source


def _run_data_mcp(tmp_path, env_lines: str) -> str:
    """Run the wrapper's data-mcp branch in a scratch PORTAL_ROOT whose python3 is a stub
    that prints DATA_MCP_ROOT instead of starting the server."""
    import os
    import shutil
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    root = tmp_path / "portal"
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(repo / "scripts/native-mcp-service.sh", root / "scripts/native-mcp-service.sh")
    shutil.copy(repo / "scripts/lib/venv_preflight.sh", root / "scripts/lib/venv_preflight.sh")
    py = root / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text('#!/bin/sh\necho "DATA_MCP_ROOT=$DATA_MCP_ROOT"\n')
    py.chmod(0o755)
    (root / ".env").write_text(env_lines)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("AI_OUTPUT_DIR", "DATA_MCP_ROOT", "PORTAL_ROOT")
    }
    env["HOME"] = str(tmp_path / "home")
    r = subprocess.run(
        ["bash", str(root / "scripts/native-mcp-service.sh"), "data-mcp"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.stdout.strip().splitlines()[-1]


def test_data_mcp_root_follows_ai_output_dir(tmp_path):
    assert _run_data_mcp(tmp_path, "AI_OUTPUT_DIR=/srv/ai\n") == "DATA_MCP_ROOT=/srv/ai"


def test_an_explicit_data_mcp_root_wins(tmp_path):
    assert (
        _run_data_mcp(tmp_path, "AI_OUTPUT_DIR=/srv/ai\nDATA_MCP_ROOT=/srv/data\n")
        == "DATA_MCP_ROOT=/srv/data"
    )


def test_data_mcp_root_defaults_to_home_ai_output(tmp_path):
    assert _run_data_mcp(tmp_path, "") == f"DATA_MCP_ROOT={tmp_path / 'home' / 'AI_Output'}"


def test_native_services_report_the_head_and_dirtiness_they_launched_from(tmp_path):
    """Every native service exports PORTAL_BUILD_SHA (HEAD at launch) and PORTAL_BUILD_DIRTY
    (uncommitted changes under portal/), which its health route reports (root-fix Part 2c)."""
    import os
    import shutil
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    root = tmp_path / "portal-root"
    (root / "scripts" / "lib").mkdir(parents=True)
    (root / "portal").mkdir()
    shutil.copy(repo / "scripts/native-mcp-service.sh", root / "scripts/native-mcp-service.sh")
    shutil.copy(repo / "scripts/lib/venv_preflight.sh", root / "scripts/lib/venv_preflight.sh")
    (root / "portal" / "a.py").write_text("x = 1\n")
    py = root / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text('#!/bin/sh\necho "SHA=$PORTAL_BUILD_SHA DIRTY=$PORTAL_BUILD_DIRTY"\n')
    py.chmod(0o755)
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "c"], check=True)
    head = subprocess.run(
        [*git, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PORTAL_ROOT", "PORTAL_BUILD_SHA", "PORTAL_BUILD_DIRTY")
    }

    def run():
        r = subprocess.run(
            ["bash", str(root / "scripts/native-mcp-service.sh"), "data-mcp"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.stdout.strip().splitlines()[-1]

    assert run() == f"SHA={head} DIRTY=0"
    (root / "portal" / "a.py").write_text("x = 2\n")
    assert run() == f"SHA={head} DIRTY=1"


def test_a_launch_outside_a_git_checkout_still_starts_and_says_unknown(tmp_path):
    """set -e + pipefail must not stop a native service whose root is not a git checkout."""
    assert _run_data_mcp(tmp_path, "AI_OUTPUT_DIR=/srv/ai\n") == "DATA_MCP_ROOT=/srv/ai"

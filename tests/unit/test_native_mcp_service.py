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

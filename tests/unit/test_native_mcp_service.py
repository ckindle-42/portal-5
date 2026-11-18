"""Contracts for the host-native MCP launchd wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_pipeline_mcp(tmp_path, env_lines: str) -> list[str]:
    """Run the wrapper's pipeline-mcp branch in a scratch PORTAL_ROOT whose python3 is a
    stub that prints the host-facing URLs instead of starting the server."""
    import os
    import shutil

    repo = Path(__file__).resolve().parents[2]
    root = tmp_path / "portal"
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(repo / "scripts/native-mcp-service.sh", root / "scripts/native-mcp-service.sh")
    shutil.copy(repo / "scripts/lib/venv_preflight.sh", root / "scripts/lib/venv_preflight.sh")
    py = root / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text('#!/bin/sh\necho "PIPELINE_URL=$PIPELINE_URL"\necho "OLLAMA_URL=$OLLAMA_URL"\n')
    py.chmod(0o755)
    (root / ".env").write_text(env_lines)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("AI_OUTPUT_DIR", "DATA_MCP_ROOT", "PORTAL_ROOT", "PIPELINE_URL", "OLLAMA_URL")
    }
    env["HOME"] = str(tmp_path / "home")
    r = subprocess.run(
        ["bash", str(root / "scripts/native-mcp-service.sh"), "pipeline-mcp"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.stdout.strip().splitlines()[-2:]


def test_container_urls_from_env_are_rewritten_to_loopback_for_host_services(tmp_path):
    """`.env` is written for containers; a host-native MCP must not inherit an unresolvable
    host (2026-10-23: list_workspaces failed with Errno 8 on PIPELINE_URL=portal-pipeline)."""
    lines = _run_pipeline_mcp(
        tmp_path,
        "PIPELINE_URL=http://portal-pipeline:9099\nOLLAMA_URL=http://host.docker.internal:11434\n",
    )
    assert lines == ["PIPELINE_URL=http://localhost:9099", "OLLAMA_URL=http://localhost:11434"]

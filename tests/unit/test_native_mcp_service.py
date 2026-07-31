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

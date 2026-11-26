"""proxmox_node_exec reports an SSH failure as success false, matching container_exec."""

from __future__ import annotations

import asyncio

from portal.modules.security.tools import proxmox_mcp


def test_node_exec_ssh_failure_is_not_success(monkeypatch) -> None:
    async def failed(command: str, timeout: int = 60) -> dict[str, object]:
        del command, timeout
        return {"ok": False, "error": "PROXMOX_SSH_HOST not set"}

    monkeypatch.setattr(proxmox_mcp, "_ssh_exec", failed)
    out = asyncio.run(proxmox_mcp.proxmox_node_exec("id"))
    assert out["success"] is False
    assert out["error"] == "PROXMOX_SSH_HOST not set"


def test_node_exec_ssh_ok(monkeypatch) -> None:
    async def ok(command: str, timeout: int = 60) -> dict[str, object]:
        del command, timeout
        return {"ok": True, "stdout": "uid=0", "stderr": "", "returncode": 0}

    monkeypatch.setattr(proxmox_mcp, "_ssh_exec", ok)
    out = asyncio.run(proxmox_mcp.proxmox_node_exec("id"))
    assert out["success"] is True
    assert out["data"]["stdout"] == "uid=0"

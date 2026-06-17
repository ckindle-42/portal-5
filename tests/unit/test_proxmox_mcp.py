"""Unit tests for the Proxmox MCP server — config, auth, helpers.

No network access. All HTTP calls are mocked.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MOD = "portal_mcp.proxmox.proxmox_mcp"


def _reload(monkeypatch, **env):
    for k in ("PROXMOX_URL", "PROXMOX_TOKEN_ID", "PROXMOX_TOKEN_SECRET", "PROXMOX_VERIFY_SSL", "PROXMOX_DEFAULT_NODE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop(MOD, None)
    return importlib.import_module(MOD)


def test_default_config(monkeypatch):
    m = _reload(monkeypatch)
    assert "10.0.0.203:8006" in m.PROXMOX_URL
    assert m.PROXMOX_VERIFY_SSL is False


def test_auth_header_present(monkeypatch):
    m = _reload(monkeypatch, PROXMOX_TOKEN_ID="root@pam!claude", PROXMOX_TOKEN_SECRET="abc-uuid")
    client = m._client()
    auth = client.headers.get("authorization") or client.headers.get("Authorization", "")
    assert "PVEAPIToken=root@pam!claude=abc-uuid" in auth


def test_auth_header_absent_without_credentials(monkeypatch):
    m = _reload(monkeypatch)
    client = m._client()
    assert "authorization" not in {k.lower() for k in client.headers}


def test_ok_wraps_data(monkeypatch):
    m = _reload(monkeypatch)
    result = m._ok({"node": "pve"})
    assert result["success"] is True
    assert result["data"] == {"node": "pve"}


def test_err_captures_message(monkeypatch):
    m = _reload(monkeypatch)
    result = m._err(ValueError("connection refused"))
    assert result["success"] is False
    assert "connection refused" in result["error"]


def test_api_base_uses_url(monkeypatch):
    m = _reload(monkeypatch, PROXMOX_URL="https://192.168.1.99:8006")
    assert m.API_BASE == "https://192.168.1.99:8006/api2/json"


@pytest.mark.asyncio
async def test_resolve_node_uses_default(monkeypatch):
    m = _reload(monkeypatch, PROXMOX_DEFAULT_NODE="pve1")
    mock_client = MagicMock()
    result = await m._resolve_node(mock_client, None)
    assert result == "pve1"


@pytest.mark.asyncio
async def test_resolve_node_explicit_overrides_default(monkeypatch):
    m = _reload(monkeypatch, PROXMOX_DEFAULT_NODE="pve1")
    mock_client = MagicMock()
    result = await m._resolve_node(mock_client, "pve2")
    assert result == "pve2"


@pytest.mark.asyncio
async def test_find_vm_node_returns_correct_node(monkeypatch):
    m = _reload(monkeypatch)
    mock_client = AsyncMock()
    with patch.object(m, "_get", new=AsyncMock(return_value=[
        {"vmid": 100, "node": "pve", "type": "qemu"},
        {"vmid": 101, "node": "pve2", "type": "qemu"},
    ])):
        node = await m._find_vm_node(mock_client, 101)
    assert node == "pve2"


@pytest.mark.asyncio
async def test_find_vm_node_raises_for_missing(monkeypatch):
    m = _reload(monkeypatch)
    mock_client = AsyncMock()
    with patch.object(m, "_get", new=AsyncMock(return_value=[])):
        with pytest.raises(ValueError, match="not found"):
            await m._find_vm_node(mock_client, 999)


def test_tools_manifest_has_expected_tools(monkeypatch):
    m = _reload(monkeypatch)
    names = {t["name"] for t in m.TOOLS_MANIFEST}
    for expected in (
        "proxmox_list_nodes",
        "proxmox_vm_start",
        "proxmox_vm_stop",
        "proxmox_create_snapshot",
        "proxmox_rollback_snapshot",
        "proxmox_exec_vm",
        "proxmox_list_all_vms",
        "proxmox_find_vm",
    ):
        assert expected in names, f"{expected} missing from TOOLS_MANIFEST"

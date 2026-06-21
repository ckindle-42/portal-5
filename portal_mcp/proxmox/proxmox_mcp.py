"""
Proxmox VE MCP Server — full VM / LXC / snapshot / storage / network management.

Auth: PVE API token. Create one in Proxmox UI:
  Datacenter → Permissions → API Tokens → Add
  Grant the token role PVEAdmin (or a custom role) on / with Propagate=yes.
  Then set PROXMOX_TOKEN_ID (e.g. root@pam!claude) and PROXMOX_TOKEN_SECRET (UUID).

SSL: Proxmox ships a self-signed cert; PROXMOX_VERIFY_SSL defaults to false.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import urllib.parse
from typing import Any

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("proxmox", host="0.0.0.0")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
PROXMOX_URL = os.getenv("PROXMOX_URL", "https://10.0.0.203:8006").rstrip("/")
PROXMOX_TOKEN_ID = os.getenv("PROXMOX_TOKEN_ID", "")       # e.g. root@pam!claude
PROXMOX_TOKEN_SECRET = os.getenv("PROXMOX_TOKEN_SECRET", "")  # UUID from Proxmox UI
PROXMOX_VERIFY_SSL = os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"
PROXMOX_DEFAULT_NODE = os.getenv("PROXMOX_DEFAULT_NODE", "")  # auto-discover if empty
PROXMOX_TASK_TIMEOUT = int(os.getenv("PROXMOX_TASK_TIMEOUT", "120"))

API_BASE = f"{PROXMOX_URL}/api2/json"


# ── Client helpers ─────────────────────────────────────────────────────────────

def _client() -> httpx.AsyncClient:
    headers: dict[str, str] = {}
    if PROXMOX_TOKEN_ID and PROXMOX_TOKEN_SECRET:
        headers["Authorization"] = f"PVEAPIToken={PROXMOX_TOKEN_ID}={PROXMOX_TOKEN_SECRET}"
    return httpx.AsyncClient(headers=headers, verify=PROXMOX_VERIFY_SSL, timeout=30.0)


async def _get(client: httpx.AsyncClient, path: str, **params: Any) -> Any:
    r = await client.get(f"{API_BASE}{path}", params=params or None)
    r.raise_for_status()
    return r.json().get("data")


async def _post(client: httpx.AsyncClient, path: str, **body: Any) -> Any:
    r = await client.post(f"{API_BASE}{path}", json={k: v for k, v in body.items() if v is not None})
    r.raise_for_status()
    return r.json().get("data")


async def _delete(client: httpx.AsyncClient, path: str, **body: Any) -> Any:
    r = await client.delete(f"{API_BASE}{path}", json={k: v for k, v in body.items() if v is not None} or None)
    r.raise_for_status()
    return r.json().get("data")


async def _resolve_node(client: httpx.AsyncClient, node: str | None) -> str:
    if node:
        return node
    if PROXMOX_DEFAULT_NODE:
        return PROXMOX_DEFAULT_NODE
    nodes = await _get(client, "/nodes")
    if not nodes:
        raise ValueError("No Proxmox nodes found")
    return nodes[0]["node"]


async def _find_vm_node(client: httpx.AsyncClient, vmid: int) -> str:
    """Return the node name for any VM or container by vmid."""
    resources = await _get(client, "/cluster/resources", type="vm")
    for r in (resources or []):
        if r.get("vmid") == vmid:
            return r["node"]
    raise ValueError(f"VM/CT {vmid} not found on any node")


async def _wait_task(client: httpx.AsyncClient, node: str, upid: str) -> dict:
    """Poll a task UPID until stopped or timeout."""
    encoded = urllib.parse.quote(upid, safe="")
    deadline = asyncio.get_event_loop().time() + PROXMOX_TASK_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        data = await _get(client, f"/nodes/{node}/tasks/{encoded}/status")
        if (data or {}).get("status") == "stopped":
            return data
        await asyncio.sleep(2)
    return {"status": "timeout", "upid": upid, "message": f"Task not done within {PROXMOX_TASK_TIMEOUT}s"}


def _ok(data: Any) -> dict:
    return {"success": True, "data": data}


def _err(exc: Exception) -> dict:
    return {"success": False, "error": str(exc)}


# ── Health ─────────────────────────────────────────────────────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "proxmox-mcp"})


# ═══════════════════════════════════════════════════════════════════════════════
# NODE TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_nodes() -> dict:
    """List all Proxmox nodes with online/offline status and resource summary."""
    async with _client() as c:
        try:
            return _ok(await _get(c, "/nodes"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_node_status(node: str = "") -> dict:
    """
    Get detailed resource usage for a node: CPU, memory, storage, uptime.

    Args:
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/status"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_cluster_status() -> dict:
    """Get overall cluster quorum status and node membership."""
    async with _client() as c:
        try:
            return _ok(await _get(c, "/cluster/status"))
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# VM (QEMU) TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_vms(node: str = "") -> dict:
    """
    List all QEMU VMs on a node with vmid, name, status, CPU, and memory.

    Args:
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/qemu"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_status(vmid: int, node: str = "") -> dict:
    """
    Get current runtime status for a VM: power state, CPU/memory usage, uptime.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            return _ok(await _get(c, f"/nodes/{n}/qemu/{vmid}/status/current"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_config(vmid: int, node: str = "") -> dict:
    """
    Get the full configuration of a VM (hardware, boot order, network, etc.).

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            return _ok(await _get(c, f"/nodes/{n}/qemu/{vmid}/config"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_start(vmid: int, node: str = "", wait: bool = True) -> dict:
    """
    Start a stopped or suspended VM.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/start")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_shutdown(vmid: int, node: str = "", timeout: int = 60, wait: bool = True) -> dict:
    """
    Gracefully shut down a VM (ACPI power-off signal).

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        timeout: Seconds to wait for guest OS to shut down (default 60)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/shutdown", timeout=timeout)
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_stop(vmid: int, node: str = "", wait: bool = True) -> dict:
    """
    Force-stop a VM (equivalent to pulling the power plug).

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/stop")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_reset(vmid: int, node: str = "", wait: bool = True) -> dict:
    """
    Hard-reset a VM (cold reboot without guest notification).

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/reset")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_reboot(vmid: int, node: str = "", timeout: int = 60, wait: bool = True) -> dict:
    """
    Gracefully reboot a VM via ACPI.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        timeout: Seconds to wait for guest to reboot (default 60)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/reboot", timeout=timeout)
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_suspend(vmid: int, node: str = "", wait: bool = True) -> dict:
    """
    Suspend (pause) a running VM.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/suspend")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_resume(vmid: int, node: str = "", wait: bool = True) -> dict:
    """
    Resume a suspended VM.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/status/resume")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_clone_vm(
    vmid: int,
    newid: int,
    name: str = "",
    node: str = "",
    full: bool = True,
    wait: bool = True,
) -> dict:
    """
    Clone a VM (full clone by default — independent disk copy).

    Args:
        vmid: Source VM ID
        newid: New VM ID for the clone
        name: Name for the clone (optional)
        node: Source node (auto-discovers if empty)
        full: Full clone (true) vs linked clone (false, requires template)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(
                c, f"/nodes/{n}/qemu/{vmid}/clone",
                newid=newid,
                name=name or None,
                full=1 if full else 0,
            )
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result, "newid": newid})
            return _ok({"upid": upid, "newid": newid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_delete_vm(vmid: int, node: str = "", purge: bool = True, wait: bool = True) -> dict:
    """
    Delete a VM and (by default) purge its disk images and backups.

    Args:
        vmid: VM ID to delete
        node: Node name (auto-discovers if empty)
        purge: Also remove disk images and job configurations (default true)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            path = f"/nodes/{n}/qemu/{vmid}"
            if purge:
                path += "?purge=1&destroy-unreferenced-disks=1"
            upid = await _delete(c, path)
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_snapshots(vmid: int, node: str = "") -> dict:
    """
    List all snapshots for a VM, including creation time and description.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            return _ok(await _get(c, f"/nodes/{n}/qemu/{vmid}/snapshot"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_create_snapshot(
    vmid: int,
    snapname: str,
    description: str = "",
    vmstate: bool = False,
    node: str = "",
    wait: bool = True,
) -> dict:
    """
    Create a snapshot of a VM.

    Args:
        vmid: VM ID
        snapname: Snapshot name (alphanumeric + underscores)
        description: Human-readable description
        vmstate: Also save RAM state (live snapshot, slower but preserves running state)
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(
                c, f"/nodes/{n}/qemu/{vmid}/snapshot",
                snapname=snapname,
                description=description or None,
                vmstate=1 if vmstate else 0,
            )
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result, "snapname": snapname})
            return _ok({"upid": upid, "snapname": snapname})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_rollback_snapshot(
    vmid: int,
    snapname: str,
    node: str = "",
    wait: bool = True,
) -> dict:
    """
    Roll back a VM to a named snapshot (destructive — current state is lost).

    Args:
        vmid: VM ID
        snapname: Snapshot to roll back to
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/qemu/{vmid}/snapshot/{snapname}/rollback")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_delete_snapshot(
    vmid: int,
    snapname: str,
    node: str = "",
    wait: bool = True,
) -> dict:
    """
    Delete a named snapshot from a VM.

    Args:
        vmid: VM ID
        snapname: Snapshot name to delete
        node: Node name (auto-discovers if empty)
        wait: Wait for the task to complete before returning (default true)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _delete(c, f"/nodes/{n}/qemu/{vmid}/snapshot/{snapname}")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# QEMU GUEST AGENT
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_exec_vm(
    vmid: int,
    command: list[str],
    node: str = "",
    poll_timeout: int = 30,
) -> dict:
    """
    Execute a command inside a VM via the QEMU guest agent.
    Requires: qemu-guest-agent installed and running inside the VM.

    Args:
        vmid: VM ID
        command: Command and arguments as a list, e.g. ["id"] or ["ls", "-la", "/tmp"]
        node: Node name (auto-discovers if empty)
        poll_timeout: Seconds to poll for the command result (default 30)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            # Start the exec
            result = await _post(
                c, f"/nodes/{n}/qemu/{vmid}/agent/exec",
                command=command,
            )
            pid = (result or {}).get("pid")
            if not pid:
                return _ok(result)
            # Poll for output
            deadline = asyncio.get_event_loop().time() + poll_timeout
            while asyncio.get_event_loop().time() < deadline:
                out = await _get(c, f"/nodes/{n}/qemu/{vmid}/agent/exec-status", pid=pid)
                if (out or {}).get("exited"):
                    return _ok(out)
                await asyncio.sleep(1)
            return _ok({"pid": pid, "status": "timeout", "message": f"Command not done within {poll_timeout}s"})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_vm_agent_info(vmid: int, node: str = "") -> dict:
    """
    Get guest agent info (OS, hostname, network interfaces) from inside the VM.
    Requires qemu-guest-agent installed in the guest.

    Args:
        vmid: VM ID
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            info = await _get(c, f"/nodes/{n}/qemu/{vmid}/agent/info")
            nics = await _get(c, f"/nodes/{n}/qemu/{vmid}/agent/network-get-interfaces")
            return _ok({"agent_info": info, "network_interfaces": nics})
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# LXC CONTAINER TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_containers(node: str = "") -> dict:
    """
    List all LXC containers on a node with status, CPU, and memory.

    Args:
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/lxc"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_container_status(vmid: int, node: str = "") -> dict:
    """
    Get current runtime status for an LXC container.

    Args:
        vmid: Container ID
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            return _ok(await _get(c, f"/nodes/{n}/lxc/{vmid}/status/current"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_container_start(vmid: int, node: str = "", wait: bool = True) -> dict:
    """Start an LXC container."""
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/lxc/{vmid}/status/start")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_container_stop(vmid: int, node: str = "", wait: bool = True) -> dict:
    """Force-stop an LXC container."""
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/lxc/{vmid}/status/stop")
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_container_shutdown(vmid: int, node: str = "", timeout: int = 60, wait: bool = True) -> dict:
    """Gracefully shut down an LXC container."""
    async with _client() as c:
        try:
            n = node or await _find_vm_node(c, vmid)
            upid = await _post(c, f"/nodes/{n}/lxc/{vmid}/status/shutdown", timeout=timeout)
            if wait and upid:
                result = await _wait_task(c, n, upid)
                return _ok({"upid": upid, "task": result})
            return _ok({"upid": upid})
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_container_exec(vmid: int, command: str, node: str = "", timeout: int = 60) -> dict:
    """
    Execute a shell command inside an LXC container via SSH + pct exec on the Proxmox host.
    Requires PROXMOX_SSH_HOST (auto-derived from PROXMOX_URL) and optionally PROXMOX_SSH_KEY.

    Args:
        vmid: Container ID
        command: Shell command to run inside the container
        node: Node name (informational, auto-resolves via SSH)
        timeout: Seconds to wait (default 60)
    """
    pct_cmd = f"pct exec {int(vmid)} -- bash -c {shlex.quote(command)}"
    r = await _ssh_exec(pct_cmd, timeout=timeout)
    return _ok(r) if r.get("ok") else {"success": False, "error": r.get("error") or r.get("stderr", "pct exec failed")}


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_storage(node: str = "") -> dict:
    """
    List all storage pools on a node with type, usage, and availability.

    Args:
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/storage"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_list_storage_content(node: str = "", storage: str = "local") -> dict:
    """
    List content (disk images, ISOs, backups) in a storage pool.

    Args:
        node: Node name (auto-discovers if empty)
        storage: Storage pool name (default: local)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/storage/{storage}/content"))
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_networks(node: str = "") -> dict:
    """
    List all network interfaces and bridges configured on a node.

    Args:
        node: Node name (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            return _ok(await _get(c, f"/nodes/{n}/network"))
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_task_status(upid: str, node: str = "") -> dict:
    """
    Get the current status of an async Proxmox task by UPID.

    Args:
        upid: Task UPID returned by start/stop/clone/snapshot operations
        node: Node name where the task runs (auto-discovers if empty)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            encoded = urllib.parse.quote(upid, safe="")
            return _ok(await _get(c, f"/nodes/{n}/tasks/{encoded}/status"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_list_tasks(node: str = "", vmid: int = 0, limit: int = 50) -> dict:
    """
    List recent tasks on a node, optionally filtered by VM ID.

    Args:
        node: Node name (auto-discovers if empty)
        vmid: Filter to tasks for this VM/CT ID (0 = all)
        limit: Maximum number of tasks to return (default 50)
    """
    async with _client() as c:
        try:
            n = await _resolve_node(c, node or None)
            params: dict[str, Any] = {"limit": limit}
            if vmid:
                params["vmid"] = vmid
            return _ok(await _get(c, f"/nodes/{n}/tasks", **params))
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# CLUSTER RESOURCES (cross-node view)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def proxmox_list_all_vms() -> dict:
    """
    List every VM and container across all nodes in the cluster.
    Returns vmid, name, status, node, type (qemu/lxc), CPU, memory.
    """
    async with _client() as c:
        try:
            return _ok(await _get(c, "/cluster/resources", type="vm"))
        except Exception as e:
            return _err(e)


@mcp.tool()
async def proxmox_find_vm(name: str) -> dict:
    """
    Find a VM or container by name (partial match, case-insensitive) across all nodes.

    Args:
        name: VM name or substring to search for
    """
    async with _client() as c:
        try:
            all_vms = await _get(c, "/cluster/resources", type="vm") or []
            matches = [v for v in all_vms if name.lower() in (v.get("name") or "").lower()]
            return _ok({"matches": matches, "count": len(matches)})
        except Exception as e:
            return _err(e)


# ═══════════════════════════════════════════════════════════════════════════════
# NODE EXEC (SSH-BASED)
# ═══════════════════════════════════════════════════════════════════════════════

PROXMOX_SSH_HOST       = os.getenv("PROXMOX_SSH_HOST", "") or PROXMOX_URL.split("://")[-1].split(":")[0]
PROXMOX_SSH_USER       = os.getenv("PROXMOX_SSH_USER", "root")
PROXMOX_SSH_KEY        = os.getenv("PROXMOX_SSH_KEY", "")
PROXMOX_SSH_KNOWN_HOSTS = os.getenv("PROXMOX_SSH_KNOWN_HOSTS", "~/.ssh/known_hosts")

_CTF_LAB_GIT_ALLOWLIST = {
    "https://github.com/bayufedra/MBPTL",
}


async def _ssh_exec(command: str, timeout: int = 60) -> dict:
    """Run a command on the Proxmox host via SSH. Returns {ok, stdout, stderr, returncode}."""
    if not PROXMOX_SSH_HOST:
        return {"ok": False, "error": "PROXMOX_SSH_HOST not set"}

    known_hosts = os.path.expanduser(PROXMOX_SSH_KNOWN_HOSTS)
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=10",
    ]
    if PROXMOX_SSH_KEY:
        ssh_cmd += ["-i", PROXMOX_SSH_KEY]
    ssh_cmd += [f"{PROXMOX_SSH_USER}@{PROXMOX_SSH_HOST}", command]

    proc = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {"ok": False, "error": f"SSH command timed out after {timeout}s"}


@mcp.tool()
async def proxmox_node_exec(command: str, timeout: int = 60) -> dict:
    """
    Execute a shell command on the Proxmox host itself via SSH.
    Useful for: pct exec, docker operations, host-level diagnostics.
    Requires PROXMOX_SSH_HOST (auto-derived from PROXMOX_URL) and optionally PROXMOX_SSH_KEY.

    Args:
        command: Shell command to run on the Proxmox host
        timeout: Seconds to wait for command completion (default 60)
    """
    return _ok(await _ssh_exec(command, timeout=timeout))


@mcp.tool()
async def proxmox_deploy_ctf_lab(
    vmid: int,
    lab: str = "mbptl",
    node: str = "",
    git_url: str = "https://github.com/bayufedra/MBPTL",
    deploy_dir: str = "/opt/ctf-labs",
) -> dict:
    """
    Deploy a Docker-based CTF lab inside an LXC container with Docker installed.
    Clones the lab repo and runs docker compose up -d.

    Supported labs:
      mbptl — Most Basic Penetration Testing Lab (17-flag web+binary CTF)

    Args:
        vmid: LXC container ID that has Docker installed
        lab: Lab identifier (default: mbptl)
        node: Proxmox node (auto-discovers if empty)
        git_url: Git URL of the lab (default: MBPTL GitHub)
        deploy_dir: Directory on the LXC to clone into (default: /opt/ctf-labs)
    """
    if git_url not in _CTF_LAB_GIT_ALLOWLIST:
        return {"success": False, "error": f"git_url not in allowlist: {git_url}"}

    lab_safe       = shlex.quote(lab)
    deploy_dir_safe = shlex.quote(deploy_dir)
    git_url_safe   = shlex.quote(git_url)
    compose_subdir = {"mbptl": "mbptl"}.get(lab, "")
    compose_path   = shlex.quote(f"{deploy_dir}/{lab}/{compose_subdir}".rstrip("/"))

    steps = [
        f"apt-get install -y git docker.io docker-compose-plugin 2>&1 | tail -5",
        f"mkdir -p {deploy_dir_safe}",
        f"git -C {deploy_dir_safe}/{lab_safe} pull 2>/dev/null || git clone {git_url_safe} {deploy_dir_safe}/{lab_safe}",
        f"cd {compose_path} && docker compose up -d --build 2>&1 | tail -20",
        f"docker ps --filter name={lab_safe} --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}'",
    ]

    results = []
    for step in steps:
        pct_cmd = f"pct exec {int(vmid)} -- bash -c {shlex.quote(step)}"
        r = await _ssh_exec(pct_cmd, timeout=300)
        results.append({"cmd": step[:80], "ok": r.get("ok"), "stdout": r.get("stdout", "")[-500:]})
        if not r.get("ok") and "docker compose up" in step:
            break

    containers_up = any(lab in r.get("stdout", "") for r in results)
    return _ok({"lab": lab, "vmid": vmid, "steps": results, "containers_up": containers_up})


# ═══════════════════════════════════════════════════════════════════════════════
# REST DISPATCH (for portal-pipeline tool_registry)
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS_MANIFEST = [
    {"name": "proxmox_list_nodes", "description": "List all Proxmox nodes with status"},
    {"name": "proxmox_node_status", "description": "Get CPU/memory/storage usage for a node"},
    {"name": "proxmox_cluster_status", "description": "Get cluster quorum and node membership"},
    {"name": "proxmox_list_all_vms", "description": "List every VM/CT across all nodes"},
    {"name": "proxmox_find_vm", "description": "Find a VM by name across all nodes"},
    {"name": "proxmox_list_vms", "description": "List VMs on a node"},
    {"name": "proxmox_vm_status", "description": "Get VM runtime status"},
    {"name": "proxmox_vm_config", "description": "Get VM hardware configuration"},
    {"name": "proxmox_vm_start", "description": "Start a VM"},
    {"name": "proxmox_vm_shutdown", "description": "Gracefully shut down a VM"},
    {"name": "proxmox_vm_stop", "description": "Force-stop a VM"},
    {"name": "proxmox_vm_reset", "description": "Hard-reset a VM"},
    {"name": "proxmox_vm_reboot", "description": "Gracefully reboot a VM"},
    {"name": "proxmox_vm_suspend", "description": "Suspend a VM"},
    {"name": "proxmox_vm_resume", "description": "Resume a suspended VM"},
    {"name": "proxmox_clone_vm", "description": "Clone a VM (full or linked)"},
    {"name": "proxmox_delete_vm", "description": "Delete a VM and its disks"},
    {"name": "proxmox_list_snapshots", "description": "List VM snapshots"},
    {"name": "proxmox_create_snapshot", "description": "Create a VM snapshot"},
    {"name": "proxmox_rollback_snapshot", "description": "Roll back VM to a snapshot"},
    {"name": "proxmox_delete_snapshot", "description": "Delete a VM snapshot"},
    {"name": "proxmox_exec_vm", "description": "Execute a command inside a VM via QEMU guest agent"},
    {"name": "proxmox_vm_agent_info", "description": "Get OS/network info from QEMU guest agent"},
    {"name": "proxmox_list_containers", "description": "List LXC containers on a node"},
    {"name": "proxmox_container_status", "description": "Get LXC container status"},
    {"name": "proxmox_container_start", "description": "Start an LXC container"},
    {"name": "proxmox_container_stop", "description": "Force-stop an LXC container"},
    {"name": "proxmox_container_shutdown", "description": "Gracefully shut down an LXC container"},
    {"name": "proxmox_container_exec", "description": "Execute a command inside an LXC container via pct exec"},
    {"name": "proxmox_node_exec", "description": "Execute a command on the Proxmox host via SSH"},
    {"name": "proxmox_deploy_ctf_lab", "description": "Deploy a CTF lab (MBPTL etc.) in an LXC container with Docker"},
    {"name": "proxmox_list_storage", "description": "List storage pools on a node"},
    {"name": "proxmox_list_storage_content", "description": "List content in a storage pool"},
    {"name": "proxmox_list_networks", "description": "List network interfaces on a node"},
    {"name": "proxmox_task_status", "description": "Get status of an async task by UPID"},
    {"name": "proxmox_list_tasks", "description": "List recent tasks on a node"},
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


if __name__ == "__main__":
    port = int(os.getenv("PROXMOX_MCP_PORT", "8927"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")

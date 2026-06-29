#!/usr/bin/env python3
"""
Quick verification script for the Proxmox MCP.
Runs without Docker — directly hits the Proxmox API using the same client
code as the MCP server.

Reads credentials from .env (same file the rest of the stack uses).
Just set PROXMOX_TOKEN_ID and PROXMOX_TOKEN_SECRET there and run:
  python3 scripts/verify_proxmox_mcp.py
"""

import asyncio
import os
import sys

# Load .env from repo root (mirrors launch.sh: set -a; source .env)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE = os.path.join(_REPO_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            # Don't overwrite vars already set in the shell environment
            os.environ.setdefault(_k, _v)

sys.path.insert(0, _REPO_ROOT)

from portal_mcp.proxmox.proxmox_mcp import (
    PROXMOX_TOKEN_ID,
    PROXMOX_TOKEN_SECRET,
    PROXMOX_URL,
    PROXMOX_VERIFY_SSL,
    _client,
    _find_vm_node,
    _get,
    _resolve_node,
)

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = []
failed = []


def ok(label: str, detail: str = ""):
    passed.append(label)
    suffix = f"  {detail}" if detail else ""
    print(f"  {GREEN}✓{RESET} {label}{suffix}")


def fail(label: str, detail: str = ""):
    failed.append(label)
    suffix = f"  {detail}" if detail else ""
    print(f"  {RED}✗{RESET} {label}{suffix}")


async def main():
    print(f"\n{BOLD}Proxmox MCP — live verification{RESET}")
    print(f"  URL:   {PROXMOX_URL}")
    print(f"  Token: {PROXMOX_TOKEN_ID or '(not set)'}")
    print(f"  SSL:   {'verify' if PROXMOX_VERIFY_SSL else 'skip (self-signed)'}\n")

    if not PROXMOX_TOKEN_ID or not PROXMOX_TOKEN_SECRET:
        print(f"{RED}ERROR: PROXMOX_TOKEN_ID and PROXMOX_TOKEN_SECRET must be set.{RESET}")
        print("  Add them to .env:")
        print("    PROXMOX_TOKEN_ID=root@pam!yourtoken")
        print("    PROXMOX_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        sys.exit(1)

    async with _client() as c:
        # 1 — reachability + auth
        try:
            nodes = await _get(c, "/nodes")
            if nodes:
                names = [n["node"] for n in nodes]
                ok("reachability + auth", f"nodes={names}")
            else:
                fail("reachability + auth", "empty node list")
        except Exception as e:
            fail("reachability + auth", str(e))
            print(f"\n{RED}Cannot reach Proxmox — aborting remaining checks.{RESET}")
            sys.exit(1)

        # 2 — node auto-discover
        try:
            node = await _resolve_node(c, None)
            ok("node auto-discover", f"node={node}")
        except Exception as e:
            fail("node auto-discover", str(e))
            node = nodes[0]["node"]

        # 3 — node status
        try:
            status = await _get(c, f"/nodes/{node}/status")
            cpu = status.get("cpu", "?")
            mem_pct = (
                round(status["memory"]["used"] / status["memory"]["total"] * 100)
                if status.get("memory")
                else "?"
            )
            ok("node status", f"cpu={cpu:.1%}  mem={mem_pct}%")
        except Exception as e:
            fail("node status", str(e))

        # 4 — list VMs
        try:
            vms = await _get(c, f"/nodes/{node}/qemu") or []
            vm_summary = [(v["vmid"], v.get("name", "?"), v.get("status")) for v in vms]
            ok("list VMs", f"{len(vms)} VMs: {vm_summary[:5]}")
        except Exception as e:
            fail("list VMs", str(e))
            vms = []

        # 5 — cluster resources (cross-node view)
        try:
            all_res = await _get(c, "/cluster/resources", type="vm") or []
            ok("cluster resources", f"{len(all_res)} total VMs/CTs across all nodes")
        except Exception as e:
            fail("cluster resources", str(e))

        # 6 — list LXC containers
        try:
            cts = await _get(c, f"/nodes/{node}/lxc") or []
            ok("list containers", f"{len(cts)} LXC containers")
        except Exception as e:
            fail("list containers", str(e))

        # 7 — storage
        try:
            stores = await _get(c, f"/nodes/{node}/storage") or []
            ok("list storage", f"{len(stores)} pools: {[s['storage'] for s in stores]}")
        except Exception as e:
            fail("list storage", str(e))

        # 8 — network
        try:
            nets = await _get(c, f"/nodes/{node}/network") or []
            ok("list networks", f"{len(nets)} interfaces")
        except Exception as e:
            fail("list networks", str(e))

        # 9 — find a VM by vmid (pick first running one if available)
        running = [v for v in vms if v.get("status") == "running"]
        if running:
            vmid = running[0]["vmid"]
            try:
                found_node = await _find_vm_node(c, vmid)
                ok("find VM by vmid", f"vmid={vmid} → node={found_node}")
            except Exception as e:
                fail("find VM by vmid", str(e))

            # 10 — VM status detail
            try:
                s = await _get(c, f"/nodes/{node}/qemu/{vmid}/status/current")
                ok(
                    "VM status detail",
                    f"vmid={vmid} status={s.get('status')} cpu={s.get('cpu', 0):.1%}",
                )
            except Exception as e:
                fail("VM status detail", str(e))

            # 11 — VM snapshots
            try:
                snaps = await _get(c, f"/nodes/{node}/qemu/{vmid}/snapshot") or []
                ok(
                    "list snapshots",
                    f"vmid={vmid} snapshots={[s['name'] for s in snaps if s.get('name') != 'current']}",
                )
            except Exception as e:
                fail("list snapshots", str(e))
        else:
            print(f"  {YELLOW}~{RESET} VM-level checks skipped (no running VMs found)")

    print()
    print(f"  {GREEN}{len(passed)} passed{RESET}  {RED}{len(failed)} failed{RESET}\n")
    if failed:
        print(f"  Failed: {failed}")
        sys.exit(1)
    print(f"  {GREEN}{BOLD}All checks passed — Proxmox MCP is operational.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())

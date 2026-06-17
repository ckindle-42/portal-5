# Portal 5 — Security Lab Setup

Offline red/blue team testing environment. Incalmo (autonomous red team) and Talon (SOC analyst) run as Docker services; they call Portal 5's pipeline as their LLM backend.

## Architecture

```
┌─────────────────────────────────────────┐    ┌─────────────────────────────┐
│  Mac (Portal 5 + Lab Services)          │    │  VM Lab (192.168.56.0/24)   │
│                                         │    │                             │
│  portal-pipeline :9099                  │    │  dc01  .100  AD DC          │
│       ↑  auto-redteam (Incalmo brain)   │    │  ws01  .101  Workstation    │
│       ↑  auto-blueteam (Talon brain)    │    │  srv01 .102  Member server  │
│       ↑  auto-purpleteam (chain)        │    │  kali  .10   Attack pivot   │
│                                         │    │    (optional)               │
│  incalmo-c2   :8930 ───────────────────────→  executes attack plans        │
│  talon-soc    :8931 ←──────────────────────── Wazuh agents ship events     │
│  wazuh-manager      ←─────────── :1515/1514   agent enrollment/syslog      │
│  wazuh-indexer :9201                    │    │                             │
└─────────────────────────────────────────┘    └─────────────────────────────┘
```

**Level 1**: Portal pipeline workspaces (auto-redteam, auto-blueteam, auto-security)  
**Level 2**: Purple team chain — Qwen3.5-abliterated → Foundation-Sec-8B in one response  
**Level 3**: Incalmo orchestrates multi-step attacks; Talon auto-triages resulting alerts

## VM Lab Setup

### Option A: GOAD (Game of Active Directory) — Recommended

GOAD is a pre-built vulnerable AD lab with known misconfigurations (Kerberoastable accounts, AS-REP roasting, coerceable hosts, NTLM relay paths). Exactly what Incalmo targets.

```bash
# On your hypervisor (Proxmox, VMware, or VirtualBox)
git clone https://github.com/Orange-Cyberdefense/GOAD.git
cd GOAD

# Proxmox (recommended — closest to production AD):
cd ad/GOAD/providers/proxmox
ansible-playbook build.yml      # ~45 min, provisions 5 VMs

# VirtualBox (lighter — 3 VMs):
cd ad/GOAD-Light/providers/virtualbox
vagrant up                      # ~30 min
```

GOAD-Light VMs:
- `DC01` — 192.168.56.10  (kingslanding.sevenkingdoms.local)
- `DC02` — 192.168.56.11  (winterfell.north.sevenkingdoms.local)
- `SRV01` — 192.168.56.22 (castelblack.north.sevenkingdoms.local)

Update `.env` to match:
```bash
LAB_TARGET_NETWORK=192.168.56.0/24
LAB_TARGET_DC=192.168.56.10
LAB_TARGET_WS=192.168.56.22
```

### Option B: Manual Windows Lab (Minimal)

| VM | OS | RAM | Disk | Role |
|---|---|---|---|---|
| dc01 | Windows Server 2022 Eval | 4GB | 60GB | AD DS + DNS |
| ws01 | Windows 10 22H2 | 4GB | 60GB | Domain member |
| srv01 | Windows Server 2019 Eval | 4GB | 60GB | IIS + SQL Express |

Configure:
1. Promote `dc01` to DC (`sevenkingdoms.local`)
2. Join `ws01` and `srv01` to domain
3. Create 3–5 service accounts with SPNs (Kerberoasting targets)
4. Enable unconstrained delegation on `srv01` (AD CS coercion path)
5. Set `Password: Password1!` on several accounts (weak password targets)

Network: **Host-only adapter** on `192.168.56.0/24`. Mac must be on same subnet or have a route.

---

## Starting the Lab

### Step 1 — Configure .env

```bash
# Minimum for Incalmo + Talon (no Wazuh):
LAB_TARGET_NETWORK=192.168.56.0/24
LAB_TARGET_DC=192.168.56.10

# For Wazuh:
LAB_OPENSEARCH_PASSWORD=SecureLab1!   # min 8 chars, 1 upper, 1 digit, 1 special
```

### Step 2 — Start lab services

```bash
# Incalmo C2 + Talon only (no Wazuh — use with existing SIEM or just Incalmo):
./launch.sh lab-up

# Full stack with Wazuh SIEM:
./launch.sh lab-up-wazuh
```

### Step 3 — Deploy Wazuh agents on VMs (if using lab-up-wazuh)

On each Windows VM (PowerShell as Administrator):
```powershell
# Replace <MAC_IP> with your Mac's IP on the host-only network
Invoke-WebRequest -Uri "https://packages.wazuh.com/4.x/windows/wazuh-agent-4.9.2-1.msi" `
  -OutFile "$env:TEMP\wazuh-agent.msi"

msiexec.exe /i "$env:TEMP\wazuh-agent.msi" `
  WAZUH_MANAGER="<MAC_IP>" `
  WAZUH_REGISTRATION_SERVER="<MAC_IP>" `
  /quiet

Start-Service -Name WazuhSvc
```

On each Linux VM:
```bash
# Replace <MAC_IP> with your Mac's IP on the host-only network
curl -so wazuh-agent.deb \
  https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.9.2-1_amd64.deb
WAZUH_MANAGER=<MAC_IP> dpkg -i ./wazuh-agent.deb
systemctl enable --now wazuh-agent
```

### Step 4 — Verify

```bash
./launch.sh lab-status

# Incalmo web UI:
open http://localhost:8930

# Talon SOC dashboard:
open http://localhost:8931

# Wazuh API check (if running):
curl -k -u wazuh:$LAB_OPENSEARCH_PASSWORD https://localhost:55000/
```

---

## Running Incalmo

Incalmo uses the Portal pipeline's `auto-redteam` workspace as its LLM brain. The LLM generates high-level declarative attack plans; Incalmo's domain agents translate them into tool calls (nmap, Metasploit modules, credential attacks).

**Basic red team run against DC:**
1. Open http://localhost:8930
2. Set target: `192.168.56.10` (or your DC IP)
3. Set objective: `Domain Admin` / `Credential Dump`
4. Start — Incalmo calls `auto-redteam` for planning, executes via agents

**Using purple team mode:**
Change `LAB_REDTEAM_WORKSPACE=auto-purpleteam` in `.env` and restart `lab-up`. Incalmo's planning calls will go through the full chain (Qwen3.5-abliterated red analysis → Foundation-Sec-8B blue analysis in one response).

---

## Talon Alert Triage

Talon polls Wazuh/OpenSearch every `LAB_TALON_POLL_INTERVAL` seconds. When alerts above `LAB_TALON_SEVERITY` (Wazuh rule level 1–15) arrive, it:
1. Enriches with threat intel (VirusTotal, MISP if configured)
2. Calls `auto-blueteam` (Foundation-Sec-8B-Reasoning) for analysis
3. Produces structured triage: severity (P1–P4), MITRE classification, containment steps, executive summary

**Testing the loop:**
Run Incalmo's Kerberoasting scenario → watch Talon triage the resulting Wazuh alerts in real time.

---

## Port Reference

| Port | Service |
|---|---|
| 8930 | Incalmo C2 web UI |
| 8931 | Talon SOC dashboard |
| 1514/udp | Wazuh syslog receiver (agents) |
| 1515 | Wazuh agent enrollment |
| 9201 | OpenSearch/Wazuh indexer API |
| 55000 | Wazuh REST API |
| 5601 | Wazuh Dashboard (lab-wazuh-ui profile only) |

---

## Shutting Down

```bash
./launch.sh lab-down     # stops all lab containers, preserves volumes
```

Wazuh volumes (`wazuh-*-data`) persist alert history across restarts. To wipe:
```bash
docker volume rm portal-5_wazuh-indexer-data portal-5_wazuh-manager-data portal-5_wazuh-manager-logs portal-5_wazuh-manager-queue
```

---

## Lab-Exec Lane (live execution from `*-exec` workspaces)

By default the `auto-purpleteam-exec` and `auto-pentest` workspaces' `execute_bash`
/ `execute_python` tools run in the locked-down code sandbox (`:8914`,
`--network none`) — they can validate logic but cannot reach lab targets. The
**lab-exec lane** lets those tools run live enumeration/PoC against a routable
remote lab machine.

Because the lab runs on a separate routable machine (not a Mac-local host-only
adapter), the DinD bridge network already provides the outbound path. You only
need to (1) ensure IP reachability and (2) set env vars.

### Enable

In `.env`:
```bash
SANDBOX_LAB_EXEC=true
SANDBOX_LAB_IMAGE=your-registry/portal5-attack:latest   # must contain nmap/impacket/netexec
LAB_TARGET_NETWORK=10.0.0.0/24      # your routable lab subnet
LAB_TARGET_DC=10.0.0.10
LAB_TARGET_WS=10.0.0.22
LAB_TARGET_SRV=10.0.0.23
```

Restart the sandbox service so it picks up the env:
```bash
./launch.sh restart   # or: docker compose -f deploy/portal-5/docker-compose.yml up -d mcp-sandbox
```

### Reachability prerequisite

This host (the Mac running Portal 5) must be able to route to the lab machine —
same LAN, a static route, or a VPN. Verify before enabling:
```bash
# From the Mac:
ping -c1 "$LAB_TARGET_DC"
# From inside the sandbox lane (proves the spawned container can reach it):
#   ask auto-pentest to run:  execute_bash -> "nc -zv $LAB_TARGET_DC 445"
```

### Posture matrix

| `SANDBOX_LAB_EXEC` | `SANDBOX_ALLOW_NETWORK` | network | image | env injected |
|---|---|---|---|---|
| false | false | none | alpine / python-slim | — |
| false | true | bridge | alpine / python-slim | — |
| true | (forced) | bridge | `SANDBOX_LAB_IMAGE` | `LAB_TARGET_*` |

### Safety

- `SANDBOX_LAB_EXEC=true` removes the network isolation that protects everything
  else. Only enable it on a host dedicated to lab work, and only point
  `LAB_TARGET_*` at systems you are authorized to test.
- The flag is global to the sandbox MCP — while it is on, **any** workspace whose
  tools reach `execute_bash`/`execute_python` runs network-enabled. Keep it off
  except during active lab sessions.

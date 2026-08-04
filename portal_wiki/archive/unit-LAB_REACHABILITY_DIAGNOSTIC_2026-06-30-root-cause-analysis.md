---
id: unit-LAB_REACHABILITY_DIAGNOSTIC_2026-06-30-root-cause-analysis
kind: why
title: "LAB_REACHABILITY_DIAGNOSTIC_2026-06-30 \u2014 Root cause analysis"
sources:
- type: design
  path: docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md
  section: Root cause analysis
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_REACHABILITY_DIAGNOSTIC_2026-06-30
created_at: 1783195000.8672352
updated_at: 1783195000.8672352
---


1. **Lab env vars unset**: `LAB_TARGET_DC`, `LAB_TARGET_SRV`, `LAB_DC_VMID`, `LAB_SRV_VMID`, and `SANDBOX_LAB_EXEC` are all empty in the current environment. The `_LAB_DC`/`_LAB_SRV` defaults to `10.10.11.21`/`10.10.11.33`.

2. **Sandbox → lab network path broken**: The `portal5-attack` container (executing inside `portal5-dind`) cannot reach the 10.10.11.0/24 subnet. The Python TCP-connect scan returns empty because every connection attempt hits `except: pass`.

3. **Proxmox MCP works**: VM lifecycle (start/rollback) succeeds — VMs 101, 102, 103 were started on proxmox3. This path doesn't go through the sandbox container.

4. **nmap unavailable in sandbox**: The `check_cve` step uses `nmap --script vuln` which fails with "Operation not permitted" in the sandbox container — this is a capability restriction.

5. **Model hallucinated target IP**: The chain model targeted `192.168.1.50:3389` instead of the expected `10.10.11.21` — this is a separate model behavior issue.

---

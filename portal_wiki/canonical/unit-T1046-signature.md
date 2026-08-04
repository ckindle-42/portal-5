---
id: unit-T1046-signature
kind: mixed
title: "T1046 \u2014 Network service discovery detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1046
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1046
- signature
- technique
- verified-v1
created_at: 1785503864.9320252
updated_at: 1785503864.9320252
---

# T1046 — Network service discovery detection signature

## What This Detection Sees

Network service discovery is caught at the attacker host by execve records for the tools that do the scanning. The SPL matches `nmap`, `masscan`, and the SNMP walkers `snmpwalk` and `snmpbulkwalk`, then groups by host and first argument so each scanning host is visible separately. A Windows variant watches process creation (4688) for the same tool names.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="nmap" OR a0="masscan" OR a0="snmpwalk" OR a0="snmpbulkwalk") | stats count by host, a0
```

## Expected Signal

Network scanning tool execution (`nmap`, `snmpwalk`) — the tool-name filter is deliberately short because discovery tooling is noisy by nature and the point is attribution, not suppression.

## Exercised By Scenarios

- `meta3_snmp_enum`
- `vuln_adminer_ssrf_recon`
- `mission_meta3_recon_exploit`
- `mission_meta3_lateral_pivot`

## Why

The signature stays with the executable SPL because the scan tools are the load-bearing constant: `nmap` and `masscan` for port sweeps, the SNMP walkers for community-string enumeration. Keeping the unit pinned to those execve literals rather than a description preserves the exact match that lab telemetry relies on, and the Windows 4688 variant documents the cross-platform shape of the same discovery behavior.

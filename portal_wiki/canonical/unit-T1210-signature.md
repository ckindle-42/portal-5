---
id: unit-T1210-signature
kind: mixed
title: "T1210 \u2014 SMB/service exploitation \u2014 lateral movement via SMB"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1210
- type: mitre
  path: ATT&CK:T1210
- type: scenario
  path: exec_chain.py#meta3_smb_exploit
last_generated_commit: ''
confidence: high
tags:
- T1210
- technique
- signature
created_at: 1783289794.013576
updated_at: 1783289794.013576
---

# T1210 — SMB/service exploitation — lateral movement via SMB

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="smbclient" OR a0="nxc" OR a0="crackmapexec") | stats count by host, a0
```

## Exercised By Scenarios

- `meta3_smb_exploit` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1210 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

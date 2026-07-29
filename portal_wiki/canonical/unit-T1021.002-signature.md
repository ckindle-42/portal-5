---
id: unit-T1021.002-signature
kind: mixed
title: "T1021.002 \u2014 SMB/Windows Admin Shares \u2014 remote file copy via SMB"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1021.002
- type: mitre
  path: ATT&CK:T1021.002
- type: scenario
  path: exec_chain.py#meta3_smb_exploit
- type: scenario
  path: exec_chain.py#meta3_winrm_weakpass
- type: scenario
  path: exec_chain.py#meta3_psexec
last_generated_commit: ''
confidence: high
tags:
- T1021.002
- technique
- signature
created_at: 1785351452.8777559
updated_at: 1785351452.8777559
---

# T1021.002 — SMB/Windows Admin Shares — remote file copy via SMB

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="smbclient" OR a0="smbget") | stats count by host, a0
```

## Exercised By Scenarios

- `meta3_smb_exploit`
- `meta3_winrm_weakpass`
- `meta3_psexec`
- `mission_meta3_lateral_pivot`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1021.002 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

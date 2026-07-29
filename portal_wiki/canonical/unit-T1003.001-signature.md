---
id: unit-T1003.001-signature
kind: mixed
title: "T1003.001 \u2014 LSASS dump \u2014 credential dumping via lsass.exe memory\
  \ access [DISTINGUISH: T1003.001 = local LSASS memory access; T1003.003 = NTDS.dit\
  \ extraction; T1003.006 = remote AD replication] [KEY: TargetImage=*lsass* or NewProcessName=*lsass*]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1003.001
- type: mitre
  path: ATT&CK:T1003.001
- type: scenario
  path: exec_chain.py#ad_full_compromise
last_generated_commit: ''
confidence: high
tags:
- T1003.001
- technique
- signature
created_at: 1785349554.521665
updated_at: 1785349554.521665
---

# T1003.001 — LSASS dump — credential dumping via lsass.exe memory access [DISTINGUISH: T1003.001 = local LSASS memory access; T1003.003 = NTDS.dit extraction; T1003.006 = remote AD replication] [KEY: TargetImage=*lsass* or NewProcessName=*lsass*]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*lsass*" OR NewProcessName="*procdump*" OR NewProcessName="*comsvcs*") OR EventCode=10 (TargetImage="*lsass*")) | stats count by NewProcessName, Account
```

## Exercised By Scenarios

- `ad_full_compromise` — target: 10.10.11.21

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Process access to lsass.exe (handle request) |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

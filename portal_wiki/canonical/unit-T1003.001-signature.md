---
id: unit-T1003.001-signature
kind: mixed
title: "T1003.001 \u2014 LSASS dump \u2014 credential dumping via lsass.exe memory\
  \ access"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1003.001
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
created_at: 1784855332.556205
updated_at: 1784855332.556205
---

# T1003.001 — LSASS dump — credential dumping via lsass.exe memory access

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

---
id: unit-T1003.003-signature
kind: mixed
title: "T1003.003 \u2014 NTDS dump \u2014 ntdsutil/ntds.dit extraction for domain\
  \ credential theft"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1003.003
- type: mitre
  path: ATT&CK:T1003.003
- type: scenario
  path: exec_chain.py#relay_to_shell
last_generated_commit: ''
confidence: high
tags:
- T1003.003
- technique
- signature
created_at: 1784898346.2116292
updated_at: 1784898346.2116292
---

# T1003.003 — NTDS dump — ntdsutil/ntds.dit extraction for domain credential theft

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*ntdsutil*") OR EventCode=4661 OR Message="*ntds.dit*") | stats count by Account, NewProcessName
```

## Exercised By Scenarios

- `relay_to_shell` — target: 10.10.11.21

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | File access to NTDS.dit or Volume Shadow Copy |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

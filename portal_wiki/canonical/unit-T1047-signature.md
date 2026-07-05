---
id: unit-T1047-signature
kind: mixed
title: "T1047 \u2014 WMI execution \u2014 remote command execution via WMI/cimv2"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1047
- type: mitre
  path: ATT&CK:T1047
- type: scenario
  path: exec_chain.py#ad_full_compromise
last_generated_commit: ''
confidence: high
tags:
- T1047
- technique
- signature
created_at: 1783289794.017426
updated_at: 1783289794.017426
---

# T1047 — WMI execution — remote command execution via WMI/cimv2

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*wmic*" OR NewProcessName="*WmiPrvSE*") OR EventCode=5861) | stats count by NewProcessName, Account
```

## Exercised By Scenarios

- `ad_full_compromise` — target: None

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1047 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

---
id: unit-T1053.005-signature
kind: mixed
title: "T1053.005 \u2014 Scheduled task persistence \u2014 Windows Security Event\
  \ 4698"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1053.005
- type: mitre
  path: ATT&CK:T1053.005
- type: scenario
  path: exec_chain.py#kerberoast_to_da
- type: scenario
  path: exec_chain.py#asrep_to_lateral
last_generated_commit: ''
confidence: high
tags:
- T1053.005
- technique
- signature
created_at: 1784898346.207846
updated_at: 1784898346.207846
---

# T1053.005 — Scheduled task persistence — Windows Security Event 4698

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4698 | stats count by TaskName, Account
```

## Exercised By Scenarios

- `kerberoast_to_da` — target: 10.10.11.21
- `asrep_to_lateral` — target: 10.10.11.21

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1053.005 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

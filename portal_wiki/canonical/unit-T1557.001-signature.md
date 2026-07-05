---
id: unit-T1557.001-signature
kind: mixed
title: "T1557.001 \u2014 LLMNR/NBT-NS poisoning \u2014 Responder/capture events on\
  \ Windows network"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1557.001
- type: mitre
  path: ATT&CK:T1557.001
- type: scenario
  path: exec_chain.py#relay_to_shell
last_generated_commit: ''
confidence: high
tags:
- T1557.001
- technique
- signature
created_at: 1783280601.5507
updated_at: 1783280601.5507
---

# T1557.001 — LLMNR/NBT-NS poisoning — Responder/capture events on Windows network

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab (sourcetype="windows:security" (EventCode=4697 OR Message="*LLMNR*" OR Message="*responder*") OR (sourcetype="linux:auditd" exe="*responder*")) | stats count by host, sourcetype
```

## Exercised By Scenarios

- `relay_to_shell` — target: None

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1557.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

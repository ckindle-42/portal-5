---
id: unit-T1558.004-signature
kind: mixed
title: "T1558.004 \u2014 AS-REP Roasting \u2014 Windows Security Event 4768 without\
  \ pre-auth [DISTINGUISH: T1558.004 uses EventCode=4768 (AS-REQ) with PreAuthType=0;\
  \ T1558.003 uses EventCode=4769 (TGS-REQ) with RC4] [KEY: PreAuthType=0 in 4768\
  \ events]"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1558.004
- type: mitre
  path: ATT&CK:T1558.004
- type: scenario
  path: exec_chain.py#asrep_to_lateral
last_generated_commit: ''
confidence: high
tags:
- T1558.004
- technique
- signature
created_at: 1784050004.179803
updated_at: 1784050004.179803
---

# T1558.004 — AS-REP Roasting — Windows Security Event 4768 without pre-auth [DISTINGUISH: T1558.004 uses EventCode=4768 (AS-REQ) with PreAuthType=0; T1558.003 uses EventCode=4769 (TGS-REQ) with RC4] [KEY: PreAuthType=0 in 4768 events]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0 | stats count by Account
```

## Exercised By Scenarios

- `asrep_to_lateral` — target: 10.10.11.21

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Event 4768 without pre-authentication required (AS-REP Roasting) |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

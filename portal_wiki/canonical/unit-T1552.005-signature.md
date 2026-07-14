---
id: unit-T1552.005-signature
kind: mixed
title: "T1552.005 \u2014 Cloud-metadata SSRF \u2014 169.254.169.254 access signal"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1552.005
- type: mitre
  path: ATT&CK:T1552.005
- type: scenario
  path: exec_chain.py#cloud_breach
last_generated_commit: ''
confidence: high
tags:
- T1552.005
- technique
- signature
created_at: 1784058424.856135
updated_at: 1784058424.856135
---

# T1552.005 — Cloud-metadata SSRF — 169.254.169.254 access signal

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" "169.254.169.254" | stats count by host, _raw
```

## Exercised By Scenarios

- `cloud_breach` — target: 10.0.1.140

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1552.005 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

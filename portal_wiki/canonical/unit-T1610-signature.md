---
id: unit-T1610-signature
kind: mixed
title: "T1610 \u2014 Container deploy \u2014 docker-daemon events"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1610
- type: mitre
  path: ATT&CK:T1610
last_generated_commit: ''
confidence: high
tags:
- T1610
- technique
- signature
created_at: 1783201357.6874099
updated_at: 1783201357.6874099
---

# T1610 — Container deploy — docker-daemon events

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="docker:daemon" (create OR start) | stats count by host, container_name
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1610 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

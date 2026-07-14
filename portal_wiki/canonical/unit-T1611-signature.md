---
id: unit-T1611-signature
kind: mixed
title: "T1611 \u2014 Container escape \u2014 host auditd + docker events"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1611
- type: mitre
  path: ATT&CK:T1611
last_generated_commit: ''
confidence: high
tags:
- T1611
- technique
- signature
created_at: 1784055842.2876632
updated_at: 1784055842.2876632
---

# T1611 — Container escape — host auditd + docker events

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab (sourcetype="linux:auditd" "nsenter" OR "mount" OR "/proc/1") OR (sourcetype="docker:daemon" "privileged") | stats count by host
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1611 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

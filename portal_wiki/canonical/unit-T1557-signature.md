---
id: unit-T1557-signature
kind: mixed
title: "T1557 \u2014 Adversary-in-the-middle \u2014 NTLM relay and LLMNR/NBT-NS poisoning"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1557
- type: mitre
  path: ATT&CK:T1557
last_generated_commit: ''
confidence: high
tags:
- T1557
- technique
- signature
created_at: 1784058424.860597
updated_at: 1784058424.860597
---

# T1557 — Adversary-in-the-middle — NTLM relay and LLMNR/NBT-NS poisoning

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4624 LogonType=3) | stats count by IpAddress, Account | where count > 5
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1557 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

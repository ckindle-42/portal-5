---
id: unit-T1550.002-signature
kind: mixed
title: "T1550.002 \u2014 Pass-the-hash \u2014 NTLM hash authentication"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1550.002
- type: mitre
  path: ATT&CK:T1550.002
claims: []
confidence: high
tags:
- T1550.002
- technique
- signature
created_at: 1788236495.093078
updated_at: 1788236495.093078
---

# T1550.002 — Pass-the-hash — NTLM hash authentication

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4624 LogonType=3 AuthenticationPackageName=NTLM | stats count by Account, IpAddress
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1550.002 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

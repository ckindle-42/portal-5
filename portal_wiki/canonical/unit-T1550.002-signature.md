---
id: unit-T1550.002-signature
kind: mixed
title: "T1550.002 \u2014 Pass-the-hash \u2014 NTLM hash authentication"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1550.002
- type: mitre
  path: ATT&CK:T1550.002
- type: scenario
  path: exec_chain.py#relay_to_shell
last_generated_commit: ''
confidence: high
tags:
- T1550.002
- technique
- signature
created_at: 1783828011.523953
updated_at: 1783828011.523953
---

# T1550.002 — Pass-the-hash — NTLM hash authentication

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4624 LogonType=3 AuthenticationPackageName=NTLM | stats count by Account, IpAddress
```

## Exercised By Scenarios

- `relay_to_shell` — target: None

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1550.002 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

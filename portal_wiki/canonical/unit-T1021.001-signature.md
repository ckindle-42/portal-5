---
id: unit-T1021.001-signature
kind: mixed
title: "T1021.001 \u2014 Remote Desktop Protocol \u2014 successful remote-interactive\
  \ Windows logon [DISTINGUISH: T1021.001 uses remote-interactive LogonType 10; T1021.002\
  \ uses SMB share access EventCode 5140] [KEY: EventCode=4624 with LogonType=10]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1021.001
- type: mitre
  path: ATT&CK:T1021.001
- type: scenario
  path: exec_chain.py#meta3_rdp_standard_auth
claims:
- probe: repo.symbol.exists
  path: portal/modules/security/core/siem/spl_detections.yaml
  symbol: T1021.001
  equals: true
confidence: high
tags:
- T1021.001
- technique
- signature
---

# T1021.001 — Remote Desktop Protocol — successful remote-interactive Windows logon [DISTINGUISH: T1021.001 uses remote-interactive LogonType 10; T1021.002 uses SMB share access EventCode 5140] [KEY: EventCode=4624 with LogonType=10]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4624 LogonType=10 (AuthenticationPackageName="Negotiate" OR AuthenticationPackageName="NTLM") | stats count by Account, IpAddress, WorkstationName
```

## Exercised By Scenarios

- `meta3_rdp_standard_auth`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1021.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

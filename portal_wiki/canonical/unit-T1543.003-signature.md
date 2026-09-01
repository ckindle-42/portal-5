---
id: unit-T1543.003-signature
kind: mixed
title: "T1543.003 \u2014 Windows service creation \u2014 suspicious System 7045 service\
  \ install [KEY: EventCode=7045 with a suspicious service image path]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1543.003
- type: mitre
  path: ATT&CK:T1543.003
claims: []
confidence: high
tags:
- T1543.003
- technique
- signature
created_at: 1788236495.097936
updated_at: 1788236495.097936
---

# T1543.003 — Windows service creation — suspicious System 7045 service install [KEY: EventCode=7045 with a suspicious service image path]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:system" EventCode=7045 (ImagePath="*powershell*" OR ImagePath="*cmd.exe*" OR ImagePath="*RemComSvc.exe*" OR ServiceFileName="*powershell*" OR ServiceFileName="*cmd.exe*" OR ServiceFileName="*RemComSvc.exe*") | stats count by host, ServiceName, ImagePath, ServiceFileName, AccountName
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1543.003 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

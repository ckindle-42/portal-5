---
id: unit-T1059.001-signature
kind: mixed
title: "T1059.001 \u2014 PowerShell execution \u2014 Sysmon process creation or script-block\
  \ telemetry [KEY: PowerShell image in Sysmon or suspicious script-block content]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1059.001
- type: mitre
  path: ATT&CK:T1059.001
claims: []
confidence: high
tags:
- T1059.001
- technique
- signature
created_at: 1788236495.0975869
updated_at: 1788236495.0975869
---

# T1059.001 — PowerShell execution — Sysmon process creation or script-block telemetry [KEY: PowerShell image in Sysmon or suspicious script-block content]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:sysmon" EventCode=1 (Image="*powershell.exe" OR OriginalFileName="PowerShell.EXE") | stats count by host, Image, CommandLine, ParentImage
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1059.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

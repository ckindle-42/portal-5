---
id: unit-T1003.003-signature
kind: mixed
title: "T1003.003 \u2014 NTDS dump \u2014 ntdsutil/ntds.dit extraction for domain\
  \ credential theft [DISTINGUISH: T1003.003 = NTDS.dit extraction; T1003.001 = local\
  \ LSASS memory access; T1003.006 = remote AD replication] [KEY: NewProcessName=*ntdsutil*\
  \ or Message=*ntds.dit*]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1003.003
- type: mitre
  path: ATT&CK:T1003.003
claims: []
confidence: high
tags:
- T1003.003
- technique
- signature
created_at: 1788561801.153826
updated_at: 1788561801.153826
---

# T1003.003 — NTDS dump — ntdsutil/ntds.dit extraction for domain credential theft [DISTINGUISH: T1003.003 = NTDS.dit extraction; T1003.001 = local LSASS memory access; T1003.006 = remote AD replication] [KEY: NewProcessName=*ntdsutil* or Message=*ntds.dit*]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*ntdsutil*") OR EventCode=4661 OR Message="*ntds.dit*") | stats count by Account, NewProcessName
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | File access to NTDS.dit or Volume Shadow Copy |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

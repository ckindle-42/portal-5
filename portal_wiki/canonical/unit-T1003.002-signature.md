---
id: unit-T1003.002-signature
kind: mixed
title: "T1003.002 \u2014 SAM dump \u2014 remote Security Account Manager hash extraction\
  \ via RemoteRegistry [DISTINGUISH: T1003.002 = local SAM hive on a non-DC host via\
  \ RemoteRegistry; T1003.001 = local LSASS memory access; T1003.003 = NTDS.dit extraction\
  \ on the DC; T1003.006 = remote AD replication] [KEY: ServiceName=\"Remote Registry\"\
  \ State=running, or IPC$ winreg pipe access]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1003.002
- type: mitre
  path: ATT&CK:T1003.002
- type: scenario
  path: exec_chain.py#relay_to_shell
claims: []
confidence: high
tags:
- T1003.002
- technique
- signature
created_at: 1788236495.093725
updated_at: 1788236495.093725
---

# T1003.002 — SAM dump — remote Security Account Manager hash extraction via RemoteRegistry [DISTINGUISH: T1003.002 = local SAM hive on a non-DC host via RemoteRegistry; T1003.001 = local LSASS memory access; T1003.003 = NTDS.dit extraction on the DC; T1003.006 = remote AD replication] [KEY: ServiceName="Remote Registry" State=running, or IPC$ winreg pipe access]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=7036 ServiceName="Remote Registry" State=running) OR (EventCode=5145 ShareName="*\\IPC$" RelativeTargetName="*winreg*") | stats count by host, Account
```

## Exercised By Scenarios

- `relay_to_shell`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1003.002 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

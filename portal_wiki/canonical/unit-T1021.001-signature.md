---
id: unit-T1021.001-signature
kind: mixed
title: "T1021.001 \u2014 Remote Desktop Protocol detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1021.001
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1021.001
- signature
- technique
- verified-v1
created_at: 1785503864.926115
updated_at: 1785503864.926115
---

# T1021.001 — Remote Desktop Protocol detection signature

## What This Detection Sees

Remote Desktop logons are spotted by the success event Windows emits for a remote-interactive session. The SPL filters 4624 events to `LogonType` 10 and the two authentication packages a normal RDP session uses, `Negotiate` or `NTLM`, then groups by `Account`, `IpAddress`, and `WorkstationName` so a session can be traced to its source host and identity.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4624 LogonType=10 (AuthenticationPackageName="Negotiate" OR AuthenticationPackageName="NTLM") | stats count by Account, IpAddress, WorkstationName
```

## Expected Signal

Successful RDP remote-interactive logon (4624 with `LogonType` 10) — the logon-type filter is what separates a desktop session from a network or service logon.

## Distinguishing From Siblings

Contrast with T1021.002, whose SMB share access is signaled by 5140 rather than a 4624 logon; the two lateral-movement channels do not share an event type.

## Exercised By Scenarios

- `meta3_rdp_standard_auth`

## Why

Grounded in the executable SPL because the logon-type filter is the whole signature: `LogonType` 10 is the remote-interactive marker, and dropping it would turn this into a generic success-logon detector. The unit also names the two authentication packages the query admits so a reader can see exactly which RDP authentication shapes the detection accepts.

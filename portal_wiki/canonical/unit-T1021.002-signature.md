---
id: unit-T1021.002-signature
kind: mixed
title: "T1021.002 \u2014 SMB/Windows Admin Shares detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1021.002
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1021.002
- signature
- technique
- verified-v1
created_at: 1785503864.926429
updated_at: 1785503864.926429
---

# T1021.002 — SMB/Windows Admin Shares detection signature

## What This Detection Sees

Remote file copy over SMB is observed at the source rather than the target: the primary SPL watches Linux auditd execve records for `smbclient` or `smbget` invocations, which is where an attack host reaches out. A Windows variant flips to the destination side, flagging 5140 share-access events where the `ShareName` is an administrative path and the account is neither anonymous nor a machine account.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="smbclient" OR a0="smbget") | stats count by host, a0
```

## Expected Signal

SMB share access from an attack host — `smbclient` or `smbget` execve on Linux, or 5140 network-share access to an admin share from a non-system account on Windows.

## Distinguishing From Siblings

The sibling RDP channel is detected through 4624 logon events; this unit instead keys on the share access itself, either from the copying tool or from the 5140 share event on the target.

## Exercised By Scenarios

- `meta3_smb_exploit`
- `meta3_winrm_weakpass`
- `meta3_psexec`
- `mission_meta3_lateral_pivot`

## Why

Pinned to the executable SPL because the source-side Linux auditd query and the destination-side 5140 variant are two different vantage points on the same move, and both are needed to catch SMB lateral movement in the lab. The scenario anchors tie the signature to the psexec and weak-password chains that actually copy files over admin shares.

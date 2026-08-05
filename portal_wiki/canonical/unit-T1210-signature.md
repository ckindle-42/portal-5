---
id: unit-T1210-signature
kind: mixed
title: "T1210 \u2014 SMB/service exploitation detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1210
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1210
- signature
- technique
- verified-v1
created_at: 1785503864.9258099
updated_at: 1785503864.9258099
---

# T1210 — SMB/service exploitation detection signature

## What This Detection Sees

SMB and service exploitation is caught at the source by the SMB client tools the attacker runs. The SPL watches auditd execve for `smbclient`, netexec (`nxc`), and `crackmapexec`, grouping by host and first argument. A Windows variant adds network logons with the `NTLM` or `Negotiate` packages as the destination-side signal of lateral movement.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="smbclient" OR a0="nxc" OR a0="crackmapexec") | stats count by host, a0
```

## Expected Signal

SMB client execution from the attack host, plus network logons on Windows carrying the `NTLM` or `Negotiate` authentication package.

## Exercised By Scenarios

- `meta3_smb_exploit`

## Why

Pinned to the executable SPL because the technique's observable is the exploitation tool, not the SMB protocol — the lab cannot see the vulnerable service's internals, so the source-side execve is the honest signal. The Windows logon variant gives the unit a target-side complement without pretending to observe the exploit itself.

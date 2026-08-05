---
id: unit-T1550.002-signature
kind: mixed
title: "T1550.002 \u2014 Pass-the-hash detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1550.002
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1550.002
- signature
- technique
- verified-v1
created_at: 1785503864.929021
updated_at: 1785503864.929021
---

# T1550.002 — Pass-the-hash detection signature

## What This Detection Sees

Pass-the-hash is the NTLM authentication case: a network logon (4624, `LogonType` 3) whose authentication package is `NTLM` means the credentials were used as a hash rather than verified interactively. The SPL groups by `Account` and source IP so the attacker's reused identity is visible across sessions.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4624 LogonType=3 AuthenticationPackageName=NTLM | stats count by Account, IpAddress
```

## Expected Signal

NTLM hash-based network authentication — the package filter is what separates this from a Kerberos logon, and the logon type pins it to network use.

## Exercised By Scenarios

- `relay_to_shell`

## Why

Grounded in the executable SPL because the authentication-package filter is the entire distinction the unit encodes: NTLM on a network logon is the hash-reuse tell. Keeping the query verbatim preserves that single-field discriminator that prose would otherwise soften.

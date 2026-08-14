---
id: unit-T1059.004-signature
kind: mixed
title: "T1059.004 \u2014 Unix shell detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1059.004
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1059.004
- signature
- technique
- verified-v1
created_at: 1785503864.930208
updated_at: 1785503864.930208
---

# T1059.004 — Unix shell detection signature

## What This Detection Sees

This sub-technique narrows command execution to the Unix shell family. The SPL watches auditd EXECVE records for the canonical interpreter paths — sh, bash, python3, perl, and php — and groups by host, executable, and first argument, so a payload dropped by a web exploit shows up as a shell invocation rather than as the exploit itself.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe="/bin/sh" OR exe="/bin/bash" OR exe="/usr/bin/python3" OR exe="/usr/bin/perl" OR exe="/usr/bin/php") | stats count by host, exe, a0
```

## Expected Signal

Shell or interpreter execve events from exploitation payloads — the query assumes the interpreter is the observable, not the original delivery vector.

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `web_to_root`
- `ctf_multi_service`
- `web_sqli_dump`
- `web_upload_bypass`

## Why

Grounded in the executable SPL because this unit is the one that fixes the interpreter list in absolute paths, and that exactness is what separates it from the broader parent technique. The scenario anchors are mostly web-to-shell chains, which is why the unit frames the interpreter execve as the shared terminal step across distinct entry vectors like SQLi and upload bypass.

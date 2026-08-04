---
id: unit-T1203-signature
kind: mixed
title: "T1203 \u2014 Exploitation for client execution detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1203
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1203
- signature
- technique
- verified-v1
created_at: 1785503864.930881
updated_at: 1785503864.930881
---

# T1203 — Exploitation for client execution detection signature

## What This Detection Sees

Client-side exploitation is detected by the delivery artifact: auditd EXECVE records whose first argument names `overflow`, `exploit`, or `payload`. The query groups by host, executable, and argument, treating the exploit stub as the observable rather than the vulnerable service it targets.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="*overflow*" OR a0="*exploit*" OR a0="*payload*") | stats count by host, exe, a0
```

## Expected Signal

Exploit payload execution against client services — the argument filter is the entire match, with no dependence on the target service's own logs.

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `ctf_multi_service`

## Why

Grounded in the executable SPL because client exploitation has no service-side event in the lab corpus, so the signature has to live on the attacker's own execve. Pinning the overflow, exploit, and payload argument literals documents that honest limitation while keeping the unit mechanically checkable.

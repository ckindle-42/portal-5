---
id: unit-T1548.001-signature
kind: mixed
title: "T1548.001 \u2014 SUID abuse detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1548.001
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1548.001
- signature
- technique
- verified-v1
created_at: 1785503864.926759
updated_at: 1785503864.926759
---

# T1548.001 — SUID abuse detection signature

## What This Detection Sees

SUID abuse is detected on Linux through auditd execve records for the two steps of the exploit. The SPL catches discovery — `find` invoked against a perm-4000 search — and abuse — `bash` launched with the privileged flag — grouping by host and executable. A Windows variant watches process creation for `runas`, `cmdkey`, and full-token elevation instead.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a1="*perm*4000*" OR exe="*/find" OR exe="*/bash" "-p") | stats count by host, exe
```

## Expected Signal

SUID binary discovery or bash `-p` execution — the query deliberately covers the reconnaissance half and the elevation half of the exploit.

## Exercised By Scenarios

- `web_to_root`

## Why

Pinned to the executable SPL because privilege escalation via setuid is a two-moment technique, and the query encodes both the discovery and the abuse in one filter. That pairing is why the unit mirrors the exact first-argument and executable literals rather than summarizing SUID exploitation generically.

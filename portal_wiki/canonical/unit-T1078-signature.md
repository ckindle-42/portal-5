---
id: unit-T1078-signature
kind: mixed
title: "T1078 \u2014 Valid accounts detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1078
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1078
- signature
- technique
- verified-v1
created_at: 1785503864.928332
updated_at: 1785503864.928332
---

# T1078 — Valid accounts detection signature

## What This Detection Sees

Valid-account abuse with default or weak credentials is detected by correlating two source types. The SPL joins web access success responses against auditd execve records where a client reaches for a service with explicit user flags — `curl` with `-u`, `mysql` with `-u`, or `redis-cli` — and groups by host, so authenticated-but-suspicious sessions stand out from the noise of unauthenticated traffic.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" (status=200) | join host [search index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="curl" "-u" OR a0="mysql" "-u" OR a0="redis-cli")] | stats count by host
```

## Expected Signal

Authenticated sessions using default or weak credentials — the cross-source join is what makes the query relational rather than a single-source watch.

## Exercised By Scenarios

- `web_nosql_inject`
- `web_idor`
- `meta3_ftp_backdoor`
- `meta3_mysql_exploit`
- `meta3_linux_privesc`

## Why

The unit follows the executable SPL because the cross-source join is the actual technique: neither the successful status alone nor the credential-using client alone is proof of T1078, only their co-occurrence on a host. Pinning that relational shape preserves the design decision, and the scenario anchors demonstrate the breadth of weak-credential abuse the lab exercises.

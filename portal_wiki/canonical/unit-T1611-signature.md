---
id: unit-T1611-signature
kind: mixed
title: "T1611 \u2014 Container escape detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1611
claims: []
confidence: high
tags:
- T1611
- signature
- technique
- verified-v1
created_at: 1785503864.9231381
updated_at: 1785503864.9231381
---

# T1611 — Container escape detection signature

## What This Detection Sees

Container escape is a two-source signal. The SPL matches Linux auditd records for the namespace-escape primitives — `nsenter`, `mount`, and access to the host init process via `/proc/1` — alongside Docker daemon events for privileged containers, grouping by host so escape attempts are attributable.

## SPL Detection

```spl
index=portal5_lab (sourcetype="linux:auditd" "nsenter" OR "mount" OR "/proc/1") OR (sourcetype="docker:daemon" "privileged") | stats count by host
```

## Expected Signal

Container escape indicators: `nsenter`, `mount`, `/proc/1` access, or a privileged container — the escape primitives are the observable, not the escape itself.

## Why

Pinned to the executable SPL because an escape is only visible through its primitives, and the query fixes exactly which ones count — `nsenter` and `mount` on the audit side, privileged on the daemon side. Keeping those literals verbatim preserves the boundary between this technique and ordinary container operations.

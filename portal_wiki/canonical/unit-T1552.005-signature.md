---
id: unit-T1552.005-signature
kind: mixed
title: "T1552.005 \u2014 Cloud-metadata SSRF detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1552.005
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1552.005
- signature
- technique
- verified-v1
created_at: 1785503864.9234078
updated_at: 1785503864.9234078
---

# T1552.005 — Cloud-metadata SSRF detection signature

## What This Detection Sees

Cloud-metadata theft is a single-literal signal: HTTP access to the link-local metadata address `169.254.169.254`. The SPL matches that address in web-access traffic and groups by host and raw event, because a server that never should reach the metadata service is either misconfigured or mid-attack.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" "169.254.169.254" | stats count by host, _raw
```

## Expected Signal

HTTP requests to the cloud metadata endpoint — one literal, deliberately narrow to keep the false-positive floor low.

## Exercised By Scenarios

- `cloud_breach`

## Why

Pinned to the executable SPL because the whole signature is the IP literal, and narrowing is the point — the unit documents that the detection intentionally trades coverage breadth for precision by matching only the canonical metadata address.

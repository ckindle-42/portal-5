---
id: unit-T1595-signature
kind: mixed
title: "T1595 \u2014 Active scanning detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1595
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1595
- signature
- technique
- verified-v1
created_at: 1785503864.927628
updated_at: 1785503864.927628
---

# T1595 — Active scanning detection signature

## What This Detection Sees

Active scanning is a volume signal on the web access log: a host accumulating a high rate of 404s is either brute-forcing paths or running a vulnerability scanner. The SPL counts not-found responses per host and URI path and retains only those above a threshold of ten.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" status=404 | stats count by host, uri_path | where count > 10
```

## Expected Signal

A high 404 rate from directory brute-force or vulnerability scanning — the count threshold is the rule, and the not-found status is the raw material.

## Exercised By Scenarios

- `web_asset_discovery`
- `web_nuclei_scan`
- `meta3_full_chain`

## Why

Pinned to the executable SPL because scanning is defined by volume, and the query's count-and-threshold shape is the whole detection. Restating "active scanning" without the 404 aggregate and the threshold would strip the unit of its only mechanical claim.

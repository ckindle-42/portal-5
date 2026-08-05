---
id: unit-T1505.003-signature
kind: mixed
title: "T1505.003 \u2014 Webshell detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1505.003
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1505.003
- signature
- technique
- verified-v1
created_at: 1785503864.922528
updated_at: 1785503864.922528
---

# T1505.003 — Webshell detection signature

## What This Detection Sees

Webshell persistence is a two-step correlation rather than a single event. The SPL takes web-access requests containing `uploads` and a `.php` extension, then joins them on host to requests that carry `cmd=` — the write followed by the execution. A host that produces both halves is a candidate webshell install.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" "uploads" ".php" | join host [search index=portal5_lab sourcetype="web:access" "cmd="] | stats count by host
```

## Expected Signal

PHP file upload followed by command execution via a webshell — the join is the technique's definition, not an afterthought.

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `meta3_webdav_upload`
- `mission_vulhub_multi_target`

## Why

The unit stays with the executable SPL because the correlation is the signature: upload alone is not persistence and command access alone is not a webshell, but the ordered pair on one host is. Keeping the join verbatim documents the design choice, and the scenario anchors show the webdav and vulhub upload paths that produce the two halves.

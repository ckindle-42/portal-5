---
id: unit-T1552-signature
kind: mixed
title: "T1552 \u2014 Unsecured credentials detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1552
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1552
- signature
- technique
- verified-v1
created_at: 1785503864.931629
updated_at: 1785503864.931629
---

# T1552 — Unsecured credentials detection signature

## What This Detection Sees

Unsecured credentials are surfaced by the HTTP fingerprints of their exposure. The SPL matches cloud metadata endpoints (the link-local address and the meta-data path), version-control and dotfile leaks (`.git/config`, `.env`), and literal credential keywords like `credentials`, `password=`, and `secret=`, grouping by host and URI path so each exposure is attributable.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" ("169.254.169.254" OR "/latest/meta-data" OR ".git/config" OR ".env" OR "credentials" OR "password=" OR "secret=") | stats count by host, uri_path, _raw
```

## Expected Signal

Metadata endpoint access or sensitive file exposure in HTTP traffic — the query is a union of exposure fingerprints rather than a single canonical event.

## Exercised By Scenarios

- `web_ssrf`
- `vuln_gitlab_rce`
- `vuln_joomla_rce`

## Why

The unit follows the executable SPL because T1552 is an umbrella technique and the query is what fixes its coverage boundaries — metadata, dotfiles, and credential keywords are three different abuse classes in one literal set. Keeping that union visible documents which exposure modes the lab can actually detect.

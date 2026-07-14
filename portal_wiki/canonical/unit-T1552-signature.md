---
id: unit-T1552-signature
kind: mixed
title: "T1552 \u2014 Unsecured credentials \u2014 SSRF-to-metadata, .env/.git exposure,\
  \ hardcoded creds"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1552
- type: mitre
  path: ATT&CK:T1552
- type: scenario
  path: exec_chain.py#web_ssrf
- type: scenario
  path: exec_chain.py#vuln_gitlab_rce
- type: scenario
  path: exec_chain.py#vuln_joomla_rce
last_generated_commit: ''
confidence: high
tags:
- T1552
- technique
- signature
created_at: 1784058424.863132
updated_at: 1784058424.863132
---

# T1552 — Unsecured credentials — SSRF-to-metadata, .env/.git exposure, hardcoded creds

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" ("169.254.169.254" OR "/latest/meta-data" OR ".git/config" OR ".env" OR "credentials" OR "password=" OR "secret=") | stats count by host, uri_path, _raw
```

## Exercised By Scenarios

- `web_ssrf` — target: 10.10.11.50
- `vuln_gitlab_rce` — target: 10.10.11.50
- `vuln_joomla_rce` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1552 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

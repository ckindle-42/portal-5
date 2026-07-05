---
id: unit-T1505.003-signature
kind: mixed
title: "T1505.003 \u2014 Webshell \u2014 file-write + subsequent exec correlation"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1505.003
- type: mitre
  path: ATT&CK:T1505.003
- type: scenario
  path: exec_chain.py#mbptl_ctf_full_chain
- type: scenario
  path: exec_chain.py#meta3_webdav_upload
last_generated_commit: ''
confidence: high
tags:
- T1505.003
- technique
- signature
created_at: 1783280601.5428128
updated_at: 1783280601.5428128
---

# T1505.003 — Webshell — file-write + subsequent exec correlation

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" "uploads" ".php" | join host [search index=portal5_lab sourcetype="web:access" "cmd="] | stats count by host
```

## Exercised By Scenarios

- `mbptl_ctf_full_chain` — target: 10.0.1.140
- `meta3_webdav_upload` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| web:access | File-write followed by execution of web-accessible path |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

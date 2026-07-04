---
id: unit-T1189-signature
kind: mixed
title: "T1189 \u2014 Drive-by compromise \u2014 reflected XSS and malicious redirect\
  \ indicators"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1189
- type: mitre
  path: ATT&CK:T1189
- type: scenario
  path: exec_chain.py#web_reflected_xss
- type: scenario
  path: exec_chain.py#web_open_redirect
last_generated_commit: ''
confidence: high
tags:
- T1189
- technique
- signature
created_at: 1783201357.693548
updated_at: 1783201357.693548
---

# T1189 — Drive-by compromise — reflected XSS and malicious redirect indicators

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" ("%3Cscript" OR "<script" OR "onerror=" OR "onload=" OR "javascript:" OR "redirect_url=" OR "Location:") | stats count by host, uri_path, _raw
```

## Exercised By Scenarios

- `web_reflected_xss` — target: 10.10.11.50
- `web_open_redirect` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1189 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

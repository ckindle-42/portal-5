---
id: unit-T1595-signature
kind: mixed
title: "T1595 \u2014 Active scanning \u2014 vulnerability scanning and directory brute-force"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1595
- type: mitre
  path: ATT&CK:T1595
- type: scenario
  path: exec_chain.py#web_asset_discovery
- type: scenario
  path: exec_chain.py#web_nuclei_scan
last_generated_commit: ''
confidence: high
tags:
- T1595
- technique
- signature
created_at: 1784898346.2097979
updated_at: 1784898346.2097979
---

# T1595 — Active scanning — vulnerability scanning and directory brute-force

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" status=404 | stats count by host, uri_path | where count > 10
```

## Exercised By Scenarios

- `web_asset_discovery` — target: 10.10.11.50
- `web_nuclei_scan` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1595 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

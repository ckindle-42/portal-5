---
id: unit-T1083-signature
kind: mixed
title: "T1083 \u2014 File and directory discovery \u2014 path traversal and LFI"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1083
- type: mitre
  path: ATT&CK:T1083
- type: scenario
  path: exec_chain.py#web_path_traversal
- type: scenario
  path: exec_chain.py#vuln_grafana_lfi
- type: scenario
  path: exec_chain.py#vuln_nginx_lfi
last_generated_commit: ''
confidence: high
tags:
- T1083
- technique
- signature
created_at: 1783201357.691377
updated_at: 1783201357.691377
---

# T1083 — File and directory discovery — path traversal and LFI

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" ("../" OR "..%2f" OR "etc/passwd" OR "proc/self") | stats count by host, uri_path
```

## Exercised By Scenarios

- `web_path_traversal` — target: 10.10.11.50
- `vuln_grafana_lfi` — target: 10.10.11.50
- `vuln_nginx_lfi` — target: 10.10.11.50
- `vuln_nexus_rce` — target: 10.10.11.50
- `vuln_rails_rce` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1083 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

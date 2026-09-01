---
id: unit-T1083-signature
kind: mixed
title: "T1083 \u2014 File and directory discovery \u2014 path traversal and LFI [KEY:\
  \ One of the path traversal literals used by this SPL]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1083
- type: mitre
  path: ATT&CK:T1083
- type: scenario
  path: exec_chain.py#web_path_traversal
- type: scenario
  path: exec_chain.py#vuln_grafana_lfi
- type: scenario
  path: exec_chain.py#vuln_nginx_lfi
claims: []
confidence: high
tags:
- T1083
- technique
- signature
created_at: 1788236495.091969
updated_at: 1788236495.091969
---

# T1083 — File and directory discovery — path traversal and LFI [KEY: One of the path traversal literals used by this SPL]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" ("../" OR "..%2f" OR "etc/passwd" OR "proc/self") | stats count by host, uri_path
```

## Exercised By Scenarios

- `web_path_traversal`
- `vuln_grafana_lfi`
- `vuln_nginx_lfi`
- `vuln_nexus_rce`
- `vuln_rails_rce`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1083 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

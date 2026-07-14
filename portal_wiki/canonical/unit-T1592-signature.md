---
id: unit-T1592-signature
kind: mixed
title: "T1592 \u2014 Gather victim host info \u2014 service fingerprinting and enumeration"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1592
- type: mitre
  path: ATT&CK:T1592
- type: scenario
  path: exec_chain.py#web_graphql_introspect
- type: scenario
  path: exec_chain.py#web_forced_error
- type: scenario
  path: exec_chain.py#web_asset_discovery
last_generated_commit: ''
confidence: high
tags:
- T1592
- technique
- signature
created_at: 1784058424.859335
updated_at: 1784058424.859335
---

# T1592 — Gather victim host info — service fingerprinting and enumeration

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" (user_agent="-" OR user_agent="curl*" OR user_agent="nmap*") | stats count by host, uri_path
```

## Exercised By Scenarios

- `web_graphql_introspect` — target: 10.10.11.50
- `web_forced_error` — target: 10.10.11.50
- `web_asset_discovery` — target: 10.10.11.50
- `meta3_snmp_enum` — target: 10.10.11.10
- `vuln_wordpress_rce` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1592 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

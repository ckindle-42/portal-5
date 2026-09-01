---
id: unit-T1592-signature
kind: mixed
title: "T1592 \u2014 Gather victim host info \u2014 service fingerprinting and enumeration"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1592
- type: mitre
  path: ATT&CK:T1592
- type: scenario
  path: exec_chain.py#web_graphql_introspect
- type: scenario
  path: exec_chain.py#web_forced_error
- type: scenario
  path: exec_chain.py#web_asset_discovery
claims: []
confidence: high
tags:
- T1592
- technique
- signature
created_at: 1788236495.0912168
updated_at: 1788236495.0912168
---

# T1592 — Gather victim host info — service fingerprinting and enumeration

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" (user_agent="-" OR user_agent="curl*" OR user_agent="nmap*") | stats count by host, uri_path
```

## Exercised By Scenarios

- `web_graphql_introspect`
- `web_forced_error`
- `web_asset_discovery`
- `meta3_snmp_enum`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1592 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

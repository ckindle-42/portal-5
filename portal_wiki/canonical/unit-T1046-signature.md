---
id: unit-T1046-signature
kind: mixed
title: "T1046 \u2014 Network service discovery \u2014 port scanning and SNMP enumeration"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1046
- type: mitre
  path: ATT&CK:T1046
- type: scenario
  path: exec_chain.py#meta3_snmp_enum
- type: scenario
  path: exec_chain.py#mission_meta3_recon_exploit
- type: scenario
  path: exec_chain.py#mission_meta3_lateral_pivot
last_generated_commit: ''
confidence: high
tags:
- T1046
- technique
- signature
created_at: 1784050004.18732
updated_at: 1784050004.18732
---

# T1046 — Network service discovery — port scanning and SNMP enumeration

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="nmap" OR a0="masscan" OR a0="snmpwalk" OR a0="snmpbulkwalk") | stats count by host, a0
```

## Exercised By Scenarios

- `meta3_snmp_enum` — target: 10.10.11.10
- `mission_meta3_recon_exploit` — target: 10.10.11.10
- `mission_meta3_lateral_pivot` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1046 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

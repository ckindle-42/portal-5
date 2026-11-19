---
id: unit-T1548.001-signature
kind: mixed
title: "T1548.001 \u2014 SUID abuse \u2014 setuid binary execution for privilege escalation"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1548.001
- type: mitre
  path: ATT&CK:T1548.001
- type: scenario
  path: exec_chain.py#web_to_root
claims:
- probe: repo.symbol.exists
  path: portal/modules/security/core/siem/spl_detections.yaml
  symbol: T1548.001
  equals: true
confidence: high
tags:
- T1548.001
- technique
- signature
---

# T1548.001 — SUID abuse — setuid binary execution for privilege escalation

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a1="*perm*4000*" OR exe="*/find" OR exe="*/bash" "-p") | stats count by host, exe
```

## Exercised By Scenarios

- `web_to_root`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1548.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

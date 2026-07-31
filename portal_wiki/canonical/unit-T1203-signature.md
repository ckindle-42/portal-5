---
id: unit-T1203-signature
kind: mixed
title: "T1203 \u2014 Exploitation for client execution \u2014 binary overflow and\
  \ service exploitation"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1203
- type: mitre
  path: ATT&CK:T1203
- type: scenario
  path: exec_chain.py#mbptl_ctf_full_chain
- type: scenario
  path: exec_chain.py#ctf_multi_service
last_generated_commit: ''
confidence: high
tags:
- T1203
- technique
- signature
created_at: 1785503864.930881
updated_at: 1785503864.930881
---

# T1203 — Exploitation for client execution — binary overflow and service exploitation

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="*overflow*" OR a0="*exploit*" OR a0="*payload*") | stats count by host, exe, a0
```

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `ctf_multi_service`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1203 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

---
id: unit-T1068-signature
kind: mixed
title: "T1068 \u2014 Exploitation for privilege escalation \u2014 kernel/userspace\
  \ privesc"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1068
- type: mitre
  path: ATT&CK:T1068
- type: scenario
  path: exec_chain.py#meta3_linux_privesc
last_generated_commit: ''
confidence: high
tags:
- T1068
- technique
- signature
created_at: 1783896250.521503
updated_at: 1783896250.521503
---

# T1068 — Exploitation for privilege escalation — kernel/userspace privesc

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe="*/exploit" OR exe="*/privesc" OR a1="*CVE*") | stats count by host, exe
```

## Exercised By Scenarios

- `meta3_linux_privesc` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1068 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

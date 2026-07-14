---
id: unit-T1548.001-signature
kind: mixed
title: "T1548.001 \u2014 SUID abuse \u2014 setuid binary execution for privilege escalation"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1548.001
- type: mitre
  path: ATT&CK:T1548.001
- type: scenario
  path: exec_chain.py#web_to_root
- type: scenario
  path: exec_chain.py#meta3_linux_privesc
- type: scenario
  path: exec_chain.py#meta3_full_chain
last_generated_commit: ''
confidence: high
tags:
- T1548.001
- technique
- signature
created_at: 1784059756.935096
updated_at: 1784059756.935096
---

# T1548.001 — SUID abuse — setuid binary execution for privilege escalation

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a1="*perm*4000*" OR exe="*/find" OR exe="*/bash" "-p") | stats count by host, exe
```

## Exercised By Scenarios

- `web_to_root` — target: 10.0.1.140
- `meta3_linux_privesc` — target: 10.10.11.10
- `meta3_full_chain` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1548.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

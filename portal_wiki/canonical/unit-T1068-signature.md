---
id: unit-T1068-signature
kind: mixed
title: "T1068 \u2014 Exploitation for privilege escalation \u2014 kernel/userspace\
  \ privesc"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1068
- type: mitre
  path: ATT&CK:T1068
last_generated_commit: ''
confidence: high
tags:
- T1068
- technique
- signature
created_at: 1785503864.927048
updated_at: 1785503864.927048
---

# T1068 — Exploitation for privilege escalation — kernel/userspace privesc

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe="*/exploit" OR exe="*/privesc" OR a1="*CVE*") | stats count by host, exe
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1068 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

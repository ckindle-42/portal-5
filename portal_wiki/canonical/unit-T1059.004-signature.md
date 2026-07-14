---
id: unit-T1059.004-signature
kind: mixed
title: "T1059.004 \u2014 Unix shell \u2014 command execution via sh/bash/python on\
  \ Linux targets"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1059.004
- type: mitre
  path: ATT&CK:T1059.004
- type: scenario
  path: exec_chain.py#mbptl_ctf_full_chain
- type: scenario
  path: exec_chain.py#web_to_root
- type: scenario
  path: exec_chain.py#ctf_multi_service
last_generated_commit: ''
confidence: high
tags:
- T1059.004
- technique
- signature
created_at: 1784050004.1858308
updated_at: 1784050004.1858308
---

# T1059.004 — Unix shell — command execution via sh/bash/python on Linux targets

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe="/bin/sh" OR exe="/bin/bash" OR exe="/usr/bin/python3" OR exe="/usr/bin/perl" OR exe="/usr/bin/php") | stats count by host, exe, a0
```

## Exercised By Scenarios

- `mbptl_ctf_full_chain` — target: 10.0.1.140
- `web_to_root` — target: 10.0.1.140
- `ctf_multi_service` — target: 10.0.1.140
- `web_sqli_dump` — target: 10.10.11.50
- `web_upload_bypass` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| linux:auditd | EXECVE syscall for /bin/sh, /bin/bash, etc. |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

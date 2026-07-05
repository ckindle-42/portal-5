---
id: unit-T1059-signature
kind: mixed
title: "T1059 \u2014 Command execution \u2014 auditd execve of shells/interpreters"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1059
- type: mitre
  path: ATT&CK:T1059
- type: scenario
  path: exec_chain.py#web_deserial_rce
- type: scenario
  path: exec_chain.py#web_reflected_xss
- type: scenario
  path: exec_chain.py#web_ssti
last_generated_commit: ''
confidence: high
tags:
- T1059
- technique
- signature
created_at: 1783289794.0099032
updated_at: 1783289794.0099032
---

# T1059 — Command execution — auditd execve of shells/interpreters

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe=/bin/sh OR exe=/bin/bash OR exe=/usr/bin/python* OR exe=/usr/bin/perl) | stats count by host, exe, a0
```

## Exercised By Scenarios

- `web_deserial_rce` — target: 10.10.11.50
- `web_reflected_xss` — target: 10.10.11.50
- `web_ssti` — target: 10.10.11.50
- `web_ssti_stored` — target: 10.10.11.50
- `meta3_elasticsearch_rce` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| linux:auditd | EXECVE syscall with shell/interpreter commands |
| windows:security | Process creation (4688) for cmd.exe/powershell.exe |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

---
id: unit-T1078-signature
kind: mixed
title: "T1078 \u2014 Valid accounts \u2014 default/weak credential usage"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1078
- type: mitre
  path: ATT&CK:T1078
- type: scenario
  path: exec_chain.py#web_nosql_inject
- type: scenario
  path: exec_chain.py#web_idor
- type: scenario
  path: exec_chain.py#meta3_ftp_backdoor
last_generated_commit: ''
confidence: high
tags:
- T1078
- technique
- signature
created_at: 1785503864.928332
updated_at: 1785503864.928332
---

# T1078 — Valid accounts — default/weak credential usage

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" (status=200) | join host [search index=portal5_lab sourcetype="linux:auditd" type=EXECVE (a0="curl" "-u" OR a0="mysql" "-u" OR a0="redis-cli")] | stats count by host
```

## Exercised By Scenarios

- `web_nosql_inject`
- `web_idor`
- `meta3_ftp_backdoor`
- `meta3_mysql_exploit`
- `meta3_linux_privesc`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Successful logon (4624) with unusual source or time |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

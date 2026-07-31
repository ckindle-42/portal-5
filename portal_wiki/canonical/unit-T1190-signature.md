---
id: unit-T1190-signature
kind: mixed
title: "T1190 \u2014 Web exploit \u2014 access-log signatures (LFI/SQLi/Log4Shell/webshell\
  \ markers) [KEY: One of the literal exploit markers used by this SPL]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1190
- type: mitre
  path: ATT&CK:T1190
- type: scenario
  path: exec_chain.py#mbptl_ctf_full_chain
- type: scenario
  path: exec_chain.py#web_to_root
- type: scenario
  path: exec_chain.py#ctf_multi_service
last_generated_commit: ''
confidence: high
tags:
- T1190
- technique
- signature
created_at: 1785503864.9216661
updated_at: 1785503864.9216661
---

# T1190 — Web exploit — access-log signatures (LFI/SQLi/Log4Shell/webshell markers) [KEY: One of the literal exploit markers used by this SPL]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" (passwd OR "../" OR "UNION SELECT" OR "${jndi:" OR ".php" OR "cmd=") | stats count by host, source, _raw
```

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `web_to_root`
- `ctf_multi_service`
- `web_sqli_dump`
- `web_graphql_introspect`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| web:access | HTTP requests with attack payloads in URI/body (LFI/SQLi/Log4Shell markers) |
| windows:security | Process creation (4688) from web server process |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

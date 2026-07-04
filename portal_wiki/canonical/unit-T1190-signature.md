---
id: unit-T1190-signature
kind: mixed
title: "T1190 \u2014 Web exploit \u2014 access-log signatures (LFI/SQLi/Log4Shell/webshell\
  \ markers)"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1190
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
created_at: 1783201357.686304
updated_at: 1783201357.686304
---

# T1190 — Web exploit — access-log signatures (LFI/SQLi/Log4Shell/webshell markers)

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="web:access" (passwd OR "../" OR "UNION SELECT" OR "${jndi:" OR ".php" OR "cmd=") | stats count by host, source, _raw
```

## Exercised By Scenarios

- `mbptl_ctf_full_chain` — target: 10.0.1.140
- `web_to_root` — target: 10.0.1.140
- `ctf_multi_service` — target: 10.0.1.140
- `web_sqli_dump` — target: 10.10.11.50
- `web_graphql_introspect` — target: 10.10.11.50

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| web:access | HTTP requests with attack payloads in URI/body (LFI/SQLi/Log4Shell markers) |
| windows:security | Process creation (4688) from web server process |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*

---
id: unit-T1190-signature
kind: mixed
title: "T1190 \u2014 Web exploit detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1190
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1190
- signature
- technique
- verified-v1
created_at: 1785503864.9216661
updated_at: 1785503864.9216661
---

# T1190 — Web exploit detection signature

## What This Detection Sees

Web-exploit initial access is detected by the payload markers an attacker leaves in access logs. The SPL matches LFI and SQLi probes (passwd, parent-dot, UNION SELECT), Log4Shell's jndi reference, and webshell indicators like `.php` and `cmd=`, grouped by host and source. An IIS variant shifts the lens to status-code and path signatures for Microsoft targets.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" (passwd OR "../" OR "UNION SELECT" OR "${jndi:" OR ".php" OR "cmd=") | stats count by host, source, _raw
```

## Expected Signal

HTTP requests with attack payloads in URI or body — the marker set spans four exploit families in one query, from traversal to Log4Shell.

## Exercised By Scenarios

- `mbptl_ctf_full_chain`
- `web_to_root`
- `ctf_multi_service`
- `web_sqli_dump`
- `web_graphql_introspect`

## Why

The unit follows the executable SPL because the technique is a grab-bag of exploit families and the query is what fixes the marker set — LFI, SQLi, Log4Shell, webshell. Describing "web exploits" without the literal list would leave the unit uncheckable, so the literals and the IIS variant are kept verbatim from the detection library.

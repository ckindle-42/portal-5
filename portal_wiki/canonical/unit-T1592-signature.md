---
id: unit-T1592-signature
kind: mixed
title: "T1592 \u2014 Gather victim host info detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1592
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1592
- signature
- technique
- verified-v1
created_at: 1785503864.927294
updated_at: 1785503864.927294
---

# T1592 — Gather victim host info detection signature

## What This Detection Sees

Host-information gathering is detected by the fingerprints scanners leave behind: web requests whose user agent is missing, a curl client, or an nmap sweep. The SPL groups by host and URI path, treating the `user_agent` field as the reconnaissance marker on the attacker's enumeration traffic.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" (user_agent="-" OR user_agent="curl*" OR user_agent="nmap*") | stats count by host, uri_path
```

## Expected Signal

Fingerprinting requests with scanner user agents — the query assumes the tool announces itself rather than disguising its identity.

## Exercised By Scenarios

- `web_graphql_introspect`
- `web_forced_error`
- `web_asset_discovery`
- `meta3_snmp_enum`
- `vuln_wordpress_rce`

## Why

The unit stays with the executable SPL because fingerprinting is a soft signal and the query fixes exactly which user agents count — absent, curl, nmap. That explicit list is what keeps the detection from flagging ordinary browsing, so the unit mirrors the literals rather than describing enumeration generically.

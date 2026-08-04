---
id: unit-T1083-signature
kind: mixed
title: "T1083 \u2014 File and directory discovery detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1083
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1083
- signature
- technique
- verified-v1
created_at: 1785503864.927974
updated_at: 1785503864.927974
---

# T1083 — File and directory discovery detection signature

## What This Detection Sees

File and directory discovery through web request pathing is a literal-match signature. The SPL scans web access for the traversal sequences an LFI probe leaves in the URI — parent-dot segments in both encoded forms, etc/passwd, and proc/self — and groups by host and URI path so the attacker's enumeration trail is visible as a set of requests rather than a single hit.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" ("../" OR "..%2f" OR "etc/passwd" OR "proc/self") | stats count by host, uri_path
```

## Expected Signal

Path traversal sequences in HTTP requests — the percent-encoded variant is included because naive decoders miss the obfuscated form.

## Exercised By Scenarios

- `web_path_traversal`
- `vuln_grafana_lfi`
- `vuln_nginx_lfi`
- `vuln_nexus_rce`
- `vuln_rails_rce`

## Why

Pinned to the executable SPL because the signature is the literals themselves: the distinction between a real LFI probe and ordinary browsing is a string difference, so a prose description would blur exactly what the query pins. Keeping the four discriminator tokens visible preserves the false-positive floor the lab relies on.

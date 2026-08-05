---
id: unit-T1189-signature
kind: mixed
title: "T1189 \u2014 Drive-by compromise detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1189
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1189
- signature
- technique
- verified-v1
created_at: 1785503864.9305542
updated_at: 1785503864.9305542
---

# T1189 — Drive-by compromise detection signature

## What This Detection Sees

Drive-by compromise is signalled at the edge by the browser-oriented payloads in web requests. The SPL matches reflected XSS markers — script tags in raw and percent-encoded form, onerror and onload handlers, and the javascript scheme — alongside redirect parameters, then groups by host, URI path, and raw event so each request is inspectable.

## SPL Detection

```spl
index=portal5_lab sourcetype="web:access" ("%3Cscript" OR "<script" OR "onerror=" OR "onload=" OR "javascript:" OR "redirect_url=" OR "Location:") | stats count by host, uri_path, _raw
```

## Expected Signal

XSS payloads or redirect parameters in HTTP requests — the percent-encoded script marker matters because proxies often keep the request intact.

## Exercised By Scenarios

- `web_reflected_xss`
- `web_open_redirect`

## Why

Pinned to the executable SPL because drive-by indicators are literal payload fragments, and the value of the unit is in which literals were chosen and why — the percent-encoded script tag catches what a naive decoder would hide. The scenario anchors show both the reflected XSS and open-redirect variants the lab reproduces.

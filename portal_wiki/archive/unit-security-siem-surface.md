---
id: unit-security-siem-surface
kind: mixed
title: "Security siem surface \u2014 Splunk integration boundary"
sources:
- type: code
  path: portal/modules/security/core/siem/__init__.py
  commit: b6f05201
last_generated_commit: b6f05201
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785796619.506561
updated_at: 1785796619.506561
---

The siem subpackage is the Splunk SIEM integration for the security bench:
HEC ingestion, the SplunkBackend query adapter, telemetry collection, the SPL
detection library, the blue-triage loop, and the index-wait gate.

## Why

The bench needs a *real* SIEM to test detections against, and grouping the
Splunk-facing code into one package marks the integration boundary: every
piece that talks to Splunk — ship telemetry in, query it out, wait for
indexing, triage the results — lives here rather than scattered through the
core. That is what lets the rest of the engine call one package for SIEM
behaviour and lets a different SIEM backend (or a mock) substitute at the
same boundary.

## Interfaces

`hec_ship` provides `ship`/`ship_batch`; `spl_backend` provides `SplunkBackend`;
`blue_triage` provides the poll/enrich/report loop; `index_wait` provides
`wait_indexed`; the SPL detection library and spl_detections live alongside.

---
id: unit-security-siem-spl-backend
kind: mixed
title: "SIEM Splunk backend \u2014 oneshot export query adapter"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_backend.py
  commit: b6f05201
last_generated_commit: b6f05201
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785796630.991267
updated_at: 1785796630.991267
---

`SplunkBackend` is the Splunk telemetry adapter implementing the
`TelemetryBackend` protocol. It queries `/services/search/jobs/export` with
oneshot JSON execution — a single round-trip with no job-poll loop — and
parses the rows for downstream correlation.

## Why

The export endpoint is chosen over the job API for a simple reason: a bench
that runs hundreds of detections cannot afford a create-job/then-poll cycle
per query, and oneshot export returns the full result in one response. The
host-field priority order (`host`, `ComputerName`, `dest`, `Computer`, `src`)
is the hard-won detail — different Windows and Linux sources name the host
field differently, and a correlation that guesses the wrong one silently
drops hosts. The class also owns the environment wiring (URL, user, index)
so the query path needs no per-call configuration.

## Interfaces

`SplunkBackend.name` is `"splunk"`; `_run_search` posts one SPL search to the
export endpoint and parses JSON hits into rows, shared by the exact
technique-SPL query and the broad discovery fallback. The public query method
implements the `TelemetryBackend` protocol the correlation layer consumes.

## Gotchas

`verify=False` on the HTTPS calls means the lab Splunk's self-signed
certificate is trusted unconditionally — acceptable inside the lab network,
but the adapter should never be pointed at a production SIEM.

---
id: unit-security-siem-index-wait
kind: mixed
title: "SIEM index-wait gate \u2014 block until telemetry is searchable"
sources:
- type: code
  path: portal/modules/security/core/siem/index_wait.py
  commit: b6f05201
last_generated_commit: b6f05201
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785796636.708726
updated_at: 1785796636.708726
---

`index_wait.py` blocks until HEC-shipped events are actually searchable, so
the blue team's SPL queries do not race the ingestion pipeline. It runs the
count query repeatedly against the export endpoint until the expected minimum
row count appears or the timeout expires.

## Why

Splunk indexes asynchronously: an event shipped by HEC is not immediately
searchable, and a detection that queries a millisecond after shipping
correctly finds nothing and produces a false negative. The wait gate is the
answer — poll the count query until the events are visible. The
honest-failure contract is the important part: on timeout the function
returns `False` and the *caller proceeds anyway*, scoring the blue response
as synthetic-fallback indeterminate rather than pretending the query was
valid. A gate that lied and reported success on a timeout would fabricate a
clean detection run.

## Interfaces

`wait_indexed(host, since_epoch, expect_min, timeout_s, index)` returns `True`
once the count query sees the expected minimum, `False` on timeout. The
caller decides what a `False` means for its own scoring.

## Gotchas

The search reuses the export endpoint with oneshot execution, so each poll is
a full query round-trip — the two-second sleep between polls bounds how hard
the gate hammers the lab.

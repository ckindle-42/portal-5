---
id: unit-surface-siem
kind: mixed
title: "Security SIEM subpackage \u2014 Splunk integration boundary"
sources:
- type: code
  path: portal/modules/security/core/siem/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785884200.0
updated_at: 1785884200.0
---

The `siem` subpackage is the Splunk integration boundary for the bench: HEC ships telemetry in, queries run as oneshot exports, detections resolve from a declarative SPL library, and a `blue_triage` loop polls, enriches, and reports alerts.

## Why

Splunk ingests asynchronously and stamps ship time, so the shipper overrides the event time and the `index_wait` gate polls a count search until telemetry is queryable. The gate's honest-failure contract is load-bearing: on timeout it returns `False` and the caller proceeds, scoring synthetic-fallback indeterminate rather than fabricating a clean run. Oneshot export skips the create-job-and-poll cycle, and the host-field priority order absorbs Windows versus Linux host naming. The blue-triage loop exists because a detection bench is not a live SOC; it replaced the dead Talon agent and writes to the local store only. Detections stay declarative and lazily loaded in YAML, with `[DISTINGUISH:` and `[KEY:` markers so an operator edits data, not Python.

## Interfaces

`hec_ship` exposes `ship` and `ship_batch` for the HEC envelope; `SplunkBackend` implements the `TelemetryBackend` protocol with `query`, `query_episode`, and `query_freeform`; `wait_indexed` gates searchability; `spl_for` and `technique_reference` serve the detection library; the `blue_triage` loop runs `poll_alerts`, `enrich_alert`, `report_triage`, and `run_triage_loop`.

## Gotchas

HEC auth is `Splunk <token>` on the collector endpoint, unlike the REST basic auth used for queries. `verify=False` trusts the lab Splunk self-signed certificate unconditionally; never point it at production. Triage severity is LLM-derived, not ground truth.

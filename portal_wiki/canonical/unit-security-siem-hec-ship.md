---
id: unit-security-siem-hec-ship
kind: mixed
title: "SIEM HEC shipper \u2014 telemetry ingestion to Splunk"
sources:
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
  commit: b6f05201
last_generated_commit: b6f05201
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785796625.259786
updated_at: 1785796625.259786
---

`hec_ship.py` ships lab telemetry to Splunk's HTTP Event Collector: each
event is wrapped in the HEC envelope (time, host, source, sourcetype, index)
and POSTed to `/services/collector/event` with a Splunk token.

## Why

The telemetry the red team produces in the lab only becomes *evidence* when it
lands in the SIEM on the right timeline. The `event_time` override is the
subtle piece: an attack that happened at 14:00 and was shipped at 14:10 must
carry the 14:00 timestamp so the detection queries see it where it belongs,
not at the arbitrary moment of ingestion. The env-driven URL, token, and index
configuration keep the lab wiring out of the code — an operator points the
shipper at a lab without editing anything.

## Interfaces

`ship(event, ...)` posts one event with the HEC envelope and returns an ok/code
result; `ship_batch` does the same for a list, so a bench run can flush a
whole attack episode with one call. `dry_run` skips the actual POST.

## Gotchas

The token is `Splunk <token>` auth on the collector endpoint, distinct from
the REST-API basic auth used by the query backend — the two are not
interchangeable even though both talk to the same Splunk.

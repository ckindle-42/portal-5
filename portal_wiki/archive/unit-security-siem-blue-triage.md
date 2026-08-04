---
id: unit-security-siem-blue-triage
kind: mixed
title: "SIEM blue-triage loop \u2014 poll, enrich, P1-P4 report"
sources:
- type: code
  path: portal/modules/security/core/siem/blue_triage.py
  commit: b6f05201
last_generated_commit: b6f05201
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- siem
created_at: 1785796642.482094
updated_at: 1785796642.482094
---

`blue_triage.py` is the blue-triage loop: it polls the SIEM for alerts,
enriches them via the LLM, and produces P1–P4 severity reports. It replaces
the dead Talon SOC agent with Portal 5's own harness and writes to the local
store only — no CoPilot coupling.

## Why

The loop exists because a detection bench is not a live SOC: the blue team's
job is to prove it can see, prioritise, and explain real alerts in the lab
SIEM, and that requires an automated triage that polls, enriches, and reports
instead of a human watching the dashboard. The "replaces the dead Talon SOC
agent" note is the design memory — an earlier external integration was
retired, and this harness is the local replacement that keeps the evaluation
self-contained. Writing to the local store only is the boundary that keeps
the bench from depending on an external analyst tool.

## Interfaces

`poll_alerts` fetches recent alerts from the SIEM; `enrich_alert` passes an
alert through the LLM to add context; `report_triage` renders the P1–P4
categorisation to a file; `run_triage_loop` drives the cycle.

## Gotchas

The severity categorisation (P1–P4) is a product of the LLM enrichment, not
a rule on raw fields — so the loop's output quality depends on the model
doing the categorisation consistently, and the report should be read as
analyst input, not ground truth.

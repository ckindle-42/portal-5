---
id: unit-claude-4-the-pipeline-is-stateless-with-metrics-persisten
historical: true
kind: why
title: "CLAUDE.md \u2014 4 \u2014 The Pipeline Is Stateless (with metrics persistence)"
sources:
- type: design
  path: CLAUDE.md
  section: "4 \u2014 The Pipeline Is Stateless (with metrics persistence)"
confidence: high
tags:
- claude
- architecture
- law

---


`portal/platform/inference/router_pipe.py` (facade for `portal/platform/inference/router/app.py`'s `app`) is stateless for conversation routing — no database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

The pipeline does persist operational metrics (request counts, TPS, errors) to `/app/data/metrics_state.json` for telemetry only — it does not affect routing decisions.

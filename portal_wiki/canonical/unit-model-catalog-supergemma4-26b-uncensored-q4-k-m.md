---
id: unit-model-catalog-supergemma4-26b-uncensored-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `supergemma4-26b-uncensored:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.632792
updated_at: 1784946220.632792
---

`supergemma4-26b-uncensored:Q4_K_M` is the abliterated SuperGemma4 26B A4B MoE. `config/backends.yaml` registers it in three groups — `general` (`ollama-general`), `security` (`ollama-security`), and `reasoning` (`ollama-reasoning`) — and every entry carries `supports_tools: false`. The config comments state the reason: the model is wired to driver-dispatched workspaces and empirically enters a reasoning loop when given tool definitions, so its output is parsed and dispatched by the driver rather than emitted as native tool calls. `config/portal.yaml` pins the derived `-ctx64k` tag on the auto-security redteam-deep and purpleteam-exec variants; `bench-supergemma4-sec` (whose `model_hint` is the base tag) records a completed 2026-06-17 bench at avg 0.783 with zero disclaimers and its promotion as auto-redteam-deep primary.

## Why

This unit's earlier "tool-use capable" and "bench eval pending" claims were both contradicted by the config: every group entry marks the model non-tool-calling, and the bench workspace records a finished bench and a promotion, not a pending one. Restating the flags, the driver-dispatched rationale, and the recorded bench outcome grounds the model's real role: a high-coverage red-team writer whose outputs are dispatched by a driver, never via native tools.

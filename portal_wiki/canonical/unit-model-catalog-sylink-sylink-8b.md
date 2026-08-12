---
id: unit-model-catalog-sylink-sylink-8b
kind: what
title: "MODEL_CATALOG \u2014 `sylink/sylink:8b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.617931
updated_at: 1784946220.617931
---

`sylink/sylink:8b` is an 8B security-domain model registered in `config/backends.yaml` under `group: general` (`ollama-general`) and `group: security` (`ollama-security`), both `supports_tools: false` — it does not emit native tool calls. `config/portal.yaml` documents its arc in two eval workspaces: `bench-sylink-8b` frames it as a GATE-D ablation candidate, and `bench-sylink` records the 2026-06-16 red-team bench (avg 0.311, correctly retired from offensive lanes) and the 2026-06-21 promotion to auto-blueteam primary on a 1.00/1.00 chain at depth 12, the deepest 8B in the fleet. The current auto-security `blueteam` workspace description now names it the previous model, switched to `granite4.1:8b` for autonomous tool-calling investigation capability.

## Why

The promotion recorded in `bench-sylink` is easy to misread as the current state, but the live `blueteam` workspace documents a later switch to `granite4.1:8b` precisely because sylink does not call tools. Both the bench-sylink promotion and the blueteam supersession are config-recorded, so this unit cites both; the model's real status is historical primary, not current.

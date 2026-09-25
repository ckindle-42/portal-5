---
id: unit-known-limitations-unregistered-hint-fallback
kind: what
title: Unregistered model_hint Served a Different Model (Resolved; gated)
sources:
- type: code
  path: portal/platform/inference/router/streaming.py
- type: code
  path: tests/wfe/settings_audit.py
- type: code
  path: tests/uat/settings_gate.py
claims: []
confidence: high
tags:
- known-limitations
- routing
- resolved
created_at: 1790333591
updated_at: 1790333591
---

- **ID**: P5-HINT-FALLBACK-001
- **Status**: RESOLVED 2026-09-25 — both seats re-registered; the class is now a FAIL in the settings auditor and a UAT gate.
- **Description**: When no backend in a workspace's routing groups resolves its `model_hint`, the router serves `backend.models[0]` and only logs a warning. `auto-coding::fast-repair` (kat-coder) and `auto-coding::uncensored-fast` (orcarouter Qwen3.8) hinted `-ctx32k` tags registered nowhere, so both were served Qwen3.6-35B HauhauCS from `omlx-creative`. The settings auditor had never walked variants, so it could not see it.
- **Guard**: `tests/wfe/settings_audit.py` audits every workspace and variant and raises `hint_unroutable` using production's own `BackendRegistry.resolve_model` over the seat's routing groups; `tests/uat/settings_gate.py` refuses to start a UAT while any production seat is unroutable or absent.

## Why

A seat that silently serves another model makes every measurement of that seat — UAT, WFE, user feedback — describe the wrong model. Making the check mechanical is the only defence, because the router's fallback is designed to keep traffic flowing rather than fail.

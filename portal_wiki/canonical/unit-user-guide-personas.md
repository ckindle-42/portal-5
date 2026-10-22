---
id: unit-user-guide-personas
kind: what
title: "USER_GUIDE \u2014 Personas"
sources:
- type: code
  path: config/personas
- type: code
  path: scripts/openwebui_init.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.514347
updated_at: 1784946220.514347
---

Personas are pre-configured specialists defined one-per-file under
`config/personas/`. Each YAML carries a `name`, `slug`, `category`, a
`workspace_model` that routes the persona to a workspace (for example
`auto-security` or `auto-coding`), and an optional `variant` naming the workspace
variant whose model, sampling and tool grants the specialist claims. `delivery`
decides how seeding publishes it: a `persona` (the default) becomes an Open WebUI
model preset in the same dropdown as workspaces, while a `role` becomes a `/slug`
prompt in Open WebUI's prompt library and selects its variant only when that
role's `workspace_model` is the routed engine. Examples include `Cyber Security
Specialist`, `Red Team Operator`, and `Python Code Generator`. A persona's system
prompt comes from the YAML's inline `system_prompt` or a shared `prompt_template`
body. The pipeline applies that same text when the request model is the persona
slug, and applies a role's text when a request opens with its `/slug` token, so
an API caller receives it without relying on the Open WebUI preset.

## Why

The generated guide treated personas as if they were a frontend concept, but they
are declarative artifacts: one YAML file per specialist. Seeding publishes either
the Open WebUI preset or the role prompt, and the pipeline applies the same prompt
when the request model is the persona slug. Grounding to `config/personas/` and
`openwebui_init.py` keeps the unit aligned with how a new persona is actually
added, and explains why a preset's name mirrors the YAML `name` field while a role
is invoked by its slug.

---
id: unit-user-guide-personas
kind: what
title: "USER_GUIDE \u2014 Personas"
sources:
- type: code
  path: config/personas
- type: code
  path: scripts/openwebui_init.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.514347
updated_at: 1784946220.514347
---

Personas are pre-configured specialists defined one-per-file under
`config/personas/`. Each YAML carries a `name`, `slug`, `category`, and a
`workspace_model` that routes the persona to a workspace (for example
`auto-security` or `auto-coding`). The bootstrap script reads every persona file
and creates an Open WebUI model preset for it, so personas appear in the same
model dropdown as workspaces. Examples include `Cyber Security Specialist`,
`Red Team Operator`, and `Python Code Generator`. A persona's system prompt comes
from the YAML's inline `system_prompt` or a shared `prompt_template` body.

## Why

The generated guide treated personas as if they were a frontend concept, but they
are declarative artifacts: one YAML file per specialist, resolved to presets only
by the seeding script. Grounding to `config/personas/` and `openwebui_init.py`
keeps the unit aligned with how a new persona is actually added, and explains why
persona names in the dropdown always mirror the YAML `name` field.

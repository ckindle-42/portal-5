---
id: unit-mcp-dev-tooling-auto-coding-workspace-laguna-variant
kind: what
title: "MCP_DEV_TOOLING \u2014 `auto-coding` Workspace \u2014 `laguna` Variant"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/config.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/preinject.py
- type: code
  path: config/backends.yaml
- type: code
  path: config/personas/codingagentic.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5778859
updated_at: 1784946220.5778859
---

The `laguna` variant of the `auto-coding` workspace is the default agentic coding lane
for opencode and Claude Code. It marks `client_tools_only: true`: when a request carries
client tools, the handler reuses `portal_client_tools_only` so the model sees only those
schemas and skips `system_prompt_append`. Tool-less requests keep the workspace tools and
prompt. `config/portal.yaml` pins its `model_hint` to
`portal5/laguna-xs21:q4_K_M-ctx128k` (Laguna-XS-2.1), sets `keep_alive` to 15 minutes and
`context_limit` to 131072, and attaches a `system_prompt_append` for the pipeline tool loop:
explore with `explore_repository`, read with `read_text_file`, plan, edit with `write_file`,
verify with `execute_bash` running pytest, then report. `config/backends.yaml` registers that tag as the Ollama fallback and aliases it, in
the `omlx-coding` entry (priority 10), to `Laguna-XS-2.1-4bit` on oMLX, which serves
the seat, and the `codingagentic`
persona in `config/personas/codingagentic.yaml` binds this variant for the IDE
picker with `ide_expose` enabled.

## Why

The pipeline tool loop remains useful for requests without client tools. IDE turns
bring their own tools and need instructions that match the schemas they actually see;
the persona indirection keeps the picker address stable while the workspace controls
when its own tool loop applies.

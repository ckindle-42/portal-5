---
id: unit-mcp-dev-tooling-auto-coding-workspace-laguna-variant
kind: what
title: "MCP_DEV_TOOLING \u2014 `auto-coding` Workspace \u2014 `laguna` Variant"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: config/personas/codingagentic.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5778859
updated_at: 1784946220.5778859
---

The `laguna` variant of the `auto-coding` workspace is the default agentic coding lane
for opencode and Claude Code. `config/portal.yaml` pins its `model_hint` to
`laguna-xs.2:Q4_K_M-ctx64k`, sets `keep_alive` to 15 minutes and `context_limit` to
65536, and attaches a `system_prompt_append` that encodes the agentic loop: explore
with `explore_repository`, read with `read_text_file`, plan, edit with `write_file`,
verify with `execute_bash` running pytest, then report. The backing model id
`laguna-xs.2:Q4_K_M` is registered in `config/backends.yaml`, and the `codingagentic`
persona in `config/personas/codingagentic.yaml` binds this variant for the IDE
picker with `ide_expose` enabled.

## Why

A coding model is only as good as the loop it is told to run. Encoding read, plan,
edit, verify directly in the system prompt removes the guesswork about which tools
exist and which order to call them, and the persona indirection lets the picker
address the variant by a stable name rather than by an implementation detail of the
workspace config.

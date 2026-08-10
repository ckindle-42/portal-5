---
id: unit-mcp-dev-tooling-workspace-selection
kind: what
title: "MCP_DEV_TOOLING \u2014 Workspace selection"
sources:
- type: code
  path: opencode.jsonc
- type: code
  path: config/portal.yaml
- type: code
  path: config/personas/codingagentic.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5750148
updated_at: 1784946220.5750148
---

opencode selects a model with `--model portal/<key>`, where the key is a base
workspace id or a curated persona slug from the `models` block in `opencode.jsonc`.
The default is `portal/codingagentic`, the Laguna agentic persona. Other curated
options include `agenticheavy` for long-horizon multi-file work, `agenticlite` for a
lighter load, `auto-coding` for one-shot generation, `auto-reasoning` for deep
reasoning, `auto-security` for defensive review, and the pentest-focused
`pentestlead` and `purpleteamexec`. The picker is keyed on the post-closeout persona
slugs — the retired alias ids no longer resolve. `opencode models` lists everything
advertised by `GET /v1/models` for full discovery.

## Why

Model choice is a routing decision, not an aesthetic one: the coding tasks split
across agentic loop, one-shot generation, and long-horizon refactor, and each
workspace is tuned for one of them. Exposing the curated subset as named personas
keeps the picker legible while the full catalog stays reachable through discovery,
which is why the keys must match the pipeline's advertised ids exactly.

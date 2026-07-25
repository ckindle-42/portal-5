---
id: unit-mcp-dev-tooling-what-opencode-gets
kind: what
title: "MCP_DEV_TOOLING \u2014 What opencode gets"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: What opencode gets
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.573175
updated_at: 1784946220.573175
---

- **Fully local inference** — all completions go through portal-pipeline (:9099) to Ollama
  on your hardware. No tokens leave the machine.
- **All workspaces + curated personas as models** — `GET /v1/models` (and `opencode models`)
  lists every base workspace plus every `ide_expose: true` persona
  (`python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`
  for the current workspace total). `opencode.jsonc`'s curated picker is a fixed 20-entry
  subset: 9 bare base-workspace ids + 11 persona slugs. Default: `portal/codingagentic`
  (persona binding `auto-coding` + `variant: laguna`) — a persona is the friendly named
  binding of (workspace + variant); see `CLOSEOUT_ALIAS_REMOVAL.md` /
  `DESIGN_OPENCODE_ADDRESSING_V1.md` for why variants are addressed by persona slug rather
  than a `base::variant` string in this human-facing picker.
- **All MCP servers** — opencode reads `.mcp.json` automatically, so it has the same
  filesystem, git, docker, sandbox, pipeline, and every other portal-* tool server — currently
  22 total (`python3 -c "import json; print(len(json.load(open('.mcp.json'))['mcpServers']))"`).
- **Cloud providers disabled** — `anthropic`, `openai`, `google`, `bedrock`, `vertex` are
  all disabled to prevent accidental cloud use.

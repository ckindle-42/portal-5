---
id: unit-mcp-dev-tooling-3-launch-opencode-reads-opencode-jsonc-mcp-json-automatically
kind: what
title: "MCP_DEV_TOOLING \u2014 3. Launch opencode (reads opencode.jsonc + .mcp.json\
  \ automatically)"
sources:
- type: code
  path: opencode.jsonc
- type: code
  path: scripts/oc-portal.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.57464
updated_at: 1784946220.57464
---

Opening the repo with bare `opencode .` picks up `opencode.jsonc` at the root, which
carries the whole IDE integration: the `portal` provider block (base URL
:9099/v1), the `env` list for `PIPELINE_API_KEY`, a cloud-provider guard,
the default model, and a dedicated `mcp` block of remote HTTP tool servers. Note that
opencode reads the `mcp` roster from `opencode.jsonc`, not from `.mcp.json` — the
latter is the Claude Code file. `scripts/oc-portal.sh` is the explicit wrapper that
sets the key and launches opencode from the repo root.

## Why

opencode merges configuration by working directory and has no strict-MCP bypass, so
the project's behaviour has to be declared in the project's own config file. Keeping
the provider, the key plumbing, and the MCP roster together in `opencode.jsonc` makes
a bare launch from the repo root fully local without any shell incantation.

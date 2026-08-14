---
id: unit-mcp-dev-tooling-quick-start
kind: what
title: "MCP_DEV_TOOLING \u2014 Quick start"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/cc-local.sh
- type: code
  path: scripts/oc-portal.sh
- type: code
  path: opencode.jsonc
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5735328
updated_at: 1784946220.5735328
---

The quick start is three steps. First bring the stack up with `./launch.sh up`, which
starts the compose services and the host-native pipeline MCP. Second, make sure
`PIPELINE_API_KEY` is exported — the wrapper scripts do this automatically, and
`opencode.jsonc` declares it for opencode. Third, open the repo: `opencode .` for the
local-pipeline client, or `claude` via one of `scripts/cc-portal.sh`,
`scripts/cc-local.sh`, or `scripts/cc-stock.sh` depending on whether the intelligence
should be cloud, local, or stock.

## Why

A quick start exists to make the zero-setup claim testable: if these three steps do
not produce a working local session, the integration is broken. Each step maps to a
concrete file or command — `launch.sh`, the key plumbing, and the per-client entry
point — so the check stays mechanical instead of depending on tribal knowledge.

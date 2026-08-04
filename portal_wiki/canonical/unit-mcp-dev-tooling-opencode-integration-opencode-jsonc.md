---
id: unit-mcp-dev-tooling-opencode-integration-opencode-jsonc
kind: what
title: "MCP_DEV_TOOLING \u2014 opencode Integration (`opencode.jsonc`)"
sources:
- type: code
  path: opencode.jsonc
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.572661
updated_at: 1784946220.572661
---

`opencode.jsonc` at the repo root tells opencode to use Portal 5 as its AI backend
instead of a cloud API. It declares a `portal` provider using the OpenAI wire format
with a base URL of :9099/v1, lists `PIPELINE_API_KEY` in the provider `env` block so the
key is passed as the bearer token, disables the built-in cloud providers, sets the
default model to `portal/codingagentic`, and carries an `mcp` block of remote HTTP
tool servers. Together these make a bare `opencode .` from the repo root a fully
local session.

## Why

opencode discovers configuration by working directory, so the project must assert
its own provider, key plumbing, and MCP roster or the client falls back to whatever
global config exists — potentially a cloud provider. Centralising the local
integration in one committed file makes the local-first posture the default for
anyone opening the repo.

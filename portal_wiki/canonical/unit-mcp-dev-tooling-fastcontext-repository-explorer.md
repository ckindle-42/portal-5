---
id: unit-mcp-dev-tooling-fastcontext-repository-explorer
kind: what
title: "MCP_DEV_TOOLING \u2014 FastContext Repository Explorer"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.572334
updated_at: 1784946220.572334
---

`explore_repository` in `portal/platform/mcp_host/pipeline_mcp.py` runs the
FastContext model (`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`) as a
dedicated repository-exploration subagent. It issues parallel READ, GLOB, and GREP
tool calls across the repo, bounded by a default of six turns, and returns compact
citations carrying path plus line ranges. If the model has not been pulled into
Ollama the tool returns an explicit error telling the caller to run
`ollama pull` on the exact model name before retrying.

## Why

FastContext exists to stop the main coding model from burning its context window
scanning the tree. A small specialist that only finds files and line ranges keeps
the expensive reasoning model focused on the change itself, and the citation format
means the returned paths are directly actionable instead of being vague hints about
where something might live.

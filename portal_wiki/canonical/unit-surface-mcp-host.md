---
id: unit-surface-mcp-host
kind: mixed
title: "MCP host \u2014 shared workspace paths and pipeline introspection server"
sources:
- type: code
  path: portal/platform/mcp_host/*.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- authored-v1
- platform
- mcp-host
created_at: 1785886400.0
updated_at: 1785886400.0
---

The `mcp_host` package is the shared core of the MCP fleet, holding two contracts every server depends on. The workspace helpers resolve the one user-file root, with `uploads/` and `generated/<category>/` beneath it, across the container and host worlds so a Docker MCP and a host-native service see the same tree. The pipeline MCP (`pipeline_mcp`, port 8928) is separate: a host-native server that gives Claude Code and opencode a live read on the stack.

## Why

The two contracts defend against failures that would otherwise degrade the fleet. Centralizing path resolution makes a future remap of the shared root one configuration change, and the traversal and SSRF guards exist because these helpers receive LLM-controlled tool arguments a prompt injection could steer. The introspection server's zero-import rule keeps coding tools from pulling the inference tier into their process and forces every datum from the pipeline's own HTTP endpoints rather than private functions, so the surface cannot silently drift from what it reports.

## Interfaces

The workspace contract resolves the root in order `WORKSPACE_DIR`, `AI_OUTPUT_DIR`, `/workspace`, then `~/AI_Output`; `get_workspace_root`, `get_uploads_dir`, and `get_generated_dir` materialize paths under the `_VALID_CATEGORIES` whitelist while `resolve_upload_path` and `assert_public_http_url` gate untrusted inputs. The introspection server exposes `get_pipeline_status`, `list_workspaces`, `get_loaded_models`, `get_metrics_summary`, `get_workspace_recommendation`, `explore_repository`, and `trigger_backend_warmup`, with `_resolve_path` plus `_check_read_allowed` bounding every file read.

## Gotchas

`get_uploads_dir` and `get_generated_dir` create their directories as a side effect, not pure readers. `resolve_upload_path` reduces its argument to a bare filename before any lookup. `assert_public_http_url` checks only the request URL, never redirect targets. The introspection server's read allowlist is anchored on `PIPELINE_MCP_REPO_ROOT`; writes are restricted further.

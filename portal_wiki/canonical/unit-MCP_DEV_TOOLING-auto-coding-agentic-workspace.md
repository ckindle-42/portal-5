---
id: unit-MCP_DEV_TOOLING-auto-coding-agentic-workspace
kind: why
title: "MCP_DEV_TOOLING \u2014 `auto-coding-agentic` Workspace"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: '`auto-coding-agentic` Workspace'
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.873736
updated_at: 1783195000.873736
---


Built specifically for Portal 5 self-improvement work. Available in Open WebUI and via opencode.

| Property | Value |
|---|---|
| **Model** | `laguna-xs.2:Q4_K_M` — Poolside AI 33B-A3B MoE, 68.2% SWE-bench Verified (~19 GB) |
| **Keep alive** | 15 min |
| **First tool** | `explore_repository` — FastContext finds exact files/lines before any edit |
| **Other tools** | `execute_bash`, `execute_python`, `execute_nodejs`, `sandbox_status`, file readers, memory |

**Agentic loop baked into system prompt:**

1. `explore_repository` — FastContext locates the relevant files and line ranges
2. `execute_bash cat -n` — read only the targeted ranges
3. State the minimal change needed and which files are affected
4. Make precise, targeted edits
5. `execute_bash pytest tests/unit/ -q` — verify before reporting done
6. Report what changed, what passed, what remains

---

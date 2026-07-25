---
id: unit-mcp-dev-tooling-auto-coding-workspace-laguna-variant
kind: what
title: "MCP_DEV_TOOLING \u2014 `auto-coding` Workspace \u2014 `laguna` Variant"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: "`auto-coding` Workspace \u2014 `laguna` Variant"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5778859
updated_at: 1784946220.5778859
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

---
id: unit-HOWTO-compatible-tools
kind: why
title: "HOWTO \u2014 Compatible tools"
sources:
- type: design
  path: docs/HOWTO.md
  section: Compatible tools
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.862404
updated_at: 1783195000.862404
---


Any tool with a configurable OpenAI API base URL works out-of-the-box:

| Tool | Setting | Value |
|------|---------|-------|
| **Continue.dev** (VS Code/JetBrains) | `apiBase` | `http://localhost:9099/v1` |
| **Cursor** | Custom model → Base URL | `http://localhost:9099/v1` |
| **Aider** | `--openai-api-base` | `http://localhost:9099/v1` |
| **LM Studio** (client mode) | API Base URL | `http://localhost:9099/v1` |
| **Jan** | OpenAI-compatible server | `http://localhost:9099/v1` |
| **Shell scripts** | `curl` with `-H "Authorization: Bearer ..."` | see examples above |
| **Python scripts** | `openai.OpenAI(base_url=...)` | see example above |

**Model selection:** Use any workspace ID (`auto`, `auto-coding`, `auto-security`, etc.) or any persona slug (`redteamoperator`, `magistralstrategist`, etc.) as the `model` field. The pipeline routes to the appropriate backend automatically.

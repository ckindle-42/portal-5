---
id: unit-BACKUP_RESTORE-what-to-back-up
kind: why
title: "BACKUP_RESTORE \u2014 What to Back Up"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: What to Back Up
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.821672
updated_at: 1783195000.821672
---


| Component | Volume | Critical? | Notes |
|-----------|--------|-----------|-------|
| Open WebUI data | `portal-5_open-webui-data` | YES | Users, chat history, settings, workspaces |
| Ollama models | `portal-5_ollama-models` | NO | Can be re-downloaded, large (10-100GB) |
| Configuration | `config/` | YES | backends.yaml, personas/ (if customized) |
| Environment | `.env` | YES | Secrets, API keys |
| MCP data | `portal-5_mcp-data` | MAYBE | Generated documents, if any |

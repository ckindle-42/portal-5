---
id: unit-backup-restore-what-to-back-up
kind: what
title: "BACKUP_RESTORE \u2014 What to Back Up"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: What to Back Up
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.523835
updated_at: 1784946220.523835
---

| Component | Volume | Critical? | Notes |
|-----------|--------|-----------|-------|
| Open WebUI data | `portal-5_open-webui-data` | YES | Users, chat history, settings, workspaces |
| Ollama models | `portal-5_ollama-models` | NO | Can be re-downloaded, large (10-100GB) |
| Configuration | `config/` | YES | backends.yaml, personas/ (if customized) |
| Environment | `.env` | YES | Secrets, API keys |
| Generated artifacts | `${AI_OUTPUT_DIR:-~/AI_Output}` (host dir, mounted `/workspace`) | MAYBE | Uploads + generated docs/images/videos/music/speech, if any (CLAUDE.md Rule 11) |

---
id: unit-ADMIN_GUIDE-backup
kind: why
title: "ADMIN_GUIDE \u2014 Backup"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Backup
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.814406
updated_at: 1783195000.814406
---


Critical data is in Docker volumes:
- `portal-5_open-webui-data` — all user accounts, chat history, settings
- `portal-5_ollama-models` — downloaded model weights (replaceable, not personal data)

```bash

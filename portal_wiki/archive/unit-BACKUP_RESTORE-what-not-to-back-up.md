---
id: unit-BACKUP_RESTORE-what-not-to-back-up
kind: why
title: "BACKUP_RESTORE \u2014 What NOT to Back Up"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: What NOT to Back Up
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.825875
updated_at: 1783195000.825875
---


- `ollama-models` volume — can be 50-100GB, easily re-downloaded
- Docker images — can be rebuilt with `docker compose build`
- `.venv/` — rebuild with `uv pip install -e ".[dev]"`

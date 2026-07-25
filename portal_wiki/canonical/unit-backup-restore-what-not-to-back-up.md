---
id: unit-backup-restore-what-not-to-back-up
kind: what
title: "BACKUP_RESTORE \u2014 What NOT to Back Up"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: What NOT to Back Up
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.53501
updated_at: 1784946220.53501
---

- `ollama-models` volume — can be 50-100GB, easily re-downloaded
- Docker images — can be rebuilt with `docker compose build`
- `.venv/` — rebuild with `uv pip install -e ".[dev]"`

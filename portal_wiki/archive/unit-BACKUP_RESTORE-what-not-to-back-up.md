---
id: unit-BACKUP_RESTORE-what-not-to-back-up
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 What NOT to Back Up"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: What NOT to Back Up
confidence: high
tags:
- docs
- BACKUP_RESTORE

---


- `ollama-models` volume — can be 50-100GB, easily re-downloaded
- Docker images — can be rebuilt with `docker compose build`
- `.venv/` — rebuild with `uv pip install -e ".[dev]"`

---
id: unit-backup-restore-what-not-to-back-up
kind: what
title: "BACKUP_RESTORE \u2014 What NOT to Back Up"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.53501
updated_at: 1784946220.53501
---

Three artifact classes are intentionally outside the backup surface. The `portal-5_ollama-models` volume is excluded because weights are re-downloadable through `./launch.sh pull-models`. Docker images are excluded because they are rebuilt from the Dockerfiles via `./launch.sh rebuild`. The local Python environment is excluded because `uv pip install -e ".[dev]"` reproduces it from `pyproject.toml` and the lockfile. All three would multiply snapshot size for zero recovery value.

## Why

A backup's value is bounded by how much it speeds recovery of state that cannot otherwise be reproduced; weights, images, and virtual environments are all deterministic outputs of inputs already under version control. Excluding them keeps snapshots small and makes the restore contract honest about what the backup actually guarantees.

---
id: unit-backup-restore-portal-6-0-0-backup-restore-guide
kind: what
title: "BACKUP_RESTORE \u2014 Portal 6.0.0 \u2014 Backup & Restore Guide"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: pyproject.toml
last_generated_commit: 5ac2ba7ee3849ad2062c91edccece2a495f18da5
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.523464
updated_at: 1784946220.523464
---

This unit family documents the backup and restore surface of the platform: the `backup` and `restore` commands in `launch.sh` backed by `scripts/lib/backup.sh`. The guide header that named the version predates the current release, which is version 8.0.0 per `pyproject.toml`, but the operational surface it describes is the same two commands still wired today. The script covers the Open WebUI and Grafana volumes, `.env`, `config/`, and `imports/`.

## Why

The version label in the original guide is a snapshot artifact rather than a semantic statement about the backup code, which is why re-grounding ties these units to the actual script instead of to the dated document. Version-named documentation drifts as releases land; source-anchored units do not.

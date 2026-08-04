---
id: unit-backup-restore-migration-to-new-host
kind: what
title: "BACKUP_RESTORE \u2014 Migration to New Host"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5346
updated_at: 1784946220.5346
---

Migration uses the same two commands as recovery: on the source host run `./launch.sh backup` to produce a timestamped snapshot, transfer that directory to the new machine, then on the target run `./launch.sh restore <path>`. The target must have `.env` present; `./launch.sh up` copies `.env.example` to `.env` when the file is missing, but restoring the saved `.env` preserves secrets and routing. The restored volumes and config become live once `./launch.sh up` recreates the compose project's containers.

## Why

Reusing the restore command for migration means the data format between hosts is identical to the recovery format — there is no separate migration artifact to generate or misplace. Because compose recreates the named volumes on first `up`, the operator does not need to pre-create them; restore populates them before the stack starts.

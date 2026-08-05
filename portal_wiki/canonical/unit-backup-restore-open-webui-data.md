---
id: unit-backup-restore-open-webui-data
kind: what
title: "BACKUP_RESTORE \u2014 Open WebUI data"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5280042
updated_at: 1784946220.5280042
---

The Open WebUI service in `deploy/portal-5/docker-compose.yml` mounts the named volume `open-webui-data` at `/app/backend/data`, and the project prefix turns that into `portal-5_open-webui-data` at the Docker level. The backup and restore functions reference the prefixed name directly so the alpine helper container can mount it. The volume survives `docker compose down` and is only destroyed by an explicit `clean` or `clean-all`, which is why the backup flow has to snapshot it separately.

## Why

Pinpointing the exact volume name matters because the backup script mounts it by literal name; a renamed or re-prefixed volume silently breaks both directions of the flow. Documenting that the prefix derives from the `deploy/portal-5` compose directory explains why the name is what it is, rather than being an arbitrary string in the script.

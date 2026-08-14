---
id: unit-backup-restore-what-to-back-up
kind: what
title: "BACKUP_RESTORE \u2014 What to Back Up"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.523835
updated_at: 1784946220.523835
---

The backup command's artifact set is fixed and covers four things: the `portal-5_open-webui-data` volume with users and chat history, the `portal-5_grafana-data` volume with dashboards and datasources, the `.env` secrets file, and the `config/` plus `imports/` trees. Excluded by design are the `portal-5_ollama-models` weights volume and the host workspace at `${AI_OUTPUT_DIR}`, the latter being recoverable only by manual archive. This is the complete inventory; nothing outside it is snapshotted.

## Why

Publishing the exact inclusion and exclusion set prevents the two failure modes that plague backup systems: assuming a component is covered when it is not, and carrying re-downloadable bulk that slows every run. The list is derived from the literal artifact sequence in `_launch_backup`, so it stays truthful as long as the script does not change.

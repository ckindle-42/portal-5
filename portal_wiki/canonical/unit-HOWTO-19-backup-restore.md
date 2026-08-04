---
id: unit-HOWTO-19-backup-restore
kind: what
title: HOWTO -- 19. Backup & Restore
sources:
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1784944767.916967
updated_at: 1784944767.916967
---

Backup and restore are implemented in `scripts/lib/backup.sh`.

```bash
./launch.sh backup                # Save all data to ./backups/ (or pass an output dir)
./launch.sh restore <backup-dir>  # Restore from a backup directory
```

`_launch_backup` creates a timestamped directory `portal5_backup_<timestamp>` under `./backups/` and fills it with `openwebui-data.tar.gz` (the Open WebUI data volume — users, chat history, settings), `grafana-data.tar.gz` (Grafana dashboards/datasources), a copy of `.env`, and copies of `config/` and `imports/`. `_launch_restore` prompts for confirmation, stops the stack, wipes and restores the two volumes from the tarballs, and copies `.env` back. Ollama model weights are NOT included — they live in the `ollama-models` volume, which neither backup nor restore touches; re-download them with `./launch.sh pull-models`.

## Why

Backup is scoped to small, generated state — OWUI data, Grafana, env, config — and deliberately excludes the large, reproducible Ollama weights that `pull-models` can always rebuild. A timestamped directory instead of a single tarball makes restores auditable and safe, and the confirmation prompt plus stack teardown in `_launch_restore` prevents restoring onto a live database.

---
id: unit-ADMIN_GUIDE-backup
kind: why
title: "ADMIN_GUIDE \u2014 Backup"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.814406
updated_at: 1783195000.814406
---

`./launch.sh backup [output-dir]` writes a timestamped directory (default under `./backups/`) via `_launch_backup` in scripts/lib/backup.sh. It tars the `portal-5_open-webui-data` volume into `openwebui-data.tar.gz` (accounts, chats, settings), tars `portal-5_grafana-data` into `grafana-data.tar.gz`, and copies `.env`, `config/`, and `imports/` alongside. Ollama weights in `portal-5_ollama-models` are intentionally excluded — they are re-pullable. `./launch.sh restore <path>` confirms interactively, stops the stack with a compose down, then restores the Open WebUI data, Grafana data, and `.env` from the same directory.

## Why

The backup is only as good as the volume inventory behind it. Personal data is confined to `open-webui-data` and `grafana-data` while model weights are disposable, so excluding `ollama-models` keeps backups small and deterministic. A directory-per-run layout plus a single `restore` argument makes recovery unambiguous and never touches `docker compose down -v`.

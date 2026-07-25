---
id: unit-HOWTO-19-backup-restore
kind: what
title: HOWTO -- 19. Backup & Restore
sources:
- type: doc
  path: docs/HOWTO.md
  commit: ddb1cc61
  section: 19. Backup & Restore
last_generated_commit: ddb1cc61
confidence: high
tags:
- docs
- HOWTO
created_at: 1784944767.916967
updated_at: 1784944767.916967
---

```bash
./launch.sh backup          # Save all data to ./backups/
./launch.sh restore <file>  # Restore from backup
```

Backup files are timestamped and include all Open WebUI data.
Ollama models are not included (re-downloadable via `./launch.sh pull-models`).

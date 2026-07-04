---
id: unit-HOWTO-data
kind: why
title: "HOWTO \u2014 Data"
sources:
- type: design
  path: docs/HOWTO.md
  section: Data
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.865555
updated_at: 1783195000.865555
---

./launch.sh backup          # Backup all data
./launch.sh restore <file>  # Restore from backup
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
./launch.sh clean           # Wipe Open WebUI data (keep models)
./launch.sh clean-all       # Wipe everything including models

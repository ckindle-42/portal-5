---
id: unit-HOWTO-data
historical: true
kind: why
title: "HOWTO \u2014 Data"
sources:
- type: design
  path: docs/HOWTO.md
  section: Data
confidence: high
tags:
- docs
- HOWTO

---

./launch.sh backup          # Backup all data
./launch.sh restore <file>  # Restore from backup
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
./launch.sh clean           # Wipe Open WebUI data (keep models)
./launch.sh clean-all       # Wipe everything including models

---
id: unit-ADMIN_GUIDE-routine-operations
kind: why
title: "ADMIN_GUIDE \u2014 Routine Operations"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Routine Operations
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8131342
updated_at: 1783195000.8131342
---


```bash
./launch.sh status      # Check service health
./launch.sh logs        # Pipeline logs (default)
./launch.sh logs ollama # Ollama logs
./launch.sh seed        # Re-seed workspaces/personas (after config changes)
./launch.sh down        # Stop all services (data preserved)
./launch.sh clean       # Wipe Open WebUI data (fresh start, Ollama models kept)
```

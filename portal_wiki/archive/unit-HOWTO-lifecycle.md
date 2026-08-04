---
id: unit-HOWTO-lifecycle
kind: why
title: "HOWTO \u2014 Lifecycle"
sources:
- type: design
  path: docs/HOWTO.md
  section: Lifecycle
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.864702
updated_at: 1783195000.864702
---

./launch.sh up              # Start everything
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Health check
./launch.sh logs [service]  # View logs
./launch.sh update          # Full update: git pull, Docker images, rebuilds, model refresh, re-seed
./launch.sh update --skip-models  # Update without model refresh (faster)
./launch.sh update --models-only  # Only refresh Ollama models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
./launch.sh prune           # Prune Docker resources

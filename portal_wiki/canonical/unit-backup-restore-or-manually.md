---
id: unit-backup-restore-or-manually
kind: what
title: "BACKUP_RESTORE \u2014 Or manually"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: portal/platform/inference/cli/_apps.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.53425
updated_at: 1784946220.53425
---

The manual model-recovery command suggested by the old guide, `docker exec ollama ollama pull`, no longer applies because the Ollama service sits behind the optional `docker-ollama` profile and the default runtime is host-native. The supported manual path is the CLI the `pull-models` case invokes, `python3 -m portal.platform.inference.cli models pull`, or a direct `ollama pull <model>` against the host's native Ollama on the default port.

## Why

The guide's docker-exec example assumes the containers-based runtime that is no longer the default, so following it on a host-native setup would fail with a missing container. Grounding the manual path in the actual CLI dispatch keeps recovery instructions aligned with how models are really pulled on this stack.

---
id: unit-backup-restore-pull-default-model
kind: what
title: "BACKUP_RESTORE \u2014 Pull default model"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: portal/platform/inference/config.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.533891
updated_at: 1784946220.533891
---

Repopulating the model catalog on a fresh or rebuilt host is a single command: `./launch.sh pull-models`, which maps to `portal.platform.inference.cli models pull`. That command reads the registry loaded from `config/backends.yaml` and pulls every configured model, using native `ollama pull` for registry models and the Python API plus `ollama create` for HuggingFace-sourced weights. It skips models already present in Ollama, so re-running is cheap and idempotent.

## Why

Driving re-pulls from the registry rather than a hardcoded list means recovery always converges to the currently configured catalog, including models added since the last backup. The existence check makes the command safe to run after a partial pull or after the weights volume is restored, avoiding redundant downloads.

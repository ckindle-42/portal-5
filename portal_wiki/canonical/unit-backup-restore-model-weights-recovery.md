---
id: unit-backup-restore-model-weights-recovery
kind: what
title: "BACKUP_RESTORE \u2014 Model Weights Recovery"
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
created_at: 1784946220.533393
updated_at: 1784946220.533393
---

Model weights live in the `portal-5_ollama-models` volume and are deliberately excluded from `./launch.sh backup`, which handles only the Open WebUI and Grafana volumes. The `clean-all` case removes the weights volume explicitly, while the `clean` case preserves it. Recovery is re-pulling: `./launch.sh pull-models` dispatches to `portal.platform.inference.cli models pull`, which walks the registry loaded from `config/backends.yaml` and issues native `ollama pull` commands for each configured model.

## Why

Weights are re-downloadable artifacts measured in tens of gigabytes, so backing them up would bloat every snapshot and slow every run for zero fidelity gain. The recovery loop is driven by the same registry that defines the model catalog, which means a rebuilt host converges to the configured model set without a manual inventory.

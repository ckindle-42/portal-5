---
id: unit-backup-restore-after-config-changes-re-seed
kind: what
title: "BACKUP_RESTORE \u2014 After config changes, re-seed"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/check_owui_preset_drift.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.531338
updated_at: 1784946220.531338
---

After restoring or hand-editing config, the Open WebUI presets must be reconciled with the files on disk. The `seed` case runs `docker compose run --rm openwebui-init`, and the init container skips presets that already exist, so reseeding is additive and non-destructive. The `reseed` case forces recreation by passing `FORCE_RESEED=true`, which deletes and recreates every preset, persona prompt, and workspace tool binding before applying config afresh.

## Why

Config files and the seeded Open WebUI database are two layers that can drift apart, and `seed` is the bridge that reconciles them. The skip-existing default protects a restored chat database from having its workspace presets clobbered on boot, while the explicit force flag hands the operator a deliberate, destructive path when a clean re-apply is actually wanted.

## Drift detection

Because `seed` skips existing presets, a workspace prompt, name or tool binding changed in `config/portal.yaml` and regenerated into `imports/openwebui/workspaces/` by `sync-config` does not reach the presets users chat with until `reseed`. `scripts/check_owui_preset_drift.py` compares each live preset (`/api/v1/models/model`) with its seeded file and names every difference; `sync-config` runs it and warns to run `./launch.sh reseed`. It is silent only when Open WebUI or its API key is unavailable. It covers the workspace presets, not persona prompts. It was added after an `auto-documents` prompt fix (1370cd64) was live in the pipeline's config but not in the preset Open WebUI sent.

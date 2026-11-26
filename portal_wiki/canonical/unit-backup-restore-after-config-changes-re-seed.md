---
id: unit-backup-restore-after-config-changes-re-seed
kind: what
title: "BACKUP_RESTORE \u2014 After config changes, re-seed"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/check_owui_preset_drift.py
claims:
- probe: repo.path.exists
  path: launch.sh
  equals: true
confidence: high
tags:
- verified-v1
---

After restoring or hand-editing config, the Open WebUI presets must be reconciled with the files on disk. The `seed` case runs `docker compose run --rm openwebui-init`, which updates presets Portal created in place (no delete). Chat history and the user's pins stay, and a preset that already matches is not written. The `reseed` case passes `FORCE_RESEED=true`, which deletes and recreates every Portal preset.

## Why

Config files and the seeded Open WebUI database are two layers that can drift apart, and `seed` is the bridge that reconciles them. The in-place update keeps a restored chat database's history and pins, while the explicit force flag hands the operator a destructive rebuild when one is actually wanted.

## Drift detection

`scripts/check_owui_preset_drift.py` compares each live preset (`/api/v1/models/model`) with its seeded file and names every difference. `./launch.sh up` runs the same upsert `seed` does, so a prompt or tool binding changed in the repo reaches the preset without `reseed`. The checker is silent only when Open WebUI or its API key is unavailable. It covers workspace presets and persona prompts. It was added after an `auto-documents` prompt fix (1370cd64) was live in the pipeline's config but not in the preset Open WebUI sent.

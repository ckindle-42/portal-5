---
id: unit-backup-restore-after-config-changes-re-seed
kind: what
title: "BACKUP_RESTORE \u2014 After config changes, re-seed"
sources:
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
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

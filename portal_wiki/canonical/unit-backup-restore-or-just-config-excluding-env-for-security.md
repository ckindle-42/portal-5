---
id: unit-backup-restore-or-just-config-excluding-env-for-security
kind: what
title: "BACKUP_RESTORE \u2014 Or just config (excluding .env for security)"
sources:
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5265658
updated_at: 1784946220.5265658
---

The alternative of backing up only `config/` and leaving `.env` out is no longer supported by the code path. The current `_launch_backup` always copies `.env` into the snapshot, and there is no flag to omit it; the only way to produce a config-only snapshot is to copy `config/` by hand. If a config-only archive is wanted, the timestamped naming convention should still be followed so the result slots into the same restore workflow.

## Why

The code traded the option of a secret-free config archive for a simpler invariant: every backup is fully restorable. That invariant is what lets a restore be a single command instead of a puzzle about which artifacts were or were not included in a given snapshot.

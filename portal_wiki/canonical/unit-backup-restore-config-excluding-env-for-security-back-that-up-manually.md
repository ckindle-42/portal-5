---
id: unit-backup-restore-config-excluding-env-for-security-back-that-up-manually
kind: what
title: "BACKUP_RESTORE \u2014 Config (excluding .env for security - back that up manually)"
sources:
- type: code
  path: scripts/lib/backup.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.528335
updated_at: 1784946220.528335
---

The old guide recommended archiving `config/` while leaving `.env` out of the tarball so secrets would not ride along. The current script does the opposite: `_launch_backup` copies `.env` into every backup alongside `config/` and `imports/`, and `_launch_restore` copies it back on restore. Secrets therefore live in every snapshot directory, so the security requirement shifts from excluding them to protecting the backup location itself with the same care as the live `.env`.

## Why

Secrets are useless at restore time if the backup that carries them omits them — a restore without `.env` cannot bring the stack up with the same pipeline keys. Bundling `.env` trades the old exclusion advice for a simpler guarantee that a backup is fully restorable, at the cost of requiring the backup directory to be treated as sensitive as the live environment file.

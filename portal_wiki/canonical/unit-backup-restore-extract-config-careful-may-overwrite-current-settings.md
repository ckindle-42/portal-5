---
id: unit-backup-restore-extract-config-careful-may-overwrite-current-settings
kind: what
title: "BACKUP_RESTORE \u2014 Extract config (careful - may overwrite current settings)"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5309289
updated_at: 1784946220.5309289
---

Restoring configuration is a manual step because `_launch_restore` restores the volumes and `.env` but deliberately leaves `config/` and `imports/` alone. The operator copies the saved directories back over the live tree, and because the backup stored them as plain directories this is a file copy rather than an archive extraction. That copy is wholesale: any tuning made since the snapshot was taken is overwritten by the saved version.

## Why

Config restoration must be an explicit, careful act rather than a silent side effect of the restore command, because the saved snapshot may predate intentional changes. Keeping it manual forces the operator to look at the difference between what the backup holds and what the live tree has before choosing to replace it.

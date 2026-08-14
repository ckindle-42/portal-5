---
id: unit-backup-restore-security-notes
kind: what
title: "BACKUP_RESTORE \u2014 Security Notes"
sources:
- type: code
  path: scripts/lib/backup.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.535368
updated_at: 1784946220.535368
---

Every backup produced by `_launch_backup` contains `.env`, including the pipeline API key, web UI secret, admin password, and any other secrets it holds. The script applies no encryption to the snapshot directory, so its confidentiality depends entirely on the filesystem permissions and physical security of the backup location. That elevates the backup directory to the same sensitivity class as the live `.env` file, with offsite or encrypted copies being the operator's responsibility.

## Why

The security model inverts the old advice: instead of keeping secrets out of backups, the code keeps them in backups and relies on the location being protected. Documenting that the snapshot is plaintext secrets at rest tells an operator why the backup directory must be treated like a credentials vault rather than a log archive.

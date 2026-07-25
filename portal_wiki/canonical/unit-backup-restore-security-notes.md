---
id: unit-backup-restore-security-notes
kind: what
title: "BACKUP_RESTORE \u2014 Security Notes"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Security Notes
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.535368
updated_at: 1784946220.535368
---

- Store backups encrypted at rest (use gpg or similar)
- Offsite backup recommended (S3, external drive)
- `.env` contains secrets — back up separately, store securely
- Test restore procedure periodically

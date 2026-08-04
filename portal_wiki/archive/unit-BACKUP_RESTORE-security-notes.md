---
id: unit-BACKUP_RESTORE-security-notes
kind: why
title: "BACKUP_RESTORE \u2014 Security Notes"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Security Notes
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.826101
updated_at: 1783195000.826101
---


- Store backups encrypted at rest (use gpg or similar)
- Offsite backup recommended (S3, external drive)
- `.env` contains secrets — back up separately, store securely
- Test restore procedure periodically

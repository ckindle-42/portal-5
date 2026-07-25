---
id: unit-backup-restore-restore-from-backup
kind: what
title: "BACKUP_RESTORE \u2014 Restore from backup"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Restore from backup
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.529736
updated_at: 1784946220.529736
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260303.tar.gz -C /

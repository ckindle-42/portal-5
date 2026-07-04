---
id: unit-BACKUP_RESTORE-migration-to-new-host
kind: why
title: "BACKUP_RESTORE \u2014 Migration to New Host"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Migration to New Host
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.825639
updated_at: 1783195000.825639
---


1. Backup from source:
   ```bash
   docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
       alpine tar czf /backup/openwebui-migration.tar.gz /data
   ```

2. Transfer backup file to new host

3. On new host:
   ```bash
   # Fresh Portal 5 install
   git clone https://github.com/ckindle-42/portal-5
   cd portal-5

   # Copy your .env (from backup or recreate from .env.example)
   cp .env.example .env
   # Edit .env with your settings

   # Stop services
   ./launch.sh down

   # Restore data
   docker volume create portal-5_open-webui-data
   docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
       alpine tar xzf /backup/openwebui-migration.tar.gz -C /

   # Start
   ./launch.sh up
   ```

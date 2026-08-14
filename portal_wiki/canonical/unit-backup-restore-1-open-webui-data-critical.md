---
id: unit-backup-restore-1-open-webui-data-critical
kind: what
title: "BACKUP_RESTORE \u2014 1. Open WebUI Data (Critical)"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.524183
updated_at: 1784946220.524183
---

The `portal-5_open-webui-data` volume holds the Open WebUI database plus uploaded files the personas read, which is why the backup script treats it as the primary artifact. The backup step runs an alpine helper container that mounts the volume at `/data` and packs the directory with `tar czf`; the restore step runs the same helper but clears `/data` first, then extracts with the archive rooted at the filesystem root. Because the tarball stores absolute paths, the mount point places the content back at the correct location.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

Operators expect chat history and identities to survive a full stack teardown, and that expectation lives entirely in this one volume. Backing it up before any configuration file matches the operator's priority ordering — a working deployment can be rebuilt from source, but the conversation data cannot be reconstructed.

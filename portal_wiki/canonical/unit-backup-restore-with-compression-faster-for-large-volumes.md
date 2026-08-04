---
id: unit-backup-restore-with-compression-faster-for-large-volumes
kind: what
title: "BACKUP_RESTORE \u2014 With compression (faster for large volumes)"
sources:
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.525281
updated_at: 1784946220.525281
---

Compression is not an option the script exposes; `_launch_backup` always writes gzip tarballs via `tar czf` when packing the Open WebUI and Grafana volumes. An operator who wants the tighter `gzip -9` level must run the alpine container manually, trading wall-clock time for smaller snapshots on very large volumes. The restored content is identical either way, since tar decompression is independent of the compression level used at creation time.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

The script optimizes for speed and simplicity by defaulting to standard gzip, which is fast enough for the two database volumes it handles. Compression level is a per-environment tradeoff between backup wall-clock and disk usage, so it is deliberately left to a manual invocation rather than hard-coded into the shared routine.

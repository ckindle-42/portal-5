---
id: unit-backup-restore-manual-backup
kind: what
title: "BACKUP_RESTORE \u2014 Manual backup"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5247529
updated_at: 1784946220.5247529
---

The manual one-liner for a single volume is exactly the mechanism `_launch_backup` wraps: an alpine container mounts `portal-5_open-webui-data` at `/data`, binds a host directory at `/backup`, and packs the data directory into a gzip tarball. The script hardcodes the volume names and output naming, so the raw one-liner is only useful when an operator wants a one-off snapshot outside the standard flow, such as right before a risky upgrade.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

Exposing the primitive behind the wrapper matters because it is the same command an operator can run against a volume when the script's fixed artifact set is not enough. The script exists to standardize naming and the multi-artifact flow, while the raw invocation stays available for ad-hoc snapshots that predate the introduction of `scripts/lib/backup.sh`.

---
id: unit-backup-restore-2-configuration-files
kind: what
title: "BACKUP_RESTORE \u2014 2. Configuration Files"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.525789
updated_at: 1784946220.525789
---

Besides `config/`, the backup command copies the `imports/` directory, which holds the Open WebUI workspace presets and persona fixtures that `openwebui-init` seeds into the UI. These files are generated artifacts, so they are regenerable via `sync-config`, but shipping them in every snapshot makes a restore self-contained without requiring regeneration first. The copies land next to `config/` inside the same timestamped backup directory, so one directory represents a complete point-in-time configuration.

## Why

Persona and workspace presets are derived from config but are themselves inputs to the running Open WebUI database, so including them means recovery does not depend on re-running a generator at restore time. Storing them as plain copies alongside config keeps a single backup directory sufficient for a full reconstruction.

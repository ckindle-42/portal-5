---
id: unit-host-log-rotation
kind: what
title: Bounded host log rotation
sources:
- type: code
  path: scripts/rotate_logs.py
- type: code
  path: scripts/lib/util.sh
- type: code
  path: deploy/launchd/com.portal5.log-rotate.plist
- type: code
  path: .env.example
- type: code
  path: tests/unit/test_rotate_logs.py
claims: []
confidence: high
tags:
- operations
- logs
- verified-v1
created_at: 1791376709
updated_at: 1791376709
---

`scripts/rotate_logs.py` copy-truncates configured host logs that exceed
`LOG_ROTATE_MAX_MB` (default 100 MiB), after writing and validating a gzip
snapshot. It retains `LOG_ROTATE_KEEP` generations (default 5), shifts older
archives, and leaves the source intact if the copy fails or the source changes
during copying. The default paths are Ollama, oMLX, and `~/.portal5/logs/*.log`;
`LOG_ROTATE_FILES` can override them with semicolon-separated glob patterns.

On Apple Silicon, `scripts/lib/util.sh` installs
`com.portal5.log-rotate.plist` as an hourly user LaunchAgent. Run
`.venv/bin/python scripts/rotate_logs.py --dry-run` to preview a pass.

## Why

Launchd keeps writers on the same log inode, so the rotator copies and gzips a
complete snapshot before truncating that inode in place. A failed or changing
source is skipped, preserving the original data for the next pass.

---
id: unit-HOWTO-backup-configuration
kind: why
title: "HOWTO \u2014 Backup configuration"
sources:
- type: design
  path: docs/HOWTO.md
  section: Backup configuration
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8588412
updated_at: 1783195000.8588412
---


```bash
tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
```

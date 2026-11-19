---
id: unit-HOWTO-backup-configuration
historical: true
kind: why
title: "HOWTO \u2014 Backup configuration"
sources:
- type: design
  path: docs/HOWTO.md
  section: Backup configuration
confidence: high
tags:
- docs
- HOWTO

---


```bash
tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
```

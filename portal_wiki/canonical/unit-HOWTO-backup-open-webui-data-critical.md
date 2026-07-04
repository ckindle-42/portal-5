---
id: unit-HOWTO-backup-open-webui-data-critical
kind: why
title: "HOWTO \u2014 Backup Open WebUI data (critical)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Backup Open WebUI data (critical)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.858591
updated_at: 1783195000.858591
---


```bash
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

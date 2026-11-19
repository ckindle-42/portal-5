---
id: unit-HOWTO-backup-open-webui-data-critical
historical: true
kind: why
title: "HOWTO \u2014 Backup Open WebUI data (critical)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Backup Open WebUI data (critical)
confidence: high
tags:
- docs
- HOWTO

---


```bash
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

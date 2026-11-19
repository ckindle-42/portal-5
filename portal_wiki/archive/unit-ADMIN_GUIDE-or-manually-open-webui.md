---
id: unit-ADMIN_GUIDE-or-manually-open-webui
historical: true
kind: why
title: "ADMIN_GUIDE \u2014 Or manually (Open WebUI):"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Or manually (Open WebUI):'
confidence: high
tags:
- docs
- ADMIN_GUIDE

---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

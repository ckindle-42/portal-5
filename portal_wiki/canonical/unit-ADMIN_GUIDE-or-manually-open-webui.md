---
id: unit-ADMIN_GUIDE-or-manually-open-webui
kind: why
title: "ADMIN_GUIDE \u2014 Or manually (Open WebUI):"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Or manually (Open WebUI):'
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.814633
updated_at: 1783195000.814633
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

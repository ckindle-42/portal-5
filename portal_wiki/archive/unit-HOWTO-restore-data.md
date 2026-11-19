---
id: unit-HOWTO-restore-data
historical: true
kind: why
title: "HOWTO \u2014 Restore data"
sources:
- type: design
  path: docs/HOWTO.md
  section: Restore data
confidence: high
tags:
- docs
- HOWTO

---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260330.tar.gz -C /

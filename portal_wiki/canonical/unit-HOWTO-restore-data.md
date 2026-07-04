---
id: unit-HOWTO-restore-data
kind: why
title: "HOWTO \u2014 Restore data"
sources:
- type: design
  path: docs/HOWTO.md
  section: Restore data
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8590631
updated_at: 1783195000.8590631
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260330.tar.gz -C /

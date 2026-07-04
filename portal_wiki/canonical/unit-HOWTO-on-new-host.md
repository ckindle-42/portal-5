---
id: unit-HOWTO-on-new-host
kind: why
title: "HOWTO \u2014 On new host:"
sources:
- type: design
  path: docs/HOWTO.md
  section: 'On new host:'
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.859532
updated_at: 1783195000.859532
---

git clone https://github.com/ckindle-42/portal-5
cd portal-5
cp /path/to/.env .env
./launch.sh down
docker volume create portal-5_open-webui-data
docker run --rm -v portal-5_open-webui-data:/data -v /path/to/backups:/backup \
    alpine tar xzf /backup/openwebui-backup-*.tar.gz -C /
./launch.sh up
```

---

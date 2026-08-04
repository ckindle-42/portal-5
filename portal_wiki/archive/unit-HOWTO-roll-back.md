---
id: unit-HOWTO-roll-back
kind: why
title: "HOWTO \u2014 roll back"
sources:
- type: design
  path: docs/HOWTO.md
  section: roll back
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.854251
updated_at: 1783195000.854251
---

curl -s localhost:8921/tools/kb_restore -X POST \
  -H 'Content-Type: application/json' \
  -d '{"arguments": {"kb_id": "nerc-cip", "version": 42}}'
```

Note: `optimize()` prunes **untagged** versions older than 7 days; the
automatic pre-rebuild tags are exempt. The restore itself is a new version, so
restores are undoable.

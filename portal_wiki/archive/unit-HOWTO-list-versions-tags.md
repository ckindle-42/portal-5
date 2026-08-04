---
id: unit-HOWTO-list-versions-tags
kind: why
title: "HOWTO \u2014 list versions + tags"
sources:
- type: design
  path: docs/HOWTO.md
  section: list versions + tags
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.854024
updated_at: 1783195000.854024
---

curl -s localhost:8921/tools/kb_versions -X POST \
  -H 'Content-Type: application/json' -d '{"arguments": {"kb_id": "nerc-cip"}}'

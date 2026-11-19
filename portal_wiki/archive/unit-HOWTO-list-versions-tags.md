---
id: unit-HOWTO-list-versions-tags
historical: true
kind: why
title: "HOWTO \u2014 list versions + tags"
sources:
- type: design
  path: docs/HOWTO.md
  section: list versions + tags
confidence: high
tags:
- docs
- HOWTO

---

curl -s localhost:8921/tools/kb_versions -X POST \
  -H 'Content-Type: application/json' -d '{"arguments": {"kb_id": "nerc-cip"}}'

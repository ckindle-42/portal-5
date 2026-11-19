---
id: unit-HOWTO-list-available-tools
historical: true
kind: why
title: "HOWTO \u2014 List available tools"
sources:
- type: design
  path: docs/HOWTO.md
  section: List available tools
confidence: high
tags:
- docs
- HOWTO

---

curl -s http://localhost:8913/tools | python3 -m json.tool
```

**Output:** Files are returned as downloadable attachments in the chat.

---

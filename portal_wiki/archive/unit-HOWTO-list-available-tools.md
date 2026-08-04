---
id: unit-HOWTO-list-available-tools
kind: why
title: "HOWTO \u2014 List available tools"
sources:
- type: design
  path: docs/HOWTO.md
  section: List available tools
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.843749
updated_at: 1783195000.843749
---

curl -s http://localhost:8913/tools | python3 -m json.tool
```

**Output:** Files are returned as downloadable attachments in the chat.

---

---
id: unit-HOWTO-generate-a-word-document
historical: true
kind: why
title: "HOWTO \u2014 Generate a Word document"
sources:
- type: design
  path: docs/HOWTO.md
  section: Generate a Word document
confidence: high
tags:
- docs
- HOWTO

---


```
Create a project proposal for migrating our monolith to microservices.
Include: executive summary, architecture diagram description, timeline, risk matrix.
Save as a Word document.
```

The AI generates structured markdown. The MCP server converts it to `.docx` using python-docx.

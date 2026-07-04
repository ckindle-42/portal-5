---
id: unit-ADMIN_GUIDE-check-which-models-ollama-currently-has-loaded
kind: why
title: "ADMIN_GUIDE \u2014 Check which models Ollama currently has loaded"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Check which models Ollama currently has loaded
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8172958
updated_at: 1783195000.8172958
---

curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

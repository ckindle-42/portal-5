---
id: unit-HOWTO-check-which-model-ollama-has-loaded-router-should-
kind: why
title: "HOWTO \u2014 Check which model Ollama has loaded (router should always be\
  \ in the list)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Check which model Ollama has loaded (router should always be in the list)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8394198
updated_at: 1783195000.8394198
---

curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

---
id: unit-HOWTO-check-which-model-ollama-has-loaded-router-should-
historical: true
kind: why
title: "HOWTO \u2014 Check which model Ollama has loaded (router should always be\
  \ in the list)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Check which model Ollama has loaded (router should always be in the list)
confidence: high
tags:
- docs
- HOWTO

---

curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

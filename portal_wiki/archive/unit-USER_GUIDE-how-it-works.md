---
id: unit-USER_GUIDE-how-it-works
historical: true
kind: why
title: "USER_GUIDE \u2014 How It Works"
sources:
- type: design
  path: docs/USER_GUIDE.md
  section: How It Works
confidence: high
tags:
- docs
- USER_GUIDE

---


Documents are split into 1500-character chunks with 100-character overlap, then
embedded using `nomic-embed-text` running locally in Ollama. Search uses hybrid
mode (semantic + keyword) for best results. No document content leaves your machine.

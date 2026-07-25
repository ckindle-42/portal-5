---
id: unit-user-guide-how-it-works
kind: what
title: "USER_GUIDE \u2014 How It Works"
sources:
- type: doc
  path: docs/USER_GUIDE.md
  commit: 05e42ec2
  section: How It Works
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.516234
updated_at: 1784946220.516234
---

Documents are split into 1500-character chunks with 100-character overlap, then
embedded using `nomic-embed-text` running locally in Ollama. Search uses hybrid
mode (semantic + keyword) for best results. No document content leaves your machine.

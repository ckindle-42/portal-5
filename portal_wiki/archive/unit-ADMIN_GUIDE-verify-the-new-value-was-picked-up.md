---
id: unit-ADMIN_GUIDE-verify-the-new-value-was-picked-up
kind: why
title: "ADMIN_GUIDE \u2014 Verify the new value was picked up:"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Verify the new value was picked up:'
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.816587
updated_at: 1783195000.816587
---

ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED
```

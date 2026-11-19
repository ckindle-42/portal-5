---
id: unit-ADMIN_GUIDE-verify-the-new-value-was-picked-up
historical: true
kind: why
title: "ADMIN_GUIDE \u2014 Verify the new value was picked up:"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Verify the new value was picked up:'
confidence: high
tags:
- docs
- ADMIN_GUIDE

---

ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED
```

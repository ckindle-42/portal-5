---
id: unit-code-portal_channels
kind: what
title: portal_channels subsystem (4 files)
sources:
- type: code
  path: portal_channels/__init__.py
  commit: 8015e9381c8a
- type: code
  path: portal_channels/dispatcher.py
  commit: 8015e9381c8a
- type: code
  path: portal_channels/slack/bot.py
  commit: 8015e9381c8a
- type: code
  path: portal_channels/telegram/bot.py
  commit: 8015e9381c8a
claims:
- probe: repo.path.exists
  path: portal_channels/__init__.py
  equals: true
confidence: high
tags:
- code
- portal_channels
---

# portal_channels subsystem

**Files:** 4

- `portal_channels/__init__.py`
- `portal_channels/dispatcher.py`
- `portal_channels/slack/bot.py`
- `portal_channels/telegram/bot.py`

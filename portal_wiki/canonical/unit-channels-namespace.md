---
id: unit-channels-namespace
kind: mixed
title: "Channels package \u2014 Slack/Telegram adapter namespace"
sources:
- type: code
  path: portal_channels/__init__.py
  commit: 5b73259d
last_generated_commit: 5b73259d
claims: []
confidence: high
tags:
- authored-v1
- channels
created_at: 1785795351.51374
updated_at: 1785795351.51374
---

The channels package is the namespace for Portal's two messenger adapters —
Slack and Telegram — and their shared dispatcher. It carries the channel
adapters' version string and no behaviour of its own.

## Why

The namespace exists to give the channel suite a stable import home and a
single version to report. Keeping the version here means both adapters and the
dispatcher agree on what release they belong to without each module carrying
its own copy of the number.

## Interfaces

The module exposes `__version__` only. The real content is the sibling modules
`dispatcher`, `slack/bot`, and `telegram/bot`.

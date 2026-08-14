---
id: unit-alerts-channel-priority
kind: what
title: "ALERTS \u2014 Channel Priority"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/notifications/channels/__init__.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.551283
updated_at: 1784946220.551283
---

There is no priority ladder and no ordered fan-out. `dispatch` gathers every registered channel into a single `asyncio.gather` call with `return_exceptions`, so Slack, Telegram, Email, Pushover, and Webhook all receive an event at the same moment, and a slow or failed receiver is isolated from the others. Because every configured channel sees every event, deduplication is left to the operator rather than built into the dispatcher.

## Why

Fanning out concurrently rather than sequentially keeps an unresponsive endpoint from delaying the other four channels, and fire-and-forget send means a notification failure can never fail a chat request. The absence of priority is deliberate: an alert is either worth sending or not, so operators who want fewer messages simply omit the channels they do not need.

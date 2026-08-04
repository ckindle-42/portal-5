---
id: unit-alerts-telegram
kind: what
title: "ALERTS \u2014 Telegram"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/telegram.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5466712
updated_at: 1784946220.5466712
---

Telegram accepts either dedicated alert credentials or the main bot variables: `TELEGRAM_ALERT_BOT_TOKEN` and `TELEGRAM_ALERT_CHANNEL_ID` take precedence, falling back to `TELEGRAM_BOT_TOKEN` and `TELEGRAM_USER_IDS`, where a comma-separated list uses its first entry. Messages POST to the bot's `sendMessage` method with Markdown parse mode, and a dedicated alert bot is recommended so operational noise never mixes with user-facing chat.

## Why

The two-variable fallback lets a deployment reuse an existing Telegram bot when no one wants to stand up a second one, while the dedicated alert variables still allow clean separation between operational noise and user chat. Relying on the bot sendMessage API rather than a channel webhook keeps configuration to just a token and a chat identifier.

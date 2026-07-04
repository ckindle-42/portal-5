---
id: unit-ALERTS-telegram
kind: why
title: "ALERTS \u2014 Telegram"
sources:
- type: design
  path: docs/ALERTS.md
  section: Telegram
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.819777
updated_at: 1783195000.819777
---


1. Create a **dedicated alert bot** via [@BotFather](https://t.me/BotFather) — keep it separate from your user-facing bot
2. Add the bot to your target channel as an admin
3. Get your channel ID — forward a message from the channel to [@userinfobot](https://t.me/userinfobot)

```bash
echo "TELEGRAM_ALERT_BOT_TOKEN=123456789:ABCdef... >> .env
echo "TELEGRAM_ALERT_CHANNEL_ID=-1001234567890" >> .env
```

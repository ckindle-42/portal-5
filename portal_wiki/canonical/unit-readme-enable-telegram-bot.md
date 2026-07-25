---
id: unit-readme-enable-telegram-bot
kind: what
title: "README \u2014 Enable Telegram Bot"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Enable Telegram Bot
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6846988
updated_at: 1784946220.6846988
---

1. Message **@BotFather** on Telegram → `/newbot` → copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram`
5. Message your bot `/start` to verify

---

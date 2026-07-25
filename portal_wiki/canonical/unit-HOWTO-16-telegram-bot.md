---
id: unit-HOWTO-16-telegram-bot
kind: what
title: HOWTO -- 16. Telegram Bot
sources:
- type: doc
  path: docs/HOWTO.md
  commit: ddb1cc61
  section: 16. Telegram Bot
last_generated_commit: ddb1cc61
confidence: high
tags:
- docs
- HOWTO
created_at: 1784944767.916281
updated_at: 1784944767.916281
---

1. Message **@BotFather** on Telegram -> `/newbot` -> copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram`
5. Message your bot `/start` to verify

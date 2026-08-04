---
id: unit-HOWTO-16-telegram-bot
kind: what
title: HOWTO -- 16. Telegram Bot
sources:
- type: code
  path: launch.sh
- type: code
  path: portal_channels/telegram/bot.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
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
4. Start: `./launch.sh up-telegram` — the `up-telegram` case in `launch.sh` refuses to start when `TELEGRAM_BOT_TOKEN` is unset, then runs `docker compose --profile telegram up -d`
5. Message your bot `/start` to verify — the bot's `/start` handler in `portal_channels/telegram/bot.py` replies

The bot container (`portal-telegram` in `deploy/portal-5/docker-compose.yml`) is profile-gated: plain `./launch.sh up` auto-detects the token and includes the telegram profile, while `up-telegram` forces it. The bot relays messages to the pipeline via `PIPELINE_URL` with `PIPELINE_API_KEY`, `TELEGRAM_USER_IDS` (comma-separated) controls which Telegram users may talk to it, and `TELEGRAM_DEFAULT_WORKSPACE` selects the routing workspace when the user has not set one with `/workspace`.

## Why

A messaging bot is just a thin channel adapter: all the intelligence stays in the pipeline, so the bot container only relays text between Telegram and the OpenAI-compatible router. Making it a compose profile rather than a default service keeps the token-less install clean, and the token auto-detection in `up` means turning the channel on is a one-line `.env` change with no extra command.

---
id: unit-readme-telegram-bot-setup
kind: what
title: "README \u2014 Enable Telegram Bot"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
- type: code
  path: portal_channels/telegram/bot.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1788033019.601702
updated_at: 1788033019.601702
---

To enable the Telegram channel, create a bot in Telegram and add its token to
`.env`:

1. Open a chat with **@BotFather** and send `/newbot`; copy the token it returns.
2. Ask **@userinfobot** for your numeric Telegram user ID.
3. In `.env` set:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Run `./launch.sh up-telegram` — `launch.sh` aborts the start when
   `TELEGRAM_BOT_TOKEN` is empty, otherwise it runs
   `docker compose --profile telegram up -d`.
5. Send `/start` to the bot; the handler in `portal_channels/telegram/bot.py`
   confirms the relay works.

The `portal-telegram` service in `deploy/portal-5/docker-compose.yml` is gated
behind the `telegram` compose profile. A plain `./launch.sh up` enables the
profile automatically when the token is present, so adding the channel is just a
`.env` edit; `up-telegram` is the explicit variant that forces the profile on.
The container relays user messages to the pipeline with `PIPELINE_URL` and
`PIPELINE_API_KEY`. `TELEGRAM_USER_IDS` accepts a comma-separated list of the
only Telegram accounts allowed to talk to the bot, and
`TELEGRAM_DEFAULT_WORKSPACE` picks the routing workspace for any user who has not
chosen one with `/workspace`.

## Why

Keeping the bot behind a compose profile, rather than a default service, keeps a
token-less first install free of an always-on relay container. The token check in
`up-telegram` fails loudly instead of booting a bot with no credentials, and the
auto-detection in `up` means the whole channel can be switched on by setting one
`.env` value — the bot itself stays a thin transport that passes text to the
pipeline and returns its answer.

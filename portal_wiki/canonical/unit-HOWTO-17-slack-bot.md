---
id: unit-HOWTO-17-slack-bot
kind: what
title: HOWTO -- 17. Slack Bot
sources:
- type: code
  path: launch.sh
- type: code
  path: portal_channels/slack/bot.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1784944767.916648
updated_at: 1784944767.916648
---

1. Go to https://api.slack.com/apps -> **Create New App** -> **From scratch**
2. Under **OAuth & Permissions** -> add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write` (Slack-side app configuration)
3. Under **Socket Mode** -> enable it -> generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack` — the `up-slack` case in `launch.sh` requires both `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` before running `docker compose --profile slack up -d`
7. Mention `@portal` in any channel to verify — `portal_channels/slack/bot.py` registers an `app_mention` event handler

The bot container (`portal-slack` in the compose file) receives the three tokens as env vars and runs `python -m portal_channels.slack.bot`. It connects via Socket Mode, so no public webhook or ingress is required. `SLACK_DEFAULT_WORKSPACE` sets the routing workspace for DMs and unmapped channels.

## Why

Slack integration uses Socket Mode precisely because it needs no public endpoint: the app-level token establishes an outbound WebSocket from the bot container, which keeps the whole deployment firewalled. The two-token requirement (bot token for the app, app token for the socket) is why `up-slack` validates both before starting — a half-configured bot fails loudly instead of silently ignoring mentions.

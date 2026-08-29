---
id: unit-readme-slack-bot-setup
kind: what
title: "README \u2014 Enable Slack Bot"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
- type: code
  path: portal_channels/slack/bot.py
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

To enable the Slack channel, create a Slack app with Socket Mode and add its
tokens to `.env`:

1. Create a new app at https://api.slack.com/apps (**Create New App** -> **From scratch**).
2. Under **OAuth & Permissions**, add the bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
   (Slack-side app configuration).
3. Enable **Socket Mode** and generate an **App-Level Token** (xapp-...).
4. Install the app to your workspace.
5. In `.env` set:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Run `./launch.sh up-slack` — `launch.sh` refuses to start unless both
   `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` are set, then runs
   `docker compose --profile slack up -d`.
7. Mention `@portal` in a channel; the `app_mention` event handler in
   `portal_channels/slack/bot.py` answers.

The `portal-slack` service (defined in `deploy/portal-5/docker-compose.yml`) gets
the three tokens as environment variables and launches
`python -m portal_channels.slack.bot`. Because the app connects over Socket Mode,
the bot opens an outbound WebSocket and needs no public webhook or ingress.
`SLACK_DEFAULT_WORKSPACE` selects the routing workspace for direct messages and
for channels that have no explicit mapping.

## Why

Socket Mode is what lets the whole integration stay behind the firewall: the
app-level token drives an outbound WebSocket from the container, so no inbound
path has to be exposed. The two-token design — bot token for the app, app token
for the socket — is why `up-slack` validates both before launching: a bot that
is only half-configured fails immediately instead of silently dropping every
mention.

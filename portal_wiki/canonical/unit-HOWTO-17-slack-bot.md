---
id: unit-HOWTO-17-slack-bot
kind: what
title: HOWTO -- 17. Slack Bot
sources:
- type: doc
  path: docs/HOWTO.md
  commit: ddb1cc61
  section: 17. Slack Bot
last_generated_commit: ddb1cc61
confidence: high
tags:
- docs
- HOWTO
created_at: 1784944767.916648
updated_at: 1784944767.916648
---

1. Go to https://api.slack.com/apps -> **Create New App** -> **From scratch**
2. Under **OAuth & Permissions** -> add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** -> enable it -> generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack`
7. Mention `@portal` in any channel to verify

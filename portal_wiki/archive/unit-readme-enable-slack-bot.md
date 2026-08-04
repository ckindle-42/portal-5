---
id: unit-readme-enable-slack-bot
kind: what
title: "README \u2014 Enable Slack Bot"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Enable Slack Bot
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.685566
updated_at: 1784946220.685566
---

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **OAuth & Permissions** → add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** → enable it → generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack`
7. Mention `@portal` in any channel to verify

---

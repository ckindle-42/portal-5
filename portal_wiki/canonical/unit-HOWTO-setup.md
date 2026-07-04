---
id: unit-HOWTO-setup
kind: why
title: "HOWTO \u2014 Setup"
sources:
- type: design
  path: docs/HOWTO.md
  section: Setup
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8554199
updated_at: 1783195000.8554199
---


1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **OAuth & Permissions** → add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** → enable → generate **App-Level Token** (xapp-...)
4. Install app to workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start:
   ```bash
   ./launch.sh up-slack
   ```

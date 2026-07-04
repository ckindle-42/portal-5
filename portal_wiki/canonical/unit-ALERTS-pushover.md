---
id: unit-ALERTS-pushover
kind: why
title: "ALERTS \u2014 Pushover"
sources:
- type: design
  path: docs/ALERTS.md
  section: Pushover
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.820197
updated_at: 1783195000.820197
---


1. Sign up at [https://pushover.net](https://pushover.net)
2. Create an application to get your API token
3. Find your user key on your dashboard

```bash
echo "PUSHOVER_API_TOKEN=your-app-token" >> .env
echo "PUSHOVER_USER_KEY=your-user-key" >> .env
```

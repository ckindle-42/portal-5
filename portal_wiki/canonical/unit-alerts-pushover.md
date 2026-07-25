---
id: unit-alerts-pushover
kind: what
title: "ALERTS \u2014 Pushover"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: Pushover
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.547549
updated_at: 1784946220.547549
---

1. Sign up at [https://pushover.net](https://pushover.net)
2. Create an application to get your API token
3. Find your user key on your dashboard

```bash
echo "PUSHOVER_API_TOKEN=your-app-token" >> .env
echo "PUSHOVER_USER_KEY=your-user-key" >> .env
```

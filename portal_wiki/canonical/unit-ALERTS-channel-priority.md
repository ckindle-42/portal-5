---
id: unit-ALERTS-channel-priority
kind: why
title: "ALERTS \u2014 Channel Priority"
sources:
- type: design
  path: docs/ALERTS.md
  section: Channel Priority
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.820888
updated_at: 1783195000.820888
---


All channels receive the same events simultaneously. To avoid duplicate alerts in
Slack/Telegram, use separate bots or filter with channel rules.

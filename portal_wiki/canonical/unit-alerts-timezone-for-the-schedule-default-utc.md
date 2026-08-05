---
id: unit-alerts-timezone-for-the-schedule-default-utc
kind: what
title: "ALERTS \u2014 Timezone for the schedule (default: UTC)"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5508978
updated_at: 1784946220.5508978
---

`ALERT_SUMMARY_TIMEZONE` names the tzinfo passed to the summary cron trigger. The example environment and the compose service both ship `America/Chicago`, so the shipped default hour of eight means eight in the morning Central time, while the in-process fallback is UTC when the variable is absent. Changing the value shifts the send moment without altering the hour number.

## Why

Scheduling in a named timezone rather than a fixed UTC offset matters because offset changes are what break a same-local-time-every-day promise across daylight saving transitions. Shipping the operator's own local zone as the example default makes the summary arrive at a genuinely convenient hour with no further configuration.

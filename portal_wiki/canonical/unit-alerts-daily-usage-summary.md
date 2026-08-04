---
id: unit-alerts-daily-usage-summary
kind: what
title: "ALERTS \u2014 Daily Usage Summary"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5459251
updated_at: 1784946220.5459251
---

The summary payload is a fixed field set. `SummaryEvent` carries `total_requests` and `requests_by_workspace` computed as deltas from the prior day's snapshot, plus `healthy_backends`, `total_backends`, and `uptime_seconds`. Extended figures such as token counts, average tokens per second, average response time, and errors by type ride along, and each channel renders the same event differently. Two guards skip the send when persisted state was wiped by a container recreation, so an empty first report never masquerades as a quiet day.

## Why

The field set is deliberately small and identical across channels so any receiver can parse the same summary in Slack, email, or raw JSON without special casing. Delta computation keeps the totals truthful for the reporting window, and the restart guards are the practical consequence of running counters that must survive process restarts to be useful.

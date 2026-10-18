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
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5459251
updated_at: 1792281600
---

The summary payload is a fixed field set. `SummaryEvent` carries `total_requests` and `requests_by_workspace` computed as deltas from the prior day's snapshot, plus `healthy_backends`, `total_backends`, and `uptime_seconds`. Extended figures ride along: token counts, token-weighted decode and answer tokens per second (each is that day's sum of tokens divided by that day's sum of seconds), the median time to first token with its `ttft_sample_count`, the top models by answer-token volume with each model's answer rate, average response time, and errors by type. Answer-rate counters include only rows with at least 32 answer tokens (`MIN_ANSWER_TOKENS_FOR_RATE`); this keeps brief, bursty answers from inflating answer tok/s. Decode and TTFT still include those rows. `bench-*` workspaces are left out of those rates. `avg_tokens_per_second` is the decode rate under its previous name. Each channel renders the same event. Two guards skip the send when persisted state was wiped by a container recreation, so an empty first report never masquerades as a quiet day.

## Why

The field set is deliberately small and identical across channels so any receiver can parse the same summary in Slack, email, or raw JSON without special casing. Delta computation keeps the totals truthful for the reporting window. Decode and answer rates are ratios of those deltas, so a long generation outweighs a short one and a restart does not have to average stored per-request rates. The restart guards are the practical consequence of running counters that must survive process restarts to be useful.

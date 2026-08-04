---
id: unit-alerts-daily-summary
kind: what
title: "ALERTS \u2014 Daily Summary"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/notifications/events.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.549702
updated_at: 1784946220.549702
---

The daily summary is a scheduled job rather than a threshold event. The scheduler registers `_send_daily_summary` on an APScheduler `CronTrigger` at the configured hour and timezone, and the job only exists when APScheduler is importable and `ALERT_SUMMARY_ENABLED` is truthy. The report is built from deltas against a persisted snapshot, so it describes the previous day's activity instead of cumulative totals since the container started.

## Why

Summaries are time-triggered, not threshold-triggered, because they report a trailing window of pipeline health rather than an anomaly that needs immediate attention. A cron trigger at a fixed local hour keeps delivery predictable for whoever reads it, and snapshot-based deltas keep the headline number honest about the reporting window regardless of when the pipeline last restarted.

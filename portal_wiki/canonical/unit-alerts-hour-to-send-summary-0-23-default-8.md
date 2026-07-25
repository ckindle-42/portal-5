---
id: unit-alerts-hour-to-send-summary-0-23-default-8
kind: what
title: "ALERTS \u2014 Hour to send summary (0-23, default: 8)"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: 'Hour to send summary (0-23, default: 8)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.550354
updated_at: 1784946220.550354
---

ALERT_SUMMARY_HOUR=8               # .env.example ships 8 (8am CST); if unset entirely, the
                                    # code falls back to 9 (scheduler.py: `os.environ.get("ALERT_SUMMARY_HOUR", "9")`)

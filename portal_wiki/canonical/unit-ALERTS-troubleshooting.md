---
id: unit-ALERTS-troubleshooting
kind: why
title: "ALERTS \u2014 Troubleshooting"
sources:
- type: design
  path: docs/ALERTS.md
  section: Troubleshooting
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.8211122
updated_at: 1783195000.8211122
---


**No alerts received:**
- Verify `NOTIFICATIONS_ENABLED=true` in `.env`
- Check pipeline logs: `docker compose logs portal-pipeline | grep -i "notification"`
- Test a channel directly — if it works in the chat app it will work here

**Telegram alerts not working:**
- Ensure the alert bot is an admin in the target channel
- Channel ID format: `-1001234567890` (negative, starts with `-100`)
- For private channels, the bot must be added before the channel ID will work

**Email not working:**
- Check SMTP credentials — many providers require app-specific passwords
- Port 587 = STARTTLS, Port 465 = SSL — verify your provider's requirements

**Pushover alerts not working:**
- Verify the user key matches your Pushover dashboard exactly
- Check that the application token is correct (not the user key)

**Daily summary not sent:**
- Confirm `ALERT_SUMMARY_ENABLED=true`
- Check the scheduled hour and timezone match your expectation
- Summary uses in-memory request counts — if the pipeline restarts between
  midnight and the summary time, counts reset to zero for that day

**Webhook not firing:**
- Verify `WEBHOOK_URL` is set and the endpoint is reachable from the container
- Check that the endpoint accepts POST requests with `Content-Type: application/json`
- If using `WEBHOOK_HEADERS`, ensure it is valid JSON — malformed JSON is logged and ignored
- Inspect outgoing requests: `docker compose logs portal-pipeline | grep -i webhook`

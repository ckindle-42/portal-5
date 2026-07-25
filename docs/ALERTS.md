# Portal 6.0.0 — Alerts & Notifications Guide

<!-- WIKI:GENERATED unit=unit-alerts-portal-6-0-0-alerts-notifications-guide -->
Portal 5 can send operational alerts and daily usage summaries to Slack, Telegram,
Email, Pushover, and any generic HTTP webhook endpoint. Notifications are disabled by default.
<!-- /WIKI:GENERATED -->

---

## Quick Start

<!-- WIKI:GENERATED unit=unit-alerts-quick-start -->
```bash
<!-- /WIKI:GENERATED -->

---

# 1. Enable notifications

<!-- WIKI:GENERATED unit=unit-alerts-1-enable-notifications -->
echo "NOTIFICATIONS_ENABLED=true" >> .env
<!-- /WIKI:GENERATED -->

---

# 3. Restart the pipeline

<!-- WIKI:GENERATED unit=unit-alerts-3-restart-the-pipeline -->
docker compose restart portal-pipeline
```
<!-- /WIKI:GENERATED -->

---

## Operational Alerts

<!-- WIKI:GENERATED unit=unit-alerts-operational-alerts -->
Fired immediately when a threshold is crossed:

| Event | Trigger | Debounce |
|-------|---------|----------|
| `backend_down` | A backend fails `ALERT_BACKEND_DOWN_THRESHOLD` consecutive health checks | Yes — one alert per transition |
| `backend_recovered` | A previously-down backend passes a health check | Yes — one alert per transition |
| `all_backends_down` | Every backend is unhealthy simultaneously | Yes — fires once, clears on any recovery |
| `config_error` | `backends.yaml` missing or unparseable | No debounce |
<!-- /WIKI:GENERATED -->

---

## Daily Usage Summary

<!-- WIKI:GENERATED unit=unit-alerts-daily-usage-summary -->
Fired once per day at a configured hour. Contains:
- Total requests since last summary
- Requests broken down by workspace
- Number of healthy backends
- Process uptime
<!-- /WIKI:GENERATED -->

---

### Slack

<!-- WIKI:GENERATED unit=unit-alerts-slack -->
1. Create an Incoming Webhook at [https://api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Copy the webhook URL (e.g. `https://hooks.slack.com/services/...`)

```bash
echo "SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" >> .env
echo "SLACK_ALERT_CHANNEL=#portal-alerts" >> .env
```
<!-- /WIKI:GENERATED -->

---

### Telegram

<!-- WIKI:GENERATED unit=unit-alerts-telegram -->
1. Create a **dedicated alert bot** via [@BotFather](https://t.me/BotFather) — keep it separate from your user-facing bot
2. Add the bot to your target channel as an admin
3. Get your channel ID — forward a message from the channel to [@userinfobot](https://t.me/userinfobot)

```bash
echo "TELEGRAM_ALERT_BOT_TOKEN=123456789:ABCdef... >> .env
echo "TELEGRAM_ALERT_CHANNEL_ID=-1001234567890" >> .env
```
<!-- /WIKI:GENERATED -->

---

### Email

<!-- WIKI:GENERATED unit=unit-alerts-email -->
Any SMTP provider works (Gmail, Mailgun, SendGrid, etc.):

```bash
echo "SMTP_HOST=smtp.example.com" >> .env
echo "SMTP_PORT=587" >> .env
echo "SMTP_USER=your-username" >> .env
echo "SMTP_PASSWORD=your-password" >> .env
echo "SMTP_FROM=portal@portal.local" >> .env
echo "EMAIL_ALERT_TO=admin@portal.local" >> .env
```

For Gmail with 2FA, use an [App Password](https://support.google.com/accounts/answer/185833).
<!-- /WIKI:GENERATED -->

---

### Pushover

<!-- WIKI:GENERATED unit=unit-alerts-pushover -->
1. Sign up at [https://pushover.net](https://pushover.net)
2. Create an application to get your API token
3. Find your user key on your dashboard

```bash
echo "PUSHOVER_API_TOKEN=your-app-token" >> .env
echo "PUSHOVER_USER_KEY=your-user-key" >> .env
```
<!-- /WIKI:GENERATED -->

---

### Webhook

<!-- WIKI:GENERATED unit=unit-alerts-webhook -->
POST JSON to any HTTP endpoint — works with PagerDuty, custom receivers, SIEM systems, or any service that accepts inbound webhooks.

```bash
echo "WEBHOOK_URL=https://your-endpoint.example.com/portal-events" >> .env
<!-- /WIKI:GENERATED -->

---

# Optional: JSON object for additional headers (e.g. auth tokens)

<!-- WIKI:GENERATED unit=unit-alerts-optional-json-object-for-additional-headers-e-g-auth-tokens -->
echo 'WEBHOOK_HEADERS={"Authorization": "Bearer YOUR_TOKEN"}' >> .env
```

**Alert event payload:**
```json
{
  "event": "backend_down",
  "message": "Backend 'ollama-general' has been unhealthy for 3 consecutive checks.",
  "backend_id": "ollama-general",
  "workspace": null,
  "timestamp": "2026-03-30T12:00:00+00:00",
  "metadata": {}
}
```

**Summary event payload:**
```json
{
  "event": "daily_summary",
  "timestamp": "2026-03-30T09:00:00+00:00",
  "total_requests": 1247,
  "requests_by_workspace": {"auto": 800, "auto-coding": 312, "auto-security": 135},
  "healthy_backends": 4,
  "total_backends": 4,
  "uptime_seconds": 86400.0
}
```
<!-- /WIKI:GENERATED -->

---

## Alert Thresholds

<!-- WIKI:GENERATED unit=unit-alerts-alert-thresholds -->
```bash
<!-- /WIKI:GENERATED -->

---

# Fire BACKEND_DOWN after this many consecutive failures per backend (default: 3)

<!-- WIKI:GENERATED unit=unit-alerts-fire-backend-down-after-this-many-consecutive-failures-per-backend-default-3 -->
ALERT_BACKEND_DOWN_THRESHOLD=3
<!-- /WIKI:GENERATED -->

---

# Fire ALL_BACKENDS_DOWN immediately when all backends fail (default: true)

<!-- WIKI:GENERATED unit=unit-alerts-fire-all-backends-down-immediately-when-all-backends-fail-default-true -->
ALERT_NO_HEALTHY_BACKENDS=true
```
<!-- /WIKI:GENERATED -->

---

## Daily Summary

<!-- WIKI:GENERATED unit=unit-alerts-daily-summary -->
```bash
<!-- /WIKI:GENERATED -->

---

# Enable/disable daily summary (default: true)

<!-- WIKI:GENERATED unit=unit-alerts-enable-disable-daily-summary-default-true -->
ALERT_SUMMARY_ENABLED=true
<!-- /WIKI:GENERATED -->

---

# Hour to send summary (0-23, .env.example default: 8, code fallback: 9)

<!-- WIKI:GENERATED unit=unit-alerts-hour-to-send-summary-0-23-default-8 -->
ALERT_SUMMARY_HOUR=8               # .env.example ships 8 (8am CST); if unset entirely, the
                                    # code falls back to 9 (scheduler.py: `os.environ.get("ALERT_SUMMARY_HOUR", "9")`)
<!-- /WIKI:GENERATED -->

---

# Timezone for the schedule (default: UTC)

<!-- WIKI:GENERATED unit=unit-alerts-timezone-for-the-schedule-default-utc -->
ALERT_SUMMARY_TIMEZONE=UTC
```
<!-- /WIKI:GENERATED -->

---

## Channel Priority

<!-- WIKI:GENERATED unit=unit-alerts-channel-priority -->
All channels receive the same events simultaneously. To avoid duplicate alerts in
Slack/Telegram, use separate bots or filter with channel rules.
<!-- /WIKI:GENERATED -->

---

## Troubleshooting

<!-- WIKI:GENERATED unit=unit-alerts-troubleshooting -->
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
<!-- /WIKI:GENERATED -->

---

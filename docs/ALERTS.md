# Portal 5.2 — Alerts & Notifications Guide

Portal 5 can send operational alerts and daily usage summaries to Slack, Telegram,
Email, and Pushover. Notifications are disabled by default.

## Quick Start

```bash
# 1. Enable notifications
echo "NOTIFICATIONS_ENABLED=true" >> .env

# 2. Configure one or more channels (see below)
# 3. Restart the pipeline
docker compose restart portal-pipeline
```

## Operational Alerts

Fired immediately when a threshold is crossed:

| Event | Trigger | Debounce |
|-------|---------|----------|
| `backend_down` | A backend fails `ALERT_BACKEND_DOWN_THRESHOLD` consecutive health checks | Yes — one alert per transition |
| `backend_recovered` | A previously-down backend passes a health check | Yes — one alert per transition |
| `all_backends_down` | Every backend is unhealthy simultaneously | Yes — fires once, clears on any recovery |
| `config_error` | `backends.yaml` missing or unparseable | No debounce |

## Daily Usage Summary

Fired once per day at a configured hour. Contains:
- Total requests since last summary
- Requests broken down by workspace
- Number of healthy backends
- Process uptime

## Configuration

### Slack

1. Create an Incoming Webhook at [https://api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Copy the webhook URL (e.g. `https://hooks.slack.com/services/...`)

```bash
echo "SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" >> .env
echo "SLACK_ALERT_CHANNEL=#portal-alerts" >> .env
```

### Telegram

1. Create a **dedicated alert bot** via [@BotFather](https://t.me/BotFather) — keep it separate from your user-facing bot
2. Add the bot to your target channel as an admin
3. Get your channel ID — forward a message from the channel to [@userinfobot](https://t.me/userinfobot)

```bash
echo "TELEGRAM_ALERT_BOT_TOKEN=123456789:ABCdef... >> .env
echo "TELEGRAM_ALERT_CHANNEL_ID=-1001234567890" >> .env
```

### Email

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

### Pushover

1. Sign up at [https://pushover.net](https://pushover.net)
2. Create an application to get your API token
3. Find your user key on your dashboard

```bash
echo "PUSHOVER_API_TOKEN=your-app-token" >> .env
echo "PUSHOVER_USER_KEY=your-user-key" >> .env
```

## Alert Thresholds

```bash
# Fire BACKEND_DOWN after this many consecutive failures per backend (default: 3)
ALERT_BACKEND_DOWN_THRESHOLD=3

# Fire ALL_BACKENDS_DOWN immediately when all backends fail (default: true)
ALERT_NO_HEALTHY_BACKENDS=true
```

## Daily Summary

```bash
# Enable/disable daily summary (default: true)
ALERT_SUMMARY_ENABLED=true

# Hour to send summary (0-23, default: 9)
ALERT_SUMMARY_HOUR=9

# Timezone for the schedule (default: UTC)
ALERT_SUMMARY_TIMEZONE=UTC
```

## Channel Priority

All channels receive the same events simultaneously. To avoid duplicate alerts in
Slack/Telegram, use separate bots or filter with channel rules.

## Troubleshooting

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

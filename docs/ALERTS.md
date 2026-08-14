# Portal 6.0.0 — Alerts & Notifications Guide

The notification layer offers five independently configurable channels — Slack, Telegram, Email, Pushover, and Webhook — all fed by a single dispatcher. Operational alerts fire on backend health transitions, and a daily usage summary runs once per day on a schedule. The whole subsystem stays off until `NOTIFICATIONS_ENABLED` is true, and channels only register when the master switch is on, so the default install sends nothing anywhere.

## Why

A single dispatcher fanning out to pluggable channels keeps delivery consistent across very different providers while making each one optional, so a stack that only uses email never has to think about Telegram. Disabled-by-default preserves the project's zero-config promise and forces an explicit choice before any external endpoint receives traffic.

---

## Quick Start

Enabling alerts is a three-step process: set `NOTIFICATIONS_ENABLED` to true in `.env`, add at least one channel's variables, and restart the pipeline so the values are read at startup. To verify without waiting for an incident, POST to the `/notifications/test` endpoint, which dispatches a sample alert and a live summary and reports each channel's configured state in the response.

## Why

A test endpoint exists because alert wiring has too many silent-failure modes — bad tokens, unreachable endpoints, malformed headers — and discovering them during a real outage is the worst possible time. An explicit verification step turns configured from a hope into a checkable state before an operator walks away.

---

# 1. Enable notifications

Notifications are disabled by default. The dispatcher reads `NOTIFICATIONS_ENABLED` at construction and refuses to register any channel while it is false, and the pipeline lifespan never even imports the notifications package unless the variable is truthy. Setting it to true in `.env` and restarting the pipeline container activates the subsystem; every channel is then independently optional, and a channel without its own variables stays silent.

## Why

A master switch means an operator who wants only Slack does not have to reason about five separate toggles, and a misconfigured channel cannot take the whole subsystem down at registration time. Disabled-by-default keeps a zero-config install quiet, so the first alert an operator sees is one they explicitly opted into rather than surprise traffic to an external service.

---

# 3. Restart the pipeline

The notification subsystem reads its entire configuration from environment variables during process startup, so editing `.env` has no effect until the pipeline container is recreated. The compose file at deploy/portal-5/docker-compose.yml defines the service as `portal-pipeline` and forwards every alert variable, so `docker compose restart portal-pipeline`, run from the compose directory, is the documented refresh path; `./launch.sh up` also recreates containers whose configuration changed.

## Why

Because the dispatcher, scheduler, and channels bind their values once at lifespan startup, there is no hot-reload path; a restart is the only way to apply a new webhook URL or token. Calling the exact command out prevents operators from editing environment files, seeing nothing change, and assuming the alert layer is broken when it simply has not been restarted.

---

## Operational Alerts

Four alert events model the operational surface. `backend_down` and `backend_recovered` are transition pairs driven by the consecutive-failure counter. `all_backends_down` latches until any backend becomes healthy again. `config_error` is dispatchable through `check_config_error` but no call site invokes it today, so a missing or unparseable backends.yaml produces no alert. All events flow from the same threshold check that the health loop invokes after each cycle.

## Why

The event set matches what a stateless router can actually observe: per-backend and whole-fleet health transitions. Keeping the config error event available but unwired reflects that the pipeline currently fails loudly at startup instead of alerting, and stating that gap matters more than pretending a table row is exercised code.

---

## Daily Usage Summary

The summary payload is a fixed field set. `SummaryEvent` carries `total_requests` and `requests_by_workspace` computed as deltas from the prior day's snapshot, plus `healthy_backends`, `total_backends`, and `uptime_seconds`. Extended figures such as token counts, average tokens per second, average response time, and errors by type ride along, and each channel renders the same event differently. Two guards skip the send when persisted state was wiped by a container recreation, so an empty first report never masquerades as a quiet day.

## Why

The field set is deliberately small and identical across channels so any receiver can parse the same summary in Slack, email, or raw JSON without special casing. Delta computation keeps the totals truthful for the reporting window, and the restart guards are the practical consequence of running counters that must survive process restarts to be useful.

---

### Slack

Slack delivery rides on an Incoming Webhook URL. `SLACK_ALERT_WEBHOOK_URL` is required; `SLACK_ALERT_CHANNEL` defaults to `#portal-alerts` and is included in the message payload so a webhook pinned to one channel can still be overridden. Both alerts and summaries POST a single text block formatted by the event's Slack renderer, which prefixes each event type with an emoji marker.

## Why

Incoming webhooks are the lowest-friction Slack integration and match the credential-light posture of the rest of the alert layer. Emitting a plain text payload keeps the transport independent of message content, so a future change to the renderer never requires receivers to change, and the default channel keeps configuration to a single required variable.

---

### Telegram

Telegram accepts either dedicated alert credentials or the main bot variables: `TELEGRAM_ALERT_BOT_TOKEN` and `TELEGRAM_ALERT_CHANNEL_ID` take precedence, falling back to `TELEGRAM_BOT_TOKEN` and `TELEGRAM_USER_IDS`, where a comma-separated list uses its first entry. Messages POST to the bot's `sendMessage` method with Markdown parse mode, and a dedicated alert bot is recommended so operational noise never mixes with user-facing chat.

## Why

The two-variable fallback lets a deployment reuse an existing Telegram bot when no one wants to stand up a second one, while the dedicated alert variables still allow clean separation between operational noise and user chat. Relying on the bot sendMessage API rather than a channel webhook keeps configuration to just a token and a chat identifier.

---

### Email

The email channel requires `SMTP_HOST` and `EMAIL_ALERT_TO`; it also reports unconfigured when the aiosmtplib dependency is not importable. `SMTP_PORT` defaults to 587 and `SMTP_FROM` to portal@portal.local. Port 465 selects implicit TLS with a default security context; any other port enables STARTTLS. Username and password are optional and are only sent when provided.

## Why

Two transport modes exist because providers split between implicit TLS on port 465 and STARTTLS on 587, and a single send path cannot serve both. Making the recipient mandatory and the credentials optional keeps the channel usable for an internal relay while still supporting authenticated providers such as Gmail, whose two-factor users need an app password.

---

### Pushover

Pushover requires both `PUSHOVER_API_TOKEN` and `PUSHOVER_USER_KEY`; either missing and the channel stays silent. Alerts post to the Pushover messages endpoint with a title prefixed by the event type, and priority escalates to high only for `backend_down`, `all_backends_down`, and `config_error`; recoveries and summaries send at normal priority. Message bodies are truncated to 512 characters to satisfy the service limit.

## Why

The high-priority mapping encodes that only genuine outages deserve Pushover's urgent sound while routine recoveries and the daily report stay quiet. Truncation exists because the service rejects longer bodies, and the channel deliberately reuses the shared HTTP client rather than opening its own connection pool.

---

### Webhook

The webhook channel POSTs a JSON body to any URL given by `WEBHOOK_URL`, which is required and must be a real value rather than the literal string false. Alerts and summaries use the same transport and differ only in the fields they post. `WEBHOOK_HEADERS` supports bearer-token receivers, content type is always application/json with a Portal user agent, and the HTTP timeout is fixed at ten seconds.

## Why

A generic webhook is the escape hatch of the alert layer: PagerDuty, SIEM collectors, and custom bots all speak inbound JSON POST, so one channel covers receivers no dedicated integration would. A short fixed timeout keeps a dead endpoint from hanging the dispatch task, while raising on HTTP errors surfaces delivery failures into the pipeline log.

---

# Optional: JSON object for additional headers (e.g. auth tokens)

`WEBHOOK_HEADERS` lets a webhook receiver demand authentication. The channel parses the variable as JSON, merges the result into a base header set that already carries `Content-Type: application/json`, and logs a warning and skips the merge when the value is not valid JSON — the request still proceeds without the extra headers. The alert payload posted by `send_alert` includes event, message, backend id, workspace, timestamp, and metadata; the summary payload additionally includes request totals, per-workspace counts, backend health, uptime, and extended metrics.

## Why

Header injection exists because many inbound-webhook targets such as PagerDuty authenticate with a bearer token rather than a shared secret URL. Treating malformed JSON as a soft failure keeps a typo in configuration from silently blocking alert delivery, and the documented payload shape is the contract a custom receiver must parse.

---

## Alert Thresholds

Two behaviors govern when operational alerts fire. `ALERT_BACKEND_DOWN_THRESHOLD`, default three, counts consecutive unhealthy health cycles before a per-backend down event fires; the health loop runs roughly every thirty seconds. The all-backends-down alert is not tunable: the threshold checker always runs with `alert_all_down` true, and the `ALERT_NO_HEALTHY_BACKENDS` variable shipped in `.env.example` and forwarded by compose is never read by any code, so it has no effect.

## Why

Thresholds exist to suppress flapping: a single missed health check should not page anyone, and firing only at the transition boundary keeps alert volume bounded. The dead all-backends-down toggle deserves documentation precisely because it looks authoritative while the hardcoded default in the checker is what actually governs the whole-fleet path.

---

# Fire BACKEND_DOWN after this many consecutive failures per backend (default: 3)

`ALERT_BACKEND_DOWN_THRESHOLD` defaults to three consecutive failures. On every health-cycle callback the dispatcher bumps a per-backend failure counter for each unhealthy check and fires `backend_down` only when the counter equals the threshold; a healthy check resets the counter, and if the threshold had previously been reached it also emits `backend_recovered`. Resetting on recovery is what makes each alert fire once per transition rather than on every check.

## Why

Counting consecutive failures rather than firing on the first missed check absorbs the transient blips a warm model or a busy Ollama can produce. Firing exactly at the threshold and resetting on recovery bounds message volume to one per state change, which keeps a genuinely failing backend identifiable without drowning every channel in duplicate alerts.

---

# Fire ALL_BACKENDS_DOWN immediately when all backends fail (default: true)

The all-backends-down alert fires the first time a health cycle finds every registered backend unhealthy, and only once: the `_alerted_all_down` latch holds until any backend recovers, then clears. Notably, `ALERT_NO_HEALTHY_BACKENDS` — the variable documented in `.env.example` and forwarded by the compose service — is never read anywhere; the checker's `alert_all_down` parameter defaults to true and the lifespan health callback always invokes it that way. Behavior is therefore fixed, not configurable.

## Why

A total outage is an emergency and should not wait for a debounce window or a configurable count, so the event is deliberately hardcoded on. Latching until recovery stops the thirty-second health loop from flooding channels with identical messages, and the inert variable is called out here so no operator trusts a toggle that silently does nothing.

---

## Daily Summary

The daily summary is a scheduled job rather than a threshold event. The scheduler registers `_send_daily_summary` on an APScheduler `CronTrigger` at the configured hour and timezone, and the job only exists when APScheduler is importable and `ALERT_SUMMARY_ENABLED` is truthy. The report is built from deltas against a persisted snapshot, so it describes the previous day's activity instead of cumulative totals since the container started.

## Why

Summaries are time-triggered, not threshold-triggered, because they report a trailing window of pipeline health rather than an anomaly that needs immediate attention. A cron trigger at a fixed local hour keeps delivery predictable for whoever reads it, and snapshot-based deltas keep the headline number honest about the reporting window regardless of when the pipeline last restarted.

---

# Enable/disable daily summary (default: true)

`ALERT_SUMMARY_ENABLED` gates the scheduler independently of the alert path. When the variable is false, the scheduler logs that summaries are disabled via env and never registers the cron job; when it is unset entirely, the code defaults to true. The gate stacks on top of the master `NOTIFICATIONS_ENABLED` switch, so both must be truthy for a summary to actually be dispatched.

## Why

The summary is the one notification operators routinely want to silence without disabling urgent alerts, so it earns its own gate. Defaulting to true preserves out-of-the-box behavior for anyone who only flipped the master switch, while the stacked arrangement keeps the scheduler a strict subset of the dispatcher's overall enablement.

---

# Hour to send summary (0-23, .env.example default: 8, code fallback: 9)

`ALERT_SUMMARY_HOUR` selects the hour at which the daily summary fires; the scheduler plugs it into a `CronTrigger` with the minute fixed at zero. The example environment ships 8 and the compose service forwards a default of 8, so the effective send time is eight in the configured timezone. Only if the variable is stripped entirely does the in-process fallback of nine apply, which is why the shipped default and the code default differ.

## Why

Two defaults exist because the shipped environment and the code's resilience are different concerns: compose always injects a value, making the runtime default mostly theoretical, while the code fallback of nine exists only so the scheduler still runs when the variable is absent. Documenting both prevents confusion when a log shows an unexpected send hour.

---

# Timezone for the schedule (default: UTC)

`ALERT_SUMMARY_TIMEZONE` names the tzinfo passed to the summary cron trigger. The example environment and the compose service both ship `America/Chicago`, so the shipped default hour of eight means eight in the morning Central time, while the in-process fallback is UTC when the variable is absent. Changing the value shifts the send moment without altering the hour number.

## Why

Scheduling in a named timezone rather than a fixed UTC offset matters because offset changes are what break a same-local-time-every-day promise across daylight saving transitions. Shipping the operator's own local zone as the example default makes the summary arrive at a genuinely convenient hour with no further configuration.

---

## Channel Priority

There is no priority ladder and no ordered fan-out. `dispatch` gathers every registered channel into a single `asyncio.gather` call with `return_exceptions`, so Slack, Telegram, Email, Pushover, and Webhook all receive an event at the same moment, and a slow or failed receiver is isolated from the others. Because every configured channel sees every event, deduplication is left to the operator rather than built into the dispatcher.

## Why

Fanning out concurrently rather than sequentially keeps an unresponsive endpoint from delaying the other four channels, and fire-and-forget send means a notification failure can never fail a chat request. The absence of priority is deliberate: an alert is either worth sending or not, so operators who want fewer messages simply omit the channels they do not need.

---

## Troubleshooting

Debugging follows the enablement chain. If nothing arrives, confirm `NOTIFICATIONS_ENABLED` is true, that the pipeline was restarted after the environment changed, then POST `/notifications/test` for per-channel config status. For webhooks verify `WEBHOOK_URL` accepts a JSON POST and that `WEBHOOK_HEADERS`, when set, parses; malformed JSON is logged and ignored. Email requires the port to match the provider, 587 for STARTTLS and 465 for SSL. The daily summary no longer resets on restart: metrics persist to `/app/data/metrics_state.json` every sixty seconds and the delta snapshot lives beside it, with guards that skip an empty first-day report.

## Why

Every failure mode here traces back to a small set of causes: environment not read, endpoint unreachable, or a restart gap. Because the summary reads persisted state rather than pure memory, the older advice that a restart between midnight and summary time zeroes the numbers is no longer accurate, and correcting it prevents operators from chasing a phantom reset.

---

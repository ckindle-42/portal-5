---
id: unit-channels-telegram-adapter
kind: mixed
title: "Telegram channel adapter \u2014 bounded-history pipeline bridge"
sources:
- type: code
  path: portal_channels/telegram/bot.py
  commit: c23c27d9
claims: []
confidence: high
tags:
- authored-v1
- channels
- telegram
created_at: 1785795189.416028
updated_at: 1785795189.416028
---

The Telegram channel adapter is the messenger front door to the pipeline:
it forwards messages to the pipeline and streams the response back, with a
per-user workspace selector and bounded conversation history. Like the Slack
adapter it is deliberately thin — no routing logic lives here — but it carries
more user-facing state than Slack because Telegram's bot API is inherently
conversational.

## Why

The workspace selector and history live in `context.user_data` per chat, and
the history is bounded by a sliding window of the newest 20 messages *and* a
24-hour age cutoff, applied together. The dual constraint is the answer to an
always-on bot with sparse users: count alone would keep a month-old
conversation alive, and age alone would truncate a long active session. The
timestamps fallback path exists because a session started before the
timestamp feature was added has a shorter timestamps list than history list,
and a strict `zip` would raise — so count-only eviction covers the legacy
shape. User filtering via `TELEGRAM_USER_IDS` (empty means allow everyone) is
the admission control that Slack's workspace model does not need.

## Interfaces

`/start`, `/clear`, `/workspace`, and `/workspaces` are the commands, and the
plain-message handler does the work: it checks `_is_allowed`, appends the user
text to history, applies the window+age eviction, sends a typing action, calls
`call_pipeline_async` with the trimmed history, and chunks the reply under the
4000-character Telegram limit with a Markdown-then-plain fallback.

## Gotchas

The 24h eviction sorts newest-first before truncation, so within the 20-message
window the *oldest* messages drop first — not the least-recent in arrival
order after a burst. The Markdown fallback exists because Telegram's parser
rejects unmatched `*`, `_`, and backticks that a model may emit.

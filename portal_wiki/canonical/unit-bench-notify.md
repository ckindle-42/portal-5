---
id: unit-bench-notify
kind: mixed
title: "Bench notify \u2014 fire-and-forget completion pings"
sources:
- type: code
  path: tests/benchmarks/bench/notify.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798440.6652448
updated_at: 1785798440.6652448
---

`notify.py` is the fire-and-forget bench notification helper: it sends
Pushover, Telegram, or Slack notifications when a bench run completes, so an
operator does not need to watch the terminal.

## Why

A long TPS bench is exactly the kind of job an operator starts and walks
away from, and the notification is what makes that safe — the completion
signal arrives on the operator's channel instead of requiring them to poll.
Fire-and-forget is the deliberate contract: a notification failure must never
fail the bench, because the measurement's value is independent of whether the
completion ping arrived.

## Interfaces

The notification functions for the three channels, reading credentials from
the environment like the notification subsystem's channels.

## Gotchas

The fire-and-forget discipline means a misconfigured notification channel is
silently skipped — the operator may not learn a channel is broken until a
run completes without a ping.

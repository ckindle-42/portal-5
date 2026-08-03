---
id: unit-notifications-events
kind: mixed
title: "Notification events \u2014 typed alert/summary vocabulary"
sources:
- type: code
  path: portal/platform/inference/notifications/events.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796457.06321
updated_at: 1785796457.06321
---

`events.py` defines the notification event types — `EventType` enum plus the
`AlertEvent` and `SummaryEvent` dataclasses that every channel consumes. It is
the vocabulary the dispatcher and channels share.

## Why

The event types are the contract between the producers (health checks, the
bench loop) and the consumers (channels). Backend-down, recovered, all-down,
config-error, daily-summary, and the loop-engagement events exist because each
needs a distinct rendering and a distinct severity, and a single free-form
message would force every channel to parse meaning out of text. The events
carry structured fields so a channel can format them without string-sniffing.

## Interfaces

`EventType` enumerates the kinds; `AlertEvent` carries the alert details and
`SummaryEvent` the daily usage numbers; the module also supplies the HTML
escaping helper used when events are rendered into channel payloads.

## Gotchas

A new event type must be added here first — a producer that invents an
informal notification shape bypasses the typed contract and would be silently
unrenderable by the channels.

---
id: unit-tests-lib-stream-wait
kind: mixed
title: "Tests lib stream-wait \u2014 event-driven streaming wait"
sources:
- type: code
  path: tests/lib/stream_wait.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798254.002919
updated_at: 1785798254.002919
---

`stream_wait.py` is the event-driven streaming wait shared across the bench,
UAT, and acceptance harnesses. Its design treats the wall-clock timeout as a
ceiling, not the primary driver: a generation is judged healthy or stuck by
actionable events — the inter-token idle gap and the model-loaded signal —
rather than elapsed time.

## Why

A generation that produces tokens every three seconds is healthy even at 90
seconds, and a generation that goes silent at two seconds is stuck — a
wall-clock timeout alone cannot tell the difference, and timing-based waits
are exactly the "works locally, fails CI" trap this project pays to avoid.
The idle-gap detection is implemented natively via
`httpx.Timeout(read=idle_gap_s)`: httpx raises `ReadTimeout` when no bytes
arrive within the read window, so detecting a silent model costs nothing
extra. The model-loaded event covers the pre-first-token period where a cold
model legitimately takes time to load without any bytes flowing.

## Interfaces

The wait API takes the stream and the event thresholds and returns when the
generation completes or the idle/loaded signals say it is stuck.

## Gotchas

The idle gap is the *primary* signal — a harness that disables it and waits
on the ceiling alone re-introduces the timing-based flakiness this module
exists to remove.

---
id: unit-corpus-injection-confirm-the-live-triage-window-is-still-clean
kind: what
title: "corpus_injection \u2014 confirm the live triage window is still clean"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/blue_triage.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.58561
updated_at: 1784946220.58561
---

The point of backdating is that injected corpus events never surface as live
alerts in the bench's triage path. `blue_triage.poll_alerts` polls with
`earliest=-{since_minutes}m` and defaults `since_minutes` to 5, so any event
stamped near ship time would be picked up as a live alert and pollute a
concurrent bench run. Corpus events avoid that window because `event_epoch`
prefers the original event timestamp, and events with no recoverable timestamp
fall back to a backdated stamp from `--backdate-days` (default 30) rather than
ship time.

```spl
index=portal5_lab earliest=-60m evidence_origin=corpus:* | stats count
```

A non-zero count means corpus events are landing close enough to ship time to
appear in triage, and the backdate logic or the source timestamps need
attention before any bench run proceeds.

## Why

An injection that "works" at index time but lands inside the live triage
window silently corrupts every subsequent bench run's alert set. The confirm
query is the cheap check that backdating held: it should return zero while the
corpus still shows data at `earliest=0`. Keeping those two views honest is what
lets corpus and bench data share one index safely.

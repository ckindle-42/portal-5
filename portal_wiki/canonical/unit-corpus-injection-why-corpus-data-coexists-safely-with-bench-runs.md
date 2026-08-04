---
id: unit-corpus-injection-why-corpus-data-coexists-safely-with-bench-runs
kind: what
title: "corpus_injection \u2014 Why corpus data coexists safely with bench runs"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
- type: code
  path: portal/modules/security/core/siem/blue_triage.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.581862
updated_at: 1784946220.581862
---

Lane B writes into the same `portal5_lab` index the bench uses. Three properties
keep the two from contaminating each other — all three are enforced in
`scripts/corpus_ingest.py` and verifiable after any injection:

1. **Backdating.** Every event ships with its original timestamp via
   `ship_batch(..., event_time=...)`. Corpus events therefore land far outside
   `blue_triage.poll_alerts`' recent `earliest=-5m` default window and never
   appear as live alerts. Events with no recoverable timestamp are backdated by
   `--backdate-days` (default 30) in `event_epoch`'s fallback rather than
   defaulting to ship time.
2. **No `episode_id`.** Episode-scoped bench scoring queries
   (`SplunkBackend.query_episode`) filter on the indexed `episode_id` field.
   Lane B ships corpus events with none, so they can never enter a bench
   episode's score. Lane C events *do* carry one (the Caldera operation id) —
   by design, so blue and purple can consume them exactly like bench telemetry.
3. **Provenance.** `evidence_origin` is `corpus:<src>:<label>` or
   `live:caldera:<profile>`, which makes every injected event attributable and
   the whole injection reversible in one search.

## Why

The three properties exist because corpus data and bench data cannot be allowed
to affect each other's ground truth: a backdated event must not become a live
alert, an untagged event must not enter a scored episode, and an
unattributable event cannot be rolled back. Encoding all three in the loader at
ship time — rather than relying on the consuming side to filter — is what makes
a single shared index safe.

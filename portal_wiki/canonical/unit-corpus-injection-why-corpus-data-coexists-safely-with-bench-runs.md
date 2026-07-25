---
id: unit-corpus-injection-why-corpus-data-coexists-safely-with-bench-runs
kind: what
title: "corpus_injection \u2014 Why corpus data coexists safely with bench runs"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: Why corpus data coexists safely with bench runs
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.581862
updated_at: 1784946220.581862
---

Lane B writes into the same `portal5_lab` index the bench uses. Three properties
keep the two from contaminating each other — all three are asserted in
`scripts/corpus_ingest.py` and verifiable after any injection:

1. **Backdating.** Every event ships with its original timestamp via
   `ship_batch(..., event_time=...)`. Corpus events therefore land far outside
   `blue_triage.poll_alerts`' recent `earliest=-Nm` window and never appear as
   live alerts. Events with no recoverable timestamp are backdated by
   `--backdate-days` (default 30) rather than defaulting to ship time.
2. **No `episode_id`.** Episode-scoped bench scoring queries
   (`SplunkBackend.query_episode`) filter on the indexed `episode_id` field.
   Corpus events carry none, so they can never enter a bench episode's score.
   Lane C events *do* carry one (the Caldera operation id) — by design, so blue
   and purple can consume them exactly like bench telemetry.
3. **Provenance.** `evidence_origin` is `corpus:<src>:<label>` or
   `live:caldera:<profile>`, which makes every injected event attributable and
   the whole injection reversible in one search.

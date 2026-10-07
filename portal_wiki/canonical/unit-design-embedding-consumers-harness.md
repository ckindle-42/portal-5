---
id: unit-design-embedding-consumers-harness
kind: mixed
title: "EmbeddingGemma 2 per-consumer measurement harness"
sources:
- type: code
  path: tests/benchmarks/embedding_consumers/__init__.py
- type: code
  path: tests/benchmarks/embedding_consumers/__main__.py
- type: code
  path: tests/benchmarks/embedding_consumers/cli.py
- type: code
  path: tests/benchmarks/embedding_consumers/framework.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/__init__.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/attack_mapping.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/router.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/tool_preselect.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/wiki_search.py
claims: []
confidence: high
tags:
- design
- embedding
- benchmark
created_at: 1791388900
updated_at: 1791388900
---

# EmbeddingGemma 2 per-consumer measurement harness

## What

`python -m tests.benchmarks.embedding_consumers --all --live` runs one probe per ledger consumer
(`framework.CONSUMERS`). Each probe compares the incumbent path (the real code where possible) with the
candidate (EmbeddingGemma 2 through `portal.platform.embedding`) on one fixture and returns `MEASURED` with
`incumbent.primary`/`candidate.primary`, or `BLOCKED` with a concrete reason. `hint` is advisory input to the
Phase-4 gates of `coding_task/TASK_EMBEDDINGGEMMA2_PLATFORM_V1.md`; the harness never decides adoption.
The Phase-3 gate passes when every consumer is MEASURED or BLOCKED-with-reason. Results land in
`reports/embedding_consumers/<stamp>/` (`results.json`, `SCORECARD.md`).

## Why

Fixtures live under `tests/data/embedding_consumers/` and follow the no-leakage, key-independent,
paraphrase-overlap and provenance rules from the task file; a probe with leakage is BLOCKED. The harness exists because the migration decision is per consumer and
evidence-based: each consumer is adopted, rejected or deferred only after its own measured comparison, so a
single shared yardstick keeps the incumbent and the candidate on identical inputs.

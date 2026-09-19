---
id: unit-surface-compliance-prove-then-scale-scripts
kind: mixed
title: "PROVE_THEN_SCALE_V1 campaign scripts — the sweep, the controls, the repair"
sources:
- type: code
  path: scripts/prove_then_scale/*.py
---

The PROVE_THEN_SCALE_V1 campaign's one-off scripts (report:
`reports/compliance/PROVE_THEN_SCALE_V1.md`), kept for provenance:

* `p1_experiment.py` — the three-seat × six-case proof: one message, one
  call, no tools; cells and judgments under
  `reports/compliance/prove_then_scale/p1/`.
* `p1_seat_failure_controls.py` — the failure-attribution controls: same
  questions over minimal material, separating long-material comprehension
  (Nemotron) from reading-level failure (Ling).
* `p4_cache_sweep.py` — the twenty-call `prompt_eval_duration` measurement
  over CIP-007-6; also the real CIP-007-6 sweep.
* `p5_review_surfaces.py` — generates the contradiction queue, a drill-down
  example, and the stratified sample packet.
* `p7_family_sweep.py` — the family sweep in dependency order, resumable per
  revision, one JSON of per-standard rows.
* `repair_derivation_columns.py` — the one-time, verified repair after the
  migration-17 table rebuild dropped four columns; re-runnable, exits 0 on an
  already-repaired store.

These are campaign instruments, not product callers: the complexity census
counts them as unwired scripts deliberately (see `config/complexity_budget.yaml`).

## Why

Campaign instruments must stay on the record: every number in the
report traces to a script that produced it, and the store repair is
re-runnable proof rather than a promise. They are one-off tools by
design — the product surface is the sweep module, not these.

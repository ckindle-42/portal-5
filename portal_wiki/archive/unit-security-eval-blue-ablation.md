---
id: unit-security-eval-blue-ablation
kind: mixed
title: "Blue orchestration ablation \u2014 GATE-D 1-vs-2-vs-3-section driver"
sources:
- type: code
  path: portal/modules/security/eval/blue_orchestration_ablation.py
  commit: 1d62c01d
last_generated_commit: 1d62c01d
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- eval
created_at: 1785795987.504139
updated_at: 1785795987.504139
---

`blue_orchestration_ablation.py` is the GATE-D full-corpus ablation driver:
it runs three arms (one-section discovery, two-section, and the locked
three-section V2 trio) across the whole captured corpus in replay mode with no
live red, classifies each outcome via `ablation_attribution.classify`,
aggregates, and emits `ABLATION_DECISION.json` plus a human report. It runs
sequentially by design and checkpoints per scenario so a mid-corpus failure
does not lose completed work.

## Why

The ablation answers the question that gates the council design: does the
three-section split of the blue orchestration actually beat one and two
sections, on real traces, with real attribution? Several constraints encode
hard-won lessons. Sequential-only is non-negotiable because concurrent
bench/eval runs contend for VRAM and evict models, producing data that looks
like an effect but is actually contention. Per-scenario checkpointing exists
because a 566-line harness that loses a full corpus on one crash teaches the
operator to never trust its output. And `--rescore` is explicitly *not*
independent confirmation — rescoring the same raw JSONL with a changed
scorer is development data, so the docstring says so rather than letting a
re-scored decision masquerade as a fresh run.

## Interfaces

`main` drives the whole run with `--reps` and `--replay-captured-red`; the
`_run_*_raw` helpers execute each arm and persist raw per-rep records to a
JSONL sidecar; `_build_decision` and `_decide_honest_blocked` assemble the
routing decision; `_write_report` renders the human-readable output.

## Gotchas

Legacy schema-v1 multi-section traces omitted returned tool content and are
classified `ATTRIBUTION_UNKNOWN` rather than retrospectively forced into a
causal retrieval or handoff class — a deliberate refusal to fabricate an
attribution the trace cannot support. The raw JSONL sidecar is what makes
`--rescore` possible at all.

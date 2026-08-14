---
id: unit-surface-security-eval
kind: mixed
title: "Security eval subpackage \u2014 bench-facing re-export boundary and ablation instrumentation"
sources:
- type: code
  path: portal/modules/security/eval/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- eval
created_at: 1785881000.0
updated_at: 1785881000.0
---

The eval subpackage is the public re-export boundary the security bench
harnesses consume: the RBP engine's eval code lives in `core/`, and this
facade exposes the stable entry points (`run_eval`, `candidate_eval_main`,
`rescore`, the blue-detection scorers) so a campaign supervisor, UAT driver,
or operator script never reaches into the moving internals. Beside the facade
sit the two ablation instruments that decide whether the three-section blue
orchestration actually beats one and two sections on real traces.

## Why

The facade exists because core internals may be reorganised freely as long as
this boundary keeps serving the same entry points — the same discipline as
the knowledge surface. The ablation instruments exist because the council
design is gated on a measured question: does the split win on real traces with
real attribution? Three constraints encode hard-won lessons. Ablation runs are
sequential-only, because concurrent bench/eval runs contend for VRAM and evict
models, producing data that looks like an effect but is actually contention.
Per-scenario checkpointing exists because a harness that loses a full corpus
on one crash teaches the operator to never trust its output. And `--rescore`
is explicitly not independent confirmation — rescoring the same raw JSONL with
a changed scorer is development data, so the decision never masquerades as a
fresh run.

## Interfaces

`classify` and `summarize` produce per-arm scenario outcomes and aggregates
from persisted plain dicts; `decide_route` returns the routing decision using
the Wilson lower bound so an arm's edge must be statistically stable rather
than a single lucky run; `_write_report` renders the human output.

## Gotchas

The attribution instrument is hermetic — it operates on persisted plain dicts
with no live calls, and fixture coverage establishes implementation behaviour
only, never validity on live traces. The attribution schema is versioned so a
scorer change is tracked, not silently applied to old results. Legacy
schema-v1 traces that omitted returned tool content are classified
`ATTRIBUTION_UNKNOWN` rather than forced into a causal class — the absence of
evidence is not evidence of absence, and fabricating an attribution the trace
cannot support is the one failure mode this subsystem refuses.

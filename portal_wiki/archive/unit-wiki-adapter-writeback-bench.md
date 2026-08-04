---
id: unit-wiki-adapter-writeback-bench
kind: mixed
title: "Wiki bench write-back \u2014 model-verdict units"
sources:
- type: code
  path: portal/platform/wiki/adapters/writeback_bench.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797599.883532
updated_at: 1785797599.883532
---

The bench write-back adapter writes candidate-eval and multi-seat bench
results into the wiki as cited model-knowledge units — a model verdict from a
bench run becomes a unit an agent can cite, through the same confirm-gated
propose path the other write-backs use.

## Why

A bench verdict kept only in a results JSON is invisible to the agents that
query the spine; written back as a unit, it is discoverable and citable. The
confirm gate matters because a model-knowledge unit is a claim about a model,
and a bench run's verdict should be inspected before it becomes canonical —
`auto_confirm` exists for harnesses that have already earned trust, but the
default is a human-visible proposal.

## Interfaces

`writeback_bench_result(model, seat, verdict, delta, result_path, auto_confirm)`
proposes the unit and returns the result.

## Gotchas

The verdict vocabulary (keep/promote/reject) is the bench's own — the adapter
records it, it does not reinterpret it.

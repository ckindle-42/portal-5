---
id: unit-archive-v5-ladder-analysis
kind: mixed
title: "V5 ladder bench analyser \u2014 archived promotion decision input"
sources:
- type: code
  path: scripts/_archive/analyze_bench_v5.py
  commit: c23c27d9
last_generated_commit: c23c27d9
claims: []
confidence: high
tags:
- authored-v1
- archive
- bench
created_at: 1785795219.1676888
updated_at: 1785795219.1676888
---

This V5 ladder-bench analyser is archived, not live: it was the operator's
decision input for the V5 workspace promotion task, and it now records what
was tried and retired rather than serving the current bench pipeline. Its
job was to turn three inputs — measured TPS ladders, the backends catalog,
and smoke-test results — into a per-workspace markdown report with Pareto
frontiers for the promotion decision.

## Why

Archival is the point of this unit. The V5 bench pipeline was superseded,
and a live reader would misread this file as current tooling when it consumes
`tests/benchmarks/results/bench_tps_v5_ladders.json` — a path the V9 pipeline
no longer produces. Keeping the file and describing it as retired preserves
the decision trail (which models won which workspace slots and why) without
implying the script still runs. The `workspace_for` substring map and the
`WORKSPACE_LADDER_MAP` encode a snapshot of the V5 catalog's workspace
groupings, including the `auto-security/redteam` split that the collapse
program later folded into variants.

## Interfaces

`workspace_for(model_id)` maps a model id to a workspace by substring, and
`main()` reads the three input files, aggregates TPS per model, builds the
per-workspace tables, computes the Pareto frontier (no other model has both
higher TPS and lower memory), and writes the report markdown.

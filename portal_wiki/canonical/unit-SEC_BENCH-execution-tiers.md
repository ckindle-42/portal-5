---
id: unit-SEC_BENCH-execution-tiers
kind: what
title: 'Three execution tiers: theory, exec, lab-exec'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: portal/modules/security/core/cli.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- tiers
created_at: 1784941806.377484
updated_at: 1784941806.377484
---

The bench supports three execution tiers:

1. **Theory pass** -- models generate prose or keyword-scored tool calls; nothing runs. Used for fleet benchmarking.
2. **Exec pass** -- tools enabled, tool-call sequence scored against `exec_sequence` definitions.
3. **Lab-exec mode** -- model-emitted `execute_bash` calls are dispatched to a Kali container (`portal5-attack:latest`) inside `portal5-dind`, which has real network reachability to lab targets.

Lab-exec is the ground truth for red/purple team evaluation. All tiers run from the same CLI.

The bench supports BenchConfig (replacing mutable module globals): all functions that previously mutated module-level globals now receive a `cfg: BenchConfig` parameter. `main()` creates the config once, calls `cfg.set_scenario()` per scenario iteration, and passes it to all chain/blue/purple runners.

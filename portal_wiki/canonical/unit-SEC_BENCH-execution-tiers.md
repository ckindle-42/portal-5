---
id: unit-SEC_BENCH-execution-tiers
kind: what
title: 'Three execution tiers: theory, exec, lab-exec'
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/_config.py
last_generated_commit: ace36bcf
claims: []
confidence: high
tags:
- bench
- security
- tiers
- verified-v1
created_at: 1784941806.377484
updated_at: 1784941806.377484
---

The bench supports three execution tiers:

1. **Theory pass** -- models generate prose or keyword-scored tool calls; nothing runs. Used for fleet benchmarking.
2. **Exec pass** -- tools enabled, tool-call sequence scored against `exec_sequence` definitions.
3. **Lab-exec mode** -- model-emitted `execute_bash` calls are dispatched to a Kali container (`portal5-attack:latest`) inside `portal5-dind`, which has real network reachability to lab targets.

Lab-exec is the ground truth for red/purple team evaluation. All tiers run from the same CLI.

The bench supports `BenchConfig` (replacing mutable module globals): all functions that previously mutated module-level globals now receive a `BenchConfig` parameter. `main()` creates the config once, calls `set_scenario()` per scenario iteration, and passes it to all chain/blue/purple runners.

## Why

Three tiers exist so throughput and truth are not conflated. Theory pass scores many models cheaply on prose quality; exec pass scores tool-call sequence without touching the lab; lab-exec is the expensive ground-truth tier that proves commands actually landed. Routing all three through the same CLI keeps the harness identical across tiers, and the `BenchConfig` refactor made the tiers safe to interleave by removing the mutable module globals that used to leak scenario state between runs.

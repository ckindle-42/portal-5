---
id: unit-SECURITY_BENCH_EXEC-benchconfig-replacing-mutable-globals
kind: why
title: "SECURITY_BENCH_EXEC \u2014 BenchConfig \u2014 Replacing Mutable Globals"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "BenchConfig \u2014 Replacing Mutable Globals"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8960168
updated_at: 1783195000.8960168
---


All functions that previously mutated module-level globals (`CHAIN_EXPECTED_ORDER`, `CHAIN_INITIAL_PROMPT`, `_DYNAMIC_CVE_MODE`, `_JUDGMENT_MODE`, `CHAIN_TOOLS`) now receive a `cfg: BenchConfig` parameter. `main()` creates the config once, calls `cfg.set_scenario()` per scenario iteration, and passes it to all chain/blue/purple runners. This preserves the "set context, then dispatch" coordination pattern without module-level mutation.

The bench supports three execution tiers:

1. **Theory pass** — models generate prose or keyword-scored tool calls; nothing runs. Used for fleet benchmarking.
2. **Exec pass** — tools enabled, tool-call sequence scored against `exec_sequence` definitions.
3. **Lab-exec mode** — model-emitted `execute_bash` calls are dispatched to a Kali container (`portal5-attack:latest`) inside `portal5-dind`, which has real network reachability to lab targets.

Lab-exec is the ground truth for red/purple team evaluation. All tiers run from the same CLI.

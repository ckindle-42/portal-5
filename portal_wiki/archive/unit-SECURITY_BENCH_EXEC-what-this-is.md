---
id: unit-SECURITY_BENCH_EXEC-what-this-is
kind: why
title: "SECURITY_BENCH_EXEC \u2014 What This Is"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: What This Is
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.895637
updated_at: 1783195000.895637
---


`bench_security` is a **package** (`tests/benchmarks/bench_security/`) decomposed into 8 modules:

| Module | Purpose |
|--------|---------|
| `_data.py` | All configuration: PROMPTS (46), EXEC_SEQUENCES (25), CHAIN_INHERITANCE, constants, env vars, service probes, tool definitions |
| `_config.py` | `BenchConfig` dataclass — per-run context replacing mutable module globals |
| `scoring.py` | Pure scoring functions (no I/O): response scoring, execution scoring, handoff quality, chain coherence, scope discipline |
| `lab.py` | Lab lifecycle: service probing, Proxmox snapshot/restore, sandbox dispatch, stealth queries, artifact injection |
| `blue.py` | Blue team defender: detection chain, telemetry, purple scoring, evasion loops |
| `chain.py` | Chain execution: multi-turn tool-call chains, synthetic results, scenarios, refusal tests |
| `cli.py` | CLI entry point: argparse, `run_bench()`, summary printing |
| `matrix.py` | Scenario × container matrix: `build_run_matrix`, `run_matrix`, `TelemetryBackend` protocol, `WazuhBackend`, coverage reports |
| `__init__.py` | Thin facade: pipeline I/O (`call_pipeline`, `call_pipeline_exec`) + re-exports |

`bench_security.py` at the package root is a backward-compat re-export shim.

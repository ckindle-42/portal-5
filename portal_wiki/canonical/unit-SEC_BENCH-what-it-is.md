---
id: unit-SEC_BENCH-what-it-is
kind: what
title: bench_security package structure and modules
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: portal/modules/security/core/
  commit: d869257b
- type: code
  path: portal/modules/security/core/__init__.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/_config.py
- type: code
  path: portal/modules/security/core/scoring.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/blue.py
- type: code
  path: portal/modules/security/core/chain.py
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/matrix.py
- type: code
  path: portal/modules/security/core/capability/__init__.py
- type: code
  path: portal/modules/security/core/goal.py
- type: code
  path: portal/modules/security/core/goal_decide.py
- type: code
  path: portal/modules/security/core/goal_eval.py
- type: code
  path: portal/modules/security/core/goal_cli.py
- type: code
  path: portal/modules/security/core/drift_gate.py
- type: code
  path: portal/modules/security/core/drift_cli.py
- type: code
  path: portal/modules/security/core/loop.py
- type: code
  path: portal/modules/security/core/loop_cli.py
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- structure
created_at: 1784941806.37069
updated_at: 1784941806.37069
---

`bench_security` is a **package** (`portal/modules/security/core/`), originally decomposed into modules. The package has grown substantially since (chain execution, scoring, and lab-exec logic were further split).

| Module | Purpose |
|--------|---------|
| `_data.py` | All configuration: PROMPTS, EXEC_SEQUENCES, CHAIN_INHERITANCE, constants, env vars, service probes, tool definitions |
| `_config.py` | `BenchConfig` dataclass -- per-run context replacing mutable module globals |
| `scoring.py` | Pure scoring functions (no I/O): response scoring, execution scoring, handoff quality, chain coherence, scope discipline |
| `lab.py` | Lab lifecycle: service probing, Proxmox snapshot/restore, sandbox dispatch, stealth queries, artifact injection |
| `blue.py` | Blue team defender: detection chain, telemetry, purple scoring, evasion loops |
| `chain.py` | Chain execution: multi-turn tool-call chains, synthetic results, scenarios, refusal tests |
| `cli.py` | CLI entry point: argparse, `run_bench()`, summary printing |
| `matrix.py` | Scenario x container matrix: `build_run_matrix`, `run_matrix`, `TelemetryBackend` protocol, `WazuhBackend`, coverage reports |
| `capability/` | Capability index -- unifies `_LAB_SERVICE_PROBES`, `challenge_classes.yaml`, and `lab_targets.yaml` into one queryable `Capability` list |
| `goal.py`, `goal_decide.py`, `goal_eval.py`, `goal_cli.py` | Goal-driven decide -- reasons over the capability index instead of a playbook DAG |
| `drift_gate.py`, `drift_cli.py` | Drift-detection gate -- rolling-baseline regression + model-behavior canary |
| `loop.py`, `loop_cli.py` | Autonomy loop escalation notifications + checkpoint/resume |
| `__init__.py` | Thin facade: pipeline I/O + re-exports |

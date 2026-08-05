---
id: unit-SEC_BENCH-what-it-is
kind: what
title: bench_security package structure and modules
sources:
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
  path: portal/modules/security/core/exec_chain.py
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
- type: code
  path: portal/modules/security/core/__init__.py
last_generated_commit: 26f31124
claims: []
confidence: high
tags:
- bench
- security
- structure
- verified-v1
created_at: 1784941806.37069
updated_at: 1784941806.37069
---

`bench_security` is a **package** (`portal/modules/security/core/`), decomposed from a single module. Chain execution, scoring, and lab-exec logic were further split into focused sub-modules; `chain.py` and `cli.py` are now thin re-export shims over the implementations that moved out.

| Module | Purpose |
|--------|---------|
| `_data.py` | All configuration: PROMPTS, EXEC_SEQUENCES, CHAIN_INHERITANCE, constants, env vars, service probes, tool definitions |
| `_config.py` | `BenchConfig` dataclass -- per-run context replacing mutable module globals |
| `scoring.py` | Pure scoring functions (no I/O): response scoring, execution scoring, handoff quality, chain coherence, scope discipline |
| `lab.py` | Lab lifecycle: service probing, Proxmox snapshot/restore, sandbox dispatch, stealth queries, artifact injection |
| `blue.py` | Blue team defender: detection chain, telemetry, purple scoring, evasion loops |
| `exec_chain.py` | Execution chain: multi-turn tool-call chains, scenarios, `_run_exec_chain()`, synthetic results |
| `chain.py` | Re-export shim for `exec_chain.py`, `refusal.py`, and `intake.py` |
| `cli.py` | CLI entry point: argparse dispatcher; `run_bench()` and summary printers live in `commands/run.py` |
| `matrix.py` | Scenario x container matrix: `build_run_matrix`, `run_matrix`, `TelemetryBackend` protocol, coverage reports |
| `capability/` | Capability index -- unifies `_LAB_SERVICE_PROBES`, `challenge_classes.yaml`, and `lab_targets.yaml` into one queryable `Capability` list |
| `goal.py`, `goal_decide.py`, `goal_eval.py`, `goal_cli.py` | Goal-driven decide -- reasons over the capability index instead of a playbook DAG |
| `drift_gate.py`, `drift_cli.py` | Drift-detection gate -- rolling-baseline regression + model-behavior canary |
| `loop.py`, `loop_cli.py` | Autonomy loop escalation notifications + checkpoint/resume |
| `__init__.py` | Thin facade: pipeline I/O + re-exports |

## Why

The package boundary exists so the security bench can grow without a single monolithic script. The refactors split chain, blue, and lab-exec logic out of the original module, and the module-level shims (`chain.py`, `cli.py`, `__init__.py`) keep import compatibility while the implementation moves. Knowing which file owns which concern — configuration in `_data.py`, pure math in `scoring.py`, live lab I/O in `lab.py` — is what lets a new contributor add a scenario or a scoring rule without touching unrelated code paths.

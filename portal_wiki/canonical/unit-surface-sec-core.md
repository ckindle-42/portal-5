---
id: unit-surface-sec-core
kind: mixed
title: "Security core \u2014 the RBP bench engine"
sources:
- type: code
  path: portal/modules/security/core/*.py
last_generated_commit: 3d7ada5ee6506e7b736addbdbd21c07778915453
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785882200.0
updated_at: 1785882200.0
---

The security core is the RBP bench engine: chain execution and lab
dispatch, blue orchestration and its verdict taxonomy, council and
multichain interpreter paths, oracle and twin-control scoring, evidence and
memory artifacts, the capability graph feeding the growth loop, telemetry
contracts, the bench fleet, and operator CLIs. Moved as a whole, the
package facade re-exports the full public surface.

## Why

The discipline every part obeys is the design. Config sits on one dataclass
because module-level mutation let runners see half-updated state. A finding
counts only when it lands on the vulnerable twin and vanishes on the
hardened one. The council votes one shared evidence pool while multichain
runs independent chains, so disagreement is about conclusions, not
evidence. Evidence stays deterministic: no model touches it, attribution
refuses fabrication, and proof capsules carry integrity hashes so replay
verifies.

## Interfaces

`BenchConfig` and `_sweep_driver` sequence the model and prompt grid; the
chain runs the `intake` and `refusal` splits; `oracles` judge scenario
objectives while `objective_oracles` verify end-states; `validation` and
`validate_captures` gate and grade runs; `recall_attribution` separates
retrieval failure from model failure; `telemetry` fixes one backend
contract; `episode`, `capsules`, `field_journal`, and `self_index` persist
records; `capability_graph` and `growth_loop` close the loop; `cli` and
`loop_cli` expose the operator surface; `ctf_bench`, `oast_bench`,
`re_firmware`, `llm_redteam`, and `council_review_bench` form the fleet;
`compliance_report` maps findings to frameworks.

## Gotchas

Because the core moved as a whole, every re-export is contractual —
split-out logic is re-exported by its parent so callers never notice. Bench
flags default to the safe choice: lab snapshots and active response are
opt-in. Oracles stay experimental until a bench gates them. Rescoring is
development data, never independent confirmation; telemetry pre-checks
catch a broken source before a run depends on it.

---
id: unit-toolpreselect-baseline-prefill
kind: mixed
title: "Tool-preselect baseline \u2014 prefill cost of full vs trimmed schemas"
sources:
- type: code
  path: tests/toolpreselect/baseline_prefill_bench.py
  commit: 7c9c4031
last_generated_commit: 7c9c4031
claims: []
confidence: high
tags:
- authored-v1
- tests
- toolpreselect
created_at: 1785795872.831234
updated_at: 1785795872.831234
---

`baseline_prefill_bench.py` measures the *prefill* cost of sending full tool
schemas to the primary model, comparing three conditions per workspace:
FULL (all tools the workspace sends, typically 8–15), TRIMMED (the first
three, simulating a preselector with K=3), and ZERO (no tools, the floor).
It reports `prompt_eval_duration` — prefill-isolated — rather than
end-to-end latency, and writes a timestamped JSONL.

## Why

The preselector's whole justification is that trimming tool schemas saves
prefill tokens on every request, and that claim needs a measurement that
isolates prefill from generation. End-to-end latency mixes in model output
length, so a bench that used it could not distinguish "fewer schema tokens"
from "shorter answer". Measuring `prompt_eval_duration` across the three
conditions gives the operator the actual prefill-cost delta per workspace,
which is the number that justifies (or fails to justify) the preselector's
existence. The ZERO condition is the floor reference that makes the TRIMMED
and FULL numbers interpretable against a no-tools baseline.

## Interfaces

`_load_tool_schemas` reads the workspace tool sets, `_warmup` isolates the
load penalty, `_run_single` times one condition, and `_run_workspace` runs the
three conditions for a workspace. `main` produces the timestamped JSONL.

## Gotchas

The bench is sequential and per-model — it does not attempt to characterise
the concurrent-load case, only the per-request prefill cost of schema size.

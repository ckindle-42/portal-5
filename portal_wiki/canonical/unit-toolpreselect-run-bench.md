---
id: unit-toolpreselect-run-bench
kind: mixed
title: "Tool-preselect acceptance runner \u2014 repped scenario bench"
sources:
- type: code
  path: tests/toolpreselect/run_bench.py
  commit: 7c9c4031
last_generated_commit: 7c9c4031
claims: []
confidence: high
tags:
- authored-v1
- tests
- toolpreselect
created_at: 1785795867.1413429
updated_at: 1785795867.1413429
---

`run_bench.py` is the exhaustive acceptance runner for the tool preselector:
it runs every scenario from `scenarios.json` against the two gemma4 MLX
variants with three repetitions each, an isolated warmup call, and sequential
execution when Ollama's parallel setting is not raised, writing a timestamped
JSONL result file.

## Why

Acceptance needs measurement discipline the one-off probes lack: fixed reps,
an isolated warmup so the first-call load penalty does not pollute the
timings, and deterministic parallelism. The three-rep structure is what turns
a lucky routing into a measured behaviour — a single correct answer could be
noise, three agreeing answers is a result. Sequential execution is the safe
default because parallel dispatch of the same model can interfere with token
generation in ways that make acceptance timings meaningless, and the runner
only raises parallelism when `OLLAMA_NUM_PARALLEL` is explicitly set higher.

## Interfaces

`_run_scenario` executes one scenario and records the response; `_run_model`
drives the three reps with warmup; `_load_scenarios` splits the corpus into
its family groups; `main` wires the models, scenarios, and output file. The
output is the timestamped JSONL that the acceptance reports aggregate.

## Gotchas

The bench measures preselector behaviour, not model quality — the output
records which tools were selected and how the ranking changed across reps,
not the fluency of the answer.

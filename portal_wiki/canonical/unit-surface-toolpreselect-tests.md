---
id: unit-surface-toolpreselect-tests
kind: mixed
title: "Tool-preselect acceptance harness \u2014 corpus, repped bench, prefill baseline"
sources:
- type: code
  path: tests/toolpreselect/*.py
last_generated_commit: 44337398432f63b63bd77ff750552c81dc7b7cc2
claims: []
confidence: high
tags:
- authored-v1
- tests
- toolpreselect
created_at: 1785881200.0
updated_at: 1785881200.0
---

The tool-preselect acceptance harness is one contract in three stages: a
generator that builds an exhaustive adversarial corpus from the *live* tool
registry, a runner that executes every scenario against the gemma4 MLX
variants with fixed reps and an isolated warmup, and a baseline bench that
measures the prefill cost of full versus trimmed tool schemas. All three
consume the same scenario surface and emit timestamped JSONL for the
acceptance reports.

## Why

A preselector that returns the wrong tool for a clear task, or the same tool
regardless of order, is a silent correctness failure — the corpus deliberately
attacks those failure modes with decoy, compound, reorder, and no-good-fit
families, and derives its positives from the live registry so a new tool gets
a scenario without hand-editing. The runner needs measurement discipline the
one-off probes lack: fixed reps turn a lucky routing into a measured behaviour
(three agreeing answers is a result), and the isolated warmup keeps the
first-call load penalty out of the timings. The baseline exists because the
preselector's whole justification is that trimming schemas saves prefill
tokens — so it isolates `prompt_eval_duration` from generation, with a ZERO
condition as the floor that makes the trimmed and full numbers interpretable.

## Interfaces

The corpus builders (`_build_positive_scenarios` and the decoy, compound,
reorder, and no-good-fit family builders) feed `scenarios.json`; the runner
drives each scenario through `_run_scenario` and `_run_model` with three reps
plus warmup; the baseline bench times FULL / TRIMMED / ZERO per workspace via
`_run_single` and `_run_workspace`. Sequential execution is the default
because parallel dispatch of one model can interfere with token generation and
make acceptance timings meaningless.

## Gotchas

The bench measures preselector behaviour, not model quality — it records which
tools were selected and how the ranking changed, not answer fluency. The
baseline is per-model and per-request only; it does not characterise the
concurrent-load case. Tools without a hand-crafted scenario fall back to a
generic-but-realistic one derived from their description, keeping corpus
coverage exhaustive.

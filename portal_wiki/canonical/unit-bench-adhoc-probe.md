---
id: unit-bench-adhoc-probe
kind: mixed
title: "Bench ad-hoc probe \u2014 TPS for unregistered candidates"
sources:
- type: code
  path: tests/benchmarks/bench/adhoc_probe.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798413.108706
updated_at: 1785798413.108706
---

`adhoc_probe.py` is the lightweight TPS/quality probe for models *not*
registered in `config/backends.yaml` — a freshly-pulled candidate tag that
has not been wired into the production fleet. It reuses the bench's prompt
library and TPS formula directly against the raw model.

## Why

`bench_tps`'s `--model` filter matches against the configured backends, which
is the right default for regression-tracking the production fleet — but it
means an unregistered candidate cannot be sanity-checked until it is wired
into config. That forced every one-off candidate eval to reinvent the loop in
a /tmp script. The probe closes that gap: an operator can measure a raw
candidate's TPS *before* deciding whether it is worth wiring in, which is the
decision input for whether a model enters the fleet at all.

## Interfaces

`probe_models(models, runs, prompt_category)` measures each model's TPS with
the shared formula; `_warmup` and `_run_one` are the per-model helpers;
`main` drives the probe and prints results.

## Gotchas

The probe talks to the raw Ollama endpoint, not the pipeline — it measures
the model, not routing, and its numbers must not be compared directly to
pipeline TPS figures.

---
id: unit-bench-discovery
kind: mixed
title: "Bench discovery \u2014 config-driven fleet plan + sizing"
sources:
- type: code
  path: tests/benchmarks/bench/discovery.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798425.1465359
updated_at: 1785798425.1465359
---

`discovery.py` is the config-driven model/workspace/persona discovery for
the bench: it reads backends.yaml and the config, groups models by routing
group, and estimates model sizes for memory planning.

## Why

A TPS bench must measure the *configured* fleet, not an arbitrary list, so
discovery starts from the config: which models are registered, which
workspaces route to them, which personas exist. The size estimation feeds the
lifecycle's memory decisions — a bench must not queue two models that
together exceed the device's memory, because the second would evict the
first mid-measurement. Discovery is what turns the config into the bench's
plan.

## Interfaces

`_load_backends_config`, `_config_ollama_models_by_group`,
`_config_ollama_models_unique`, `_config_workspaces`, `_discover_personas`,
and `_parse_model_size_gb` are the discovery surface the runners consume.

## Gotchas

The size estimate is approximate (parsed from the config's stated size), used
for scheduling — a wrong estimate degrades the run plan, not the measurement.

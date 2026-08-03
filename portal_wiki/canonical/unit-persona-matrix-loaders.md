---
id: unit-persona-matrix-loaders
kind: mixed
title: "Persona matrix loaders \u2014 config/catalog/persona readers"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/loaders.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785796989.3566458
updated_at: 1785796989.3566458
---

`loaders.py` reads the persona-matrix inputs: the backends catalog, the model
chains per workspace, the personas for a workspace or by slug, and Ollama
size estimates for memory planning.

## Why

The sweep needs the config read consistently — the model chain a workspace
uses, the personas that belong to it, and the size of each candidate model —
and separating that into loaders keeps the sweep orchestration readable.
`_ollama_size_estimate` matters because the sweep's memory discipline
depends on knowing how big a model is before it is loaded: a sweep that
queues two models whose combined size exceeds the device would evict one
mid-cell, corrupting the run.

## Interfaces

`load_backends_yaml` reads the catalog; `chain_for_workspace` and
`chain_models_for_workspace` resolve a workspace's model chain;
`load_personas_for_workspace` and `load_personas_by_slugs` resolve the
persona set; `_ollama_size_estimate` estimates a model's memory footprint.
`models_in_group` returns the models sharing a routing group.

## Gotchas

`_ollama_size_estimate` is an estimate, not a measurement — the sweep uses
it for *scheduling* decisions (which models to load together), so a wrong
estimate degrades scheduling, not correctness.

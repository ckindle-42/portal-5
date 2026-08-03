---
id: unit-inference-cli-models
kind: mixed
title: "Inference CLI models \u2014 dual-origin model provisioning"
sources:
- type: code
  path: portal/platform/inference/cli/models.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797857.005394
updated_at: 1785797857.005394
---

`portal models` is the model registry surface: pulling native Ollama
registry models and HuggingFace models (via the Python API plus `ollama
create`), listing the catalog, and managing the backend model set.

## Why

Model provisioning is a two-world problem: some models are native Ollama
registry pulls and others are HuggingFace GGUF files that must be downloaded
and created into Ollama. The CLI unifies both behind one command so an
operator adds a model the same way regardless of its origin, and the
existence checks prevent pulling a model that is already present.

## Interfaces

`_pull_native` handles registry pulls, `_pull_hf_model` handles the
HuggingFace path, and the remaining commands list and manage the registry,
all registered on `models_app`.

## Gotchas

The HuggingFace path is the more fragile of the two — it depends on the HF
API and the `ollama create` step, so a failure there must not be confused
with a native-pull failure.

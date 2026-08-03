---
id: unit-inference-cli-common
kind: mixed
title: "Inference CLI common \u2014 shared Ollama/helper utilities"
sources:
- type: code
  path: portal/platform/inference/cli/_common.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797839.222193
updated_at: 1785797839.222193
---

`_common.py` holds the shared helpers for the CLI sub-modules: the Ollama
command resolver (native binary or docker exec), model-existence checks, and
the other utilities the model and workspace commands reuse.

## Why

The CLI needs to know how to talk to Ollama whether it is running natively
or inside Docker — a one-line `ollama pull` that works on one deployment and
fails on another is exactly the portability trap the resolver exists to
avoid. Centralising the detection keeps every sub-command consistent about
which Ollama it is addressing, so `portal models` and `portal workspace` do
not disagree about the backend.

## Interfaces

`_detect_ollama_cmd` returns the native or docker-exec command;
`_model_exists_in_ollama` checks the backend for a model; the other shared
helpers serve the command implementations.

## Gotchas

The docker-exec path is used when no native `ollama` binary is on `PATH` —
a deployment mixing native and containerised Ollama would get inconsistent
behaviour, which is why the detection is shared rather than per-command.

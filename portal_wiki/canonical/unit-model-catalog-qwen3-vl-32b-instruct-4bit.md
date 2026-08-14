---
id: unit-model-catalog-qwen3-vl-32b-instruct-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Qwen3-VL-32B-Instruct-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`Qwen3-VL-32B-Instruct-4bit` is a 4-bit MLX conversion of Qwen3-VL-32B-Instruct registered in `config/backends.yaml` under `group: omlx` (`omlx-local`) with `supports_tools: false` — the group's live-probe notes record a passing vision probe, not structured tool calling. The `omlx` holding group carries no `workspace_routing` reference, so traffic reaches the model only through the tier-3 absolute fallback. Phase-0 Gate-6 recorded a 7.7s load and correct image understanding via OpenAI `image_url` parts. It is an evaluation candidate for the `auto-vision` lane, whose production primary is the GGUF `qwen3-vl:32b` family, and must clear a migration gate before any promotion.

## Why

The oMLX entry's `supports_tools: false` is easy to misread as a vision failure; in fact the vision probe passed and only tool-calling is disclaimed. Grounding the flag against the `omlx-local` entry and noting the holding group's lack of `workspace_routing` makes both the capability boundary and the reachability boundary explicit, and prevents a future reader from wiring the model into a production lane by mistake.

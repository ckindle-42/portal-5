---
id: unit-model-catalog-devstral-small-2-latest
kind: what
title: "MODEL_CATALOG \u2014 `devstral-small-2:latest`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: db75e444cdca521f9be63059be9180bb380a4a64
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6214578
updated_at: 1784946220.6214578
---

`devstral-small-2:latest` is registered in `config/backends.yaml` under the `general` group with `supports_tools: false` and under the `security` group with `supports_tools: true`, cross-listing it for deep-chain security workspaces. `config/portal.yaml` gives it the `bench-devstral-small-2` workspace `model_hint`. The catalog records ~15GB and a 15.5 TPS pipeline figure, below the interactive floor, so the model is intended for deep async use; a 2026-06-21 run scored 1.00/1.00 on both scenarios at depth 11.0. The coding group carries the bare `devstral-small-2` id and the `devstral-small-2:latest-ctx8k` variant.

## Why

The general-versus-security split in `config/backends.yaml` is the config fact behind the "cross-listed in security" claim, and `config/portal.yaml` binds it to the bench workspace via `model_hint`. The throughput and chain-depth figures are kept as institutional notes, but the group registrations and the workspace binding are what the config actually asserts.

---
id: unit-model-catalog-tongyi-deepresearch-30b-a3b-abliterated-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Tongyi-DeepResearch-30B-A3B-abliterated-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786316500.0
updated_at: 1786316500.0
---

`Tongyi-DeepResearch-30B-A3B-abliterated-4bit` is the 4-bit MLX conversion (jurejaklic, via huihui-ai's abliteration) of Tongyi-DeepResearch-30B-A3B served by the oMLX evaluation backend. `config/backends.yaml` registers it in the `omlx-reasoning` entry (group `reasoning`, `priority: 10`), added alongside `DeepSeek-R1-0528-Qwen3-8B-4bit` once Phase 4 verification of TASK_OMLX_FULL_PIPELINE_COVERAGE_V1 showed `auto-research` pins its own `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` model_hint — distinct from `auto-reasoning`'s DeepSeek-R1 hint — so a single-model `omlx-reasoning` entry left `auto-research` falling through to Ollama by hint mismatch, not by admission reject. Live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`, no template/tokenizer defects). Already on disk per `TASK_DAILY_WORK_FLEET_SOAK_V1`'s own per-category model table.

## Why

Grounds the model to the `omlx-reasoning` multi-model registration and explains why it was added in the same task as DeepSeek-R1 despite the task's original Phase 0 table implying one model per group — the `reasoning` group's four daily workspaces each pin a different `model_hint`, so full pipeline coverage for the group needed every distinct hint aliased, not just the group's namesake workspace.

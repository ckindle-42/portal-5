---
id: unit-model-catalog-huihui-ai-tongyi-deepresearch-abliterated
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/tongyi-deepresearch-abliterated`"
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
created_at: 1784946220.6323571
updated_at: 1784946220.6323571
---

`huihui_ai/tongyi-deepresearch-abliterated` is an abliterated deepresearch model in the Qwen3.5-abliterated lineage, registered in `config/backends.yaml` under the `reasoning` group with `supports_tools: true`. `config/portal.yaml` routes the `auto-research` workspace through the `:latest-ctx64k` derived tag as its `model_hint`, so the base id anchors the reasoning pool while the derived tag carries the web-research traffic. The tool-capable verdict was confirmed by an audit-tools run that emitted a real tool_call. The base id itself has no separate workspace binding; it is the reasoning-group registration that matters.

## Why

The `reasoning`-group placement with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` shows the `auto-research` workspace resolving the `:latest-ctx64k` variant rather than this base id. The audit-tools confirmation is preserved because it is the recorded reason the tool flag is true, and the base-versus-derived routing split is the fact the body now states instead of the older bare assertion.

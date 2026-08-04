---
id: unit-model-catalog-hf-co-mitkox-fastcontext-1-0-4b-sft-q4-k-m-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6134982
updated_at: 1784946220.6134982
---

`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` (~2.5GB, Microsoft fastcontext arxiv:2606.14066, mitkox GGUF) is the repository-exploration subagent model: it issues parallel READ/GLOB/GREP tool calls to locate relevant code and returns compact file+line citations, cutting main-agent exploration token burn on SWE-bench. `config/backends.yaml` registers it in the `general` group with `supports_tools: false` and in the `coding` group with `supports_tools: true` — the coding entry is what lets the explore_repository subagent use its three native tools. `config/portal.yaml` selects it as the `model_hint` for `bench-fastcontext`, whose description records the empty-content probe result and PROMOTE_POLICY=blocked pending a correct Modelfile. It is used by `pipeline_mcp.explore_repository()`, called by auto-coding before edits.

## Why

The doc body asserted the READ/GLOB/GREP tool set and the `pipeline_mcp.explore_repository()` usage; re-grounding verifies the id and its group-split `supports_tools` flags in `config/backends.yaml`, the bench lane and blocked status in `config/portal.yaml`, and the `_FASTCONTEXT_MODEL` constant in `pipeline_mcp.py` that backs the subagent. The token-burn-reduction figure is kept as paper-reported knowledge, while every config-resolvable claim now points at its source file.

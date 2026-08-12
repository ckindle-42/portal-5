---
id: unit-model-catalog-portal5-deepwen-3-6-q4-5-moq-ctx32k
kind: what
title: "MODEL_CATALOG \u2014 `portal5/deepwen-3.6:q4.5-moq-ctx32k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786396600.0
updated_at: 1786396600.0
---

`portal5/deepwen-3.6:q4.5-moq-ctx32k` is the ctx-baked derived tag for `portal5/deepwen-3.6:q4.5-moq`, created via `./launch.sh apply-model-params` (`PARAMETER num_ctx 32768` baked into a new Ollama layer, idempotent — no re-download) to work around `P5-OLLAMA-OPTIONS-001` (Ollama's `/v1/chat/completions` endpoint silently ignores request-time `options.num_ctx`; see `unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch`). `config/portal.yaml`'s `bench-deepwen-cad` workspace `model_hint` points at this tag, not the bare `q4.5-moq` tag — the bare tag alone produced corrupted tool-call JSON through the pipeline. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, inherited from the base tag's direct-probe verification.

## Why

Kept as a separate catalog entry (not folded into the base tag's) because `test_model_catalog_parity.py::test_all_backends_models_have_catalog_entry` requires a `### \`id\`` section for every distinct id in `backends.yaml`, and because the derived tag is the one actually served — a future session checking why `bench-deepwen-cad` doesn't route to the plain `q4.5-moq` id should find this pointer immediately rather than assuming a typo.

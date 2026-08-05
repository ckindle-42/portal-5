---
id: unit-model-catalog-portal5-gemma4-12b-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `portal5/gemma4-12b:q4_K_M-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: fccb30525d4520443bca3fdbeebfbdb0fd6980f6
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6023412
updated_at: 1784946220.6023412
---

`portal5/gemma4-12b:q4_K_M-ctx8k` is the 8192-token capped tag of the Gemma 4 12B Q4 model (~7.6GB, Google). `config/backends.yaml` registers it in `group: general` with `supports_tools: true`. The cap exists because the 12B family's very large native context inflates KV-cache reservations and collapses TPS; the num_ctx 8192 limit is baked into this dedicated id via the `apply-params` command. It is not pinned by any `config/portal.yaml` workspace `model_hint`; it serves as a general-pool option. See the QAT sibling `gemma4:12b-it-qat` for the same-size family entry.

## Why

Grounding anchors the tag to the general-group registration whose supports_tools true flag the config declares, and records honestly that no portal.yaml workspace consumes it. The old body's reference to a `gemma4:12b-it-q4_K_M` base id is not verifiable in config, so it is dropped in favor of the actual 12B family entry the config carries. The KV-cache rationale is kept as the institutional reason the cap exists.

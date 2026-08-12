---
id: unit-model-catalog-qwen3-6-27b-mtp-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `qwen3.6:27b-mtp-q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.634285
updated_at: 1784946220.634285
---

`qwen3.6:27b-mtp-q4_K_M` is the Q4 embedded-MTP draft model (~19GB, Alibaba) that feeds `portal5/qwen3.6-27b-mtp:q8_0-drafted`. `config/backends.yaml` registers it in `group: reasoning` with `supports_tools: true`. `config/portal.yaml`'s `bench-qwen36-27b-mtp` description names this draft tag as the speculative-decoding companion to the q8_0 base. It must be pulled before the draft-application step runs; the draft heads come with the model, and `apply-mtp-drafts` combines it with the base tag.

## Why

Grounding anchors the draft model to its reasoning-group registration and to the bench workspace whose description names it as the MTP draft. The relationship to the drafted q8_0 tag is the load-bearing fact — this id exists only to feed speculative decoding, so the unit states the pull prerequisite rather than inventing serving details that no config supports.

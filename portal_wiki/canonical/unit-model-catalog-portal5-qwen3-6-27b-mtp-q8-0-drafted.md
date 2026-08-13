---
id: unit-model-catalog-portal5-qwen3-6-27b-mtp-q8-0-drafted
kind: what
title: "MODEL_CATALOG \u2014 `portal5/qwen3.6-27b-mtp:q8_0-drafted`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.634649
updated_at: 1784946220.634649
---

`portal5/qwen3.6-27b-mtp:q8_0-drafted` is the speculative-decoding tag built by `apply-mtp-drafts` (TASK_MODEL_FLEET_REFRESH_V2 Phase 5): a q8_0 base with the `mtp-q4_K_M` draft attached via a DRAFT directive. `config/backends.yaml` registers it in `group: general` with `supports_tools: false` and in `group: reasoning` with `supports_tools: true`. `config/portal.yaml` pins it as the `bench-qwen36-27b-mtp` workspace `model_hint` for the Phase-5 MTP A/B against the plain q8_0 bench. The tag is not pre-pulled; the draft-application step creates it before use.

## Why

Grounding anchors the tag to the two backends.yaml registrations that carry it — general with supports_tools false, reasoning with true — and to the bench workspace that pins it as `model_hint`. The doc's creation instruction is kept because `config/portal.yaml` itself says to run `apply-mtp-drafts` to create the tag before use, which is the operational prerequisite for the bench.

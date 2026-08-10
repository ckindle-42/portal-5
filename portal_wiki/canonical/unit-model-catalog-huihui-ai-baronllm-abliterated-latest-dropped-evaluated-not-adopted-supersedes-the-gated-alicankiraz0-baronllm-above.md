---
id: unit-model-catalog-huihui-ai-baronllm-abliterated-latest-dropped-evaluated-not-adopted-supersedes-the-gated-alicankiraz0-baronllm-above
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/baronllm-abliterated:latest` \u2014 DROPPED\
  \ (evaluated, not adopted; supersedes the gated AlicanKiraz0 BaronLLM above)"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.628695
updated_at: 1784946220.628695
---

`huihui_ai/baronllm-abliterated:latest` was evaluated for the EXPLOIT slot and dropped. `config/backends.yaml` registers it only under the `general` group with `supports_tools: false`, and `config/portal.yaml` binds it as the `bench-exec-exploit` and retired `bench-qwable-35b` `model_hint`s rather than any production workspace. The candidate-eval ran the fixed six-scenario gauntlet against the `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` incumbent: the model executed its assigned exploit step with clean tool calls, but the AD-chain handoff stalled, producing a worse aggregate unique-coverage delta with no lab-success gain, and the reliability re-bench recorded valid_rate 0.25 with malformed tool-call attempts. Net result: real capability, no refusal wall, but a handoff-stability regression.

## Why

The `general`-group-only registration with `supports_tools: false` is asserted by `config/backends.yaml`, and `config/portal.yaml` confirms the bench-only binding, which is the mechanical proof of the drop. The evaluation detail is preserved because it is the recorded reason the model was not adopted and it explains why a tool-capable-looking fork carries a false flag in the registry.

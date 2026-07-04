---
id: unit-SECURITY_FLEET_REVIEW_2026-06-remove
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Remove"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: Remove
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.9150221
updated_at: 1783195000.9150221
---


| Model | Cov | Reason |
|---|---|---|
| `hf.co/huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated-MTP-GGUF:latest` | 0.00 | Errors on every chain and tool probe. No path to recovery in current format. |
| `baronllm:q6_k` | 0.00 | Tool template bug caused chain failures (TASK_TOOLCALL_FIX_LOCKIN_V1 fixed this in the abliterated variant, not the q6_k). The base model is not the problem — this quantization/template combination is. |
| `deepseek-r1:32b-q4_k_m` | 0.00 | Cannot emit tool_calls — text_only on all probes. Not a model failure; it's a reasoning model in the wrong group. Already available to `auto-blueteam` through the reasoning group pathway. |
| `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` | 0.64 | Failed CANDIDATE_EVAL_V1 Step 0 threshold. Commit `9d3a63f` promoted it anyway — that decision is reversed here. Also: `ollama rm` this model. |

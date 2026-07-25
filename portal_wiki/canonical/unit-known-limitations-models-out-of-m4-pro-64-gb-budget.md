---
id: unit-known-limitations-models-out-of-m4-pro-64-gb-budget
kind: what
title: "KNOWN_LIMITATIONS \u2014 Models Out of M4 Pro 64 GB Budget"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Models Out of M4 Pro 64 GB Budget
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.675589
updated_at: 1784946220.675589
---

The following models were evaluated and explicitly **refused** from the Portal 5
catalog. They exceed the M4 Pro 64 GB unified memory ceiling at the lowest
quality-preserving quantization. Do not re-propose without a cluster scaling
plan (P5_ROADMAP Stage 3 vLLM node).

**Guardrail for future Claude sessions**: before recommending any MoE model
with total params > 100B on a 64 GB M4 Pro budget, compute the 4-bit weight
footprint. If > 50 GB, refuse and reference this section. Mac Studio 128 GB+
is the path for these models.

| Model | 4-bit MLX resident | Why refused |
|-------|--------------------|-------------|
| `mlx-community/MiniMax-M2-4bit` | ~129 GB | 230B-A10B MoE. 4-bit weight footprint alone exceeds 64 GB before any KV cache. |
| `mlx-community/MiniMax-M2.5-4bit` (and Uncensored variant) | ~129 GB | Same architecture as M2. |
| `mlx-community/MiniMax-M2.7-4bit-mxfp4` | ~129 GB | mxfp4 does not reduce the dense-weight component substantially. |
| `thetom-ai/MiniMax-M2.7-ConfigI-MLX` (mixed-precision) | ~87 GB | Aggressive Config-I 2-bit on expert MLPs, still over 64 GB. |
| `mlx-community/DeepSeek-V4-Flash` (community 4-bit) | ~142 GB | 284B-A13B MoE FP4+FP8 base. |
| `mlx-community/DeepSeek-V4-Pro` (community 4-bit) | ~800 GB | 1.6T total params. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-4bit` (Instruct + Thinking) | ~578 GB | 1T total MoE, 32B active. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-DQ3_K_M` | ~450 GB | Mixed 3-4 bit still over budget. |
| GLM-5 (Z.AI flagship) | 192+ GB at 4-bit | 744B params; not yet in MLX. |
| `huihui-ai/Huihui-GLM-5.1-abliterated` (754B) | 377+ GB at 4-bit | Same bucket as GLM-5 — abliterated variant, total params far exceed 64 GB. |

**P5-MODEL-64GB principle**: MoE active-parameter count governs decode *speed*, but total parameters govern *whether it fits* — 64 GB gates on total, not active. The April-2026 headline releases (DeepSeek-V4-Flash 284B/13B active, Kimi-K2.6 1T/32B active) are verified real but excluded on this basis. They become relevant only at the cluster Stage-3 / Mac-Studio tier on the roadmap.

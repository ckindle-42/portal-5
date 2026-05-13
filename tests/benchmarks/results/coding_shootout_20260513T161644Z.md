# Coding Shootout — Results Summary

**Source matrix run**: `coding_shootout_20260513T161644Z.json`
**Decision rule**: candidate defeats incumbent iff pass-rate +>= 10pp AND TPS ratio >= 0.75x incumbent.

## Per-Model Aggregate

| Model | Pass-rate | Passed/Total | TPS (median) | Memory GB |
|---|---|---|---|---|
| `mlx-community/Laguna-XS.2-4bit`  incumbent | 93.9% | 31/33 | 240.2 | 19 |
| `lmstudio-community/Devstral-Small-2507-MLX-4bit` | 90.9% | 30/33 | 60.2 | 15 |
| `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` | 87.9% | 29/33 | 191.1 | 22 |
| `mlx-community/GLM-4.7-Flash-4bit` | 72.7% | 24/33 | 199.1 | 15 |

## Verdict

**INCONCLUSIVE**

Reason: no candidate beat incumbent by >= 10pp pass-rate while staying within 25% TPS

**Next action**: no repin. Incumbent stays. If new candidate models become available (or the scenario set is broadened), re-run this shootout.

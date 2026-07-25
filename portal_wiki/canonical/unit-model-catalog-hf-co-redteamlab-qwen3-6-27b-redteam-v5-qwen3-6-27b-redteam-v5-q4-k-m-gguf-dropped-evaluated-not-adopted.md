---
id: unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-redteam-v5-qwen3-6-27b-redteam-v5-q4-k-m-gguf-dropped-evaluated-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/RedTeamLab/Qwen3.6-27B-redteam-v5:qwen3.6-27b-redteam-v5-Q4_K_M.gguf`\
  \ \u2014 DROPPED (evaluated, not adopted)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/RedTeamLab/Qwen3.6-27B-redteam-v5:qwen3.6-27b-redteam-v5-Q4_K_M.gguf`\
    \ \u2014 DROPPED (evaluated, not adopted)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6264472
updated_at: 1784946220.6264472
---

Red EXPLOIT-slot candidate (RedTeamLab, Qwen3.6-27B QLoRA, same lineage as their blueteam-v1 above). TPS-
probe 10.4 t/s, below floor — evaluated via `--force`. First run's result JSON was silently lost to a
path-sanitization bug (see git history for the fix) and rerun for a saved record: candidate-eval vs
gemma-4-abliterated:E2b incumbent: aggregate -0.075 order-accuracy, +0.000 coverage/lab_success —
NEUTRAL/slightly negative, worse than RavenX on web_sqli_dump (depth 1/3 vs the same incumbent baseline's
3/3) and ctf_multi_service (depth 5/7 vs baseline 7/7).

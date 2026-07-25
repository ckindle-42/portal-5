---
id: unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-blueteam-v1-q3-k-s-dropped-evaluated-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/RedTeamLab/Qwen3.6-27B-blueteam-v1:Q3_K_S` \u2014\
  \ DROPPED (evaluated, not adopted)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/RedTeamLab/Qwen3.6-27B-blueteam-v1:Q3_K_S` \u2014 DROPPED (evaluated,\
    \ not adopted)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.62447
updated_at: 1784946220.62447
---

Blue-defender candidate (RedTeamLab, Qwen3.6-27B base; only Q3_K_S quant shipped by the source repo).
Passed preflight + tool-call audit. Purple-benched vs sylink/sylink:8b incumbent on the 6-scenario
candidate-eval gauntlet (fixed red=gemma-4-abliterated:E2b): f1=0.00 on all 6 scenarios — ties the
incumbent's zero-detection result on the same set, no improvement.

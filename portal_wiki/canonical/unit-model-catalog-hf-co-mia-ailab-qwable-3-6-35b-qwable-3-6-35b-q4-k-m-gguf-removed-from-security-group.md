---
id: unit-model-catalog-hf-co-mia-ailab-qwable-3-6-35b-qwable-3-6-35b-q4-k-m-gguf-removed-from-security-group
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`\
  \ \u2014 REMOVED from security group"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` \u2014 REMOVED\
    \ from security group"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.620333
updated_at: 1784946220.620333
---

Qwable-3.6-35B MoE (~21GB, MIT). SUPERSEDED in bench chain and auto-pentest by gemma-4-abliterated:E2b-qat (2026-06-25). REMOVED from `ollama-security` group 2026-06-30 per SECURITY_FLEET_REVIEW_2026-06.md (security chain coverage 0.64, below 2/2 WIN threshold) — config had drifted from the documented decision; corrected here. Confirmed substituted by `qwen3-coder:30b-a3b-q4_K_M` in the 2026-06-29 chain rerun. Still present in `ollama-coding` group (separate decision, untouched). Confirmed tool-use 2026-06-18.

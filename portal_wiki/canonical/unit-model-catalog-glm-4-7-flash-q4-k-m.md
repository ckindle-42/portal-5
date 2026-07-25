---
id: unit-model-catalog-glm-4-7-flash-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `glm-4.7-flash:Q4_K_M`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`glm-4.7-flash:Q4_K_M`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6146472
updated_at: 1784946220.6146472
---

GLM-4.7-Flash Q4_K_M (~13GB, ZhipuAI / Z.AI, MIT). 31B MoE, 4 experts/token (~3B active). 128K context. Diverse non-Meta/Qwen lineage. Coding quality 0.67 in bench 2026-06-21 (benchmark prompt style may not favour GLM chat template) — the "template mismatch suspected" note asked for re-verification, never done until now. RE-VERIFIED 2026-07-16 (P5-AUTOSEC-RESELECT): the suspicion was stale, dating from before this project's Ollama 0.30.7 upgrade / MLX retirement (2026-06-09). Direct probes against the real production tool schema (2 turns incl. post-tool-result continuation) plus the formal audit-tools probe (`emitted 1 tool_call(s); first=get_current_time`) all confirm clean, well-formed tool calls. Security chain-test (kerberoast_to_da, --lab-exec): valid_rate 1.00, redundant_call_rate 0.00 — best of 11 candidates measured in the auto-security reselection (docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md). `supports_tools` flipped true in backends.yaml on this basis. DO NOT pull :math variant. bench-glm target; staged as auto-security reselection candidate.

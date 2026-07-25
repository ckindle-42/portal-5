---
id: unit-model-catalog-ravenx-cyberagent-35b-q4-k-m-dropped-evaluated-not-adopted-local-alias-for-ravenx-cyberagent-35b
kind: what
title: "MODEL_CATALOG \u2014 `ravenx-cyberagent-35b:Q4_K_M` \u2014 DROPPED (evaluated,\
  \ not adopted; local alias for RavenX-CyberAgent-35B)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`ravenx-cyberagent-35b:Q4_K_M` \u2014 DROPPED (evaluated, not adopted;\
    \ local alias for RavenX-CyberAgent-35B)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.625427
updated_at: 1784946220.625427
---

Red EXPLOIT-slot candidate (upstream `deadbydawn101/RavenX-CyberAgent-Qwen3.6-35B-A3B-Opus-4.7-
OpenMythos-Pentester-BugHunter-RATH-GGUF`; Qwen3.6-35B-A3B MoE, Claude-4.7-Opus distill + abliteration +
RATH-protocol LoRA). Ollama's hf.co puller rejects the upstream repo name outright (`400 Bad Request:
invalid model name` — repo path >90 chars, fails with or without a quant tag); worked around via manual
HF download + `ollama create` under a short local alias. TPS-probe 14.7 t/s, below the 20 t/s intake
floor — evaluated anyway via `candidate-eval --force` (deliberate quality-over-speed override; a slower
27B/35B model may out-detect a faster small one, and the floor exists for chain responsiveness, not
capability). candidate-eval vs gemma-4-abliterated:E2b incumbent, EXPLOIT slot, 6-scenario gauntlet:
aggregate +0.111 order-accuracy, +0.000 coverage/lab_success — NEUTRAL, slight edge on web_sqli_dump
(depth 3/3 vs incumbent 1/3) but no decisive win.

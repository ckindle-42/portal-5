---
id: unit-model-catalog-hf-co-vegss-titus-cybersecurityllm-v1-0-q4-k-m-no-mtp-gguf-q4-k-m-dropped-evaluated-not-adopted
historical: true
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Vegss/Titus-CybersecurityLLM-v1.0-Q4_K_M-No-MTP-GGUF:Q4_K_M`\
  \ \u2014 DROPPED (evaluated, not adopted)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/Vegss/Titus-CybersecurityLLM-v1.0-Q4_K_M-No-MTP-GGUF:Q4_K_M` \u2014\
    \ DROPPED (evaluated, not adopted)"
confidence: high
tags:
- docs

---

Blue-defender candidate (AlicanKiraz0 lineage, Qwen3.6 35B, SOC/DFIR-tuned, No-MTP quant). Preflight
passed (coherent kerberoasting/MITRE response). Disqualified on tool-call audit: Ollama returns "does not
support tools" — the GGUF's embedded chat template has no tool-calling syntax. Hard model limitation, not
benched.

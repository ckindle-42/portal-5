---
id: unit-model-catalog-hf-co-mradermacher-vulnllm-r-7b-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.619392
updated_at: 1784946220.619392
---

VulnLLM-R-7B (UCSB SURFI, Dec 2025, Qwen2.5-7B base, ~4.4GB Q4_K_M). AppSec / code vulnerability specialist — CVE severity, CWE classification, vulnerable code patterns. Full-fleet bench 2026-06-20: 2/2 chain wins at 15s (fastest security-group winner). audit-tools 2026-06-20: tool_call confirmed. supports_tools=true (Qwen2.5-7B tool-call format). CORRECTED 2026-07-16 (P5-AUTOSEC-RESELECT): the 2026-06-20 claim predates the reliability-scoring fix and never measured tool-call argument grounding. Live re-bench (kerberoast_to_da, --lab-exec): valid_rate 0.89 but redundant_call_rate 0.50 — repeatedly re-guesses hallucinated vmid values instead of reusing the value it was just given (docs/reselection/AUTOSEC_VULNLLM_DIAGNOSIS_20260716T164436Z.md). glm-4.7-flash:Q4_K_M staged as reselection primary (docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md). auto-security + auto-pentest co-primary (vuln depth complements baronllm domain breadth) — pending operator confirmation of the swap.

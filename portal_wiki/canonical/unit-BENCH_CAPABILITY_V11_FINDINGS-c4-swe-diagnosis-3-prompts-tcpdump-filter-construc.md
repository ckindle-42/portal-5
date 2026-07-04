---
id: unit-BENCH_CAPABILITY_V11_FINDINGS-c4-swe-diagnosis-3-prompts-tcpdump-filter-construc
kind: why
title: "BENCH_CAPABILITY_V11_FINDINGS \u2014 C4 \u2014 SWE Diagnosis (3 prompts: tcpdump\
  \ filter construction)"
sources:
- type: design
  path: docs/BENCH_CAPABILITY_V11_FINDINGS.md
  section: "C4 \u2014 SWE Diagnosis (3 prompts: tcpdump filter construction)"
last_generated_commit: ''
confidence: high
tags:
- docs
- BENCH_CAPABILITY_V11_FINDINGS
created_at: 1783195000.827156
updated_at: 1783195000.827156
---


| Workspace | format_score | capability_score |
|---|---|---|
| bench-laguna (production IDE default) | 1.00 | 0.22 |
| bench-qwen3-coder-30b (production coder) | 1.00 | 0.67 |
| bench-agentworld | 0.67 | 0.56 |

**Call: harness helped but capability gap still present.** AgentWorld's format_score of 0.67 (vs 1.00 for baselines) suggests it occasionally fails to produce the requested plan/fence structure even after preamble stripping. Its capability_score of 0.56 beats laguna (0.22) but trails qwen3-coder (0.67). The V10 score of 2.0/5.0 was partly format-bias (now fixed) but the capability signal is real and mixed — AgentWorld is competitive on tcpdump filter quality but inconsistent on answer structure.

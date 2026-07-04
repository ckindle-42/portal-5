---
id: unit-SECURITY_FLEET_REVIEW_2026-06-2-security-group-training-purpose-map
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 2. Security Group \u2014 Training Purpose\
  \ Map"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "2. Security Group \u2014 Training Purpose Map"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.914738
updated_at: 1783195000.914738
---


Understanding what each model was actually built for changes every placement decision.

| Model | Base | Training purpose | Primary strength |
|---|---|---|---|
| `huihui_ai/baronllm-abliterated` | Llama-3.1-8B | 53K cybersec examples, 200+ cybersec domains (AlicanKiraz0/Cybersecurity-BaronLLM) | Broad security domain knowledge — offensive and defensive |
| `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` | Unknown | Vulnerability research and exploitation reasoning | Vuln-specific analysis and pen-test technique knowledge |
| `sylink/sylink:8b` | Qwen3-8B | SOC triage, threat intel, MITRE ATT&CK mapping, incident response | **Blue team** — defensive analysis, not offensive |
| `supergemma4-26b-uncensored:Q4_K_M` | Gemma 4 26B | General Gemma 4 with safety removed | Uncensored general quality; good at security because Gemma 4 is capable, not because security-specialized |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF` | Gemma 4 31B | General Gemma 4 uncensored, uncensored | Deep analysis quality at 31B; not security-specialized |
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` | Qwen3.6-35B MoE | Aggressively uncensored Qwen3.6 | Offensive uncensored with creative quality |
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | Unknown | Security **reasoning and analysis** (thinking-mode) | Long-form security analysis, threat modeling — analytical, not agentic |
| `devstral-small-2:latest` | Mistral | Agentic **software engineering** and coding | Sequential structured planning — works on chains because pentest orchestration resembles code; no security domain knowledge |
| `lfm2.5:8b` | LFM hybrid | Agentic tool use, multilingual (hybrid conv+attention) | Fast general agentic work; architecture diversity |
| `granite4.1:8b` | IBM Granite | Enterprise structured output, compliance, instruction following | Detection engineering, SPL/KQL, compliance reporting |

---

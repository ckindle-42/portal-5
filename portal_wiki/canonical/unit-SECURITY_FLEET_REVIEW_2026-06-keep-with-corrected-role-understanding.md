---
id: unit-SECURITY_FLEET_REVIEW_2026-06-keep-with-corrected-role-understanding
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Keep \u2014 with corrected role understanding"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "Keep \u2014 with corrected role understanding"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.9155421
updated_at: 1783195000.9155421
---


| Model | Cov | Depth | TPS | Training purpose | Role |
|---|---|---|---|---|---|
| `huihui_ai/baronllm-abliterated:latest` | **1.00** | 8.5 | 28.2 | Cybersecurity specialist — 53K examples, 200+ domains | **`auto-security` primary** — Run A: 1.00/1.00, 11s; quality 4/4 (Log4Shell correct); fastest 8B in batch |
| `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` | 1.00 | 9.5 | 28.7 | Vulnerability research | `auto-pentest`, `auto-security` — domain-specific vuln knowledge; quality 3/4 (Log4Shell gap documented) |
| `sylink/sylink:8b` | 1.00 | **12.0** | 11.8 | **SOC triage, DFIR, ATT&CK, IR** | **`auto-blueteam` anchor** — Run B: 1.00/1.00, 242s; quality 4/4; deepest chains + purpose-built defensive |
| `supergemma4-26b-uncensored:Q4_K_M` | 1.00 | 8.5 | 24.2 | General Gemma 4 uncensored | `auto-redteam`, `auto-security-uncensored` — Run C: 1.00/1.00, 36s; fleet bench confirmed clean |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF` | 1.00 | 10.5 | 5.2 | General Gemma 4 uncensored | `auto-purpleteam-exec` — quality 4/4; TPS 5.2 rules out interactive; right for long-form exec synthesis |
| `huihui_ai/qwen3.5-abliterated:9b` | 1.00 | 11.0 | 16.9 | General Qwen3.5 uncensored | Backbone generalist fallback — quality 4/4; proven backbone when specialists are loaded |

---
id: unit-SECURITY_FLEET_REVIEW_2026-06-4-final-proposed-security-group
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 4. Final Proposed Security Group"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: 4. Final Proposed Security Group
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.91661
updated_at: 1783195000.91661
---


```yaml
ollama-security:
  # Security domain specialists — know the field
  - huihui_ai/baronllm-abliterated:latest           # primary: 53K cybersec, 200+ domains, 28 TPS
  - hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M    # vuln research specialist, fast, 29 TPS

  # Blue team anchor — defensive, SOC, ATT&CK
  - sylink/sylink:8b                                # SOC/DFIR/ATT&CK purpose-built, depth 12

  # Uncensored offensive — red team and adversarial
  - supergemma4-26b-uncensored:Q4_K_M               # uncensored general quality, security:1.0
  # HauhauCS-Aggressive:Q4 NOT added — Run B 0.50 (stalled asrep_to_lateral); stays in creative only

  # Deep analysis / exec synthesis
  - hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF   # 31B quality for purpleteam-exec long-form

  # Cross-listed for architecture diversity + agentic tool discipline
  - lfm2.5:8b                                       # hybrid non-transformer, fast, tool-use native
  - granite4.1:8b                                   # structured output, detection eng, compliance
  - devstral-small-2:latest                         # coding discipline for deep chain workspaces

  # Generalist uncensored fallback
  - huihui_ai/qwen3.5-abliterated:9b                # proven backbone when specialists are loaded
```

**Remove from security group:**
- `Huihui-Qwen3.6-35B-A3B-abliterated-MTP` — errors
- `baronllm:q6_k` — template-broken variant
- `deepseek-r1:32b-q4_k_m` — reasoning model, wrong group
- `Qwable-3.6-35b` — FAIL per CANDIDATE_EVAL_V1; also `ollama rm`

**Move to reasoning group:**
- `Foundation-Sec-8B-Reasoning` — analytical security, not agentic

---

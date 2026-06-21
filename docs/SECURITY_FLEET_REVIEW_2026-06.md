# Security Fleet Review — June 2026

**Date**: 2026-06-21  
**Bench data**: `sec_bench_20260620T153821Z.json` (105 models, full fleet)  
**TPS data**: `bench_tps_20260621T030634Z.json` (286 results)  
**Completion bench**: `sec_bench_20260621T132602Z.json` (Run A — baronllm-abl, Foundation-Sec, devstral-small-2)  
**Prior plan**: `tests/PORTAL5_CANDIDATE_EVAL_V1.md` — covers prior removal decisions; read before changing workspace counts  
**Status**: All bench data complete. Ready for config changes.

---

## Context from CANDIDATE_EVAL_V1

Key decisions already locked in before this review cycle:

- **3 Qwable-27B dense variants were removed** — all <15 TPS. Not candidates.
- **Huihui-Qwen3.6-27B dense gate failed** — pipeline TPS 12.5, below 15 TPS threshold. Chain bench skipped; model out.
- **Qwable-35B security chain = FAIL** — 0.64 coverage, below 2/2 WIN threshold. Per CANDIDATE_EVAL_V1 Step 0, this required removal. Commit `9d3a63f` promoted it instead — this review corrects that.
- **devstral-small-2**: 15.5 TPS pipeline — below 20 TPS interactive floor. Stays in coding pool per Step 3. Chain bench (Run A) informs cross-listing only.

---

## 1. Workspace Intent Map

| Workspace | Groups pulled | Intent |
|---|---|---|
| `auto-pentest` | security only | Agentic offensive — multi-hop tool-chain execution |
| `auto-redteam` | security + general | Creative adversarial — novel attack paths, lateral thinking |
| `auto-redteam-deep` | security + general | Longer horizon, complex multi-pivot scenarios; latency acceptable |
| `auto-security` | security + general | Vulnerability analysis, threat modeling, security advice — domain knowledge matters more than chain mechanics |
| `auto-security-uncensored` | security + general | Same, no safety filters |
| `auto-blueteam` | **reasoning** + security + general | SOC triage, DFIR, ATT&CK mapping, detection engineering, SPL/KQL writing |
| `auto-purpleteam` | security + general | Attack synthesis mapped to detection response |
| `auto-purpleteam-deep` | security + **coding** + general | Purple + scripting exploits and detections; coding group matters |
| `auto-purpleteam-exec` | security + coding + general | Executive synthesis — attack surface to business risk narrative |

**Important**: `auto-blueteam` pulls from reasoning first, so deepseek-r1 and Foundation-Sec (once moved) are already available there. A model that scores 0 on offensive tool-chains may still be exactly right — just through the reasoning pathway.

---

## 2. Security Group — Training Purpose Map

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

## 3. Current Security Group — Decision per Model

### Remove

| Model | Cov | Reason |
|---|---|---|
| `hf.co/huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated-MTP-GGUF:latest` | 0.00 | Errors on every chain and tool probe. No path to recovery in current format. |
| `baronllm:q6_k` | 0.00 | Tool template bug caused chain failures (TASK_TOOLCALL_FIX_LOCKIN_V1 fixed this in the abliterated variant, not the q6_k). The base model is not the problem — this quantization/template combination is. |
| `deepseek-r1:32b-q4_k_m` | 0.00 | Cannot emit tool_calls — text_only on all probes. Not a model failure; it's a reasoning model in the wrong group. Already available to `auto-blueteam` through the reasoning group pathway. |
| `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` | 0.64 | Failed CANDIDATE_EVAL_V1 Step 0 threshold. Commit `9d3a63f` promoted it anyway — that decision is reversed here. Also: `ollama rm` this model. |

### Move (not remove)

| Model | From | To | Reason |
|---|---|---|---|
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | security | reasoning | Run A confirmed 400 error on every tool probe — cannot use tool manifests at all. But quality 1.0 in TPS bench and trained for security reasoning. Belongs in reasoning group where it contributes to `auto-blueteam` analytical work: ATT&CK analysis, threat modeling, DFIR reasoning. This is correct placement for its training, not a demotion. |

### Keep — with corrected role understanding

| Model | Cov | Depth | TPS | Training purpose | Role |
|---|---|---|---|---|---|
| `huihui_ai/baronllm-abliterated:latest` | **1.00** | 8.5 | 28.2 | Cybersecurity specialist — 53K examples, 200+ domains | **`auto-security` primary** — the most security-domain-trained model in the group; was previously primary before template issues; Run A confirmed: 1.00/1.00, 11s per chain, fastest of the batch |
| `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` | 1.00 | 9.5 | 28.7 | Vulnerability research | `auto-pentest`, `auto-security` — domain-specific vuln knowledge; fast |
| `sylink/sylink:8b` | 1.00 | **12.0** | 11.8 | **SOC triage, DFIR, ATT&CK, IR** | **`auto-blueteam` anchor** — deepest chains + purpose-built for defensive analysis. 267s/chain is fine for the analytical investigation pace of blueteam work. Previously misread as redteam-deep; its training says defensive. |
| `supergemma4-26b-uncensored:Q4_K_M` | 1.00 | 8.0 | 24.2 | General Gemma 4 uncensored | `auto-redteam`, `auto-security-uncensored` — strongest uncensored general quality (security:1.0 in TPS bench); good at security because Gemma 4 is broadly capable |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF` | 1.00 | 10.5 | 5.2 | General Gemma 4 uncensored | `auto-purpleteam-exec` — TPS 5.2 rules it out for interactive chains; 31B quality + general:1.0 is right for long-form executive synthesis where latency is acceptable |
| `huihui_ai/qwen3.5-abliterated:9b` | 1.00 | 11.0 | 16.9 | General Qwen3.5 uncensored | Backbone generalist fallback — covers gaps when specialized models are loaded |

### Add (data complete, decision clear)

| Model | Cov | Depth | TPS | Training purpose | Target role |
|---|---|---|---|---|---|
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` | 1.00 | 11.5 | 30.8 | Aggressively uncensored Qwen3.6 | `auto-redteam`, `auto-security-uncensored` — explicitly offensive uncensored; creative:1.0 quality; best chain depth + speed for adversarial creative work. Currently creative only. |
| `lfm2.5:8b` | 1.00 | 10.0 | 78.5 | Agentic tool use, hybrid architecture | `auto-security`, general security assistant — fast, agentic by design, unique non-transformer architecture adds diversity. Not security-domain trained but strong tool discipline. Currently general only. |
| `granite4.1:8b` | 1.00 | 8.0 | 19.3 | Enterprise structured output, compliance | `auto-blueteam` support — IBM-trained for structured output and instruction fidelity; IFEval 87.1; right for detection engineering, SPL/KQL writing, compliance analysis. Currently general + reasoning; cross-listing directly in security makes it selectable for `auto-blueteam` alongside sylink. |

### Conditional on Run A (now resolved)

| Model | Run A result | Decision |
|---|---|---|
| `devstral-small-2:latest` | Cov 1.00, depth 11.0, 45s — WIN | Cross-list in security for `auto-purpleteam-deep` and `auto-redteam-deep` only — depth 11 at 45s/chain is an asset for those workspaces where latency is accepted. Stays in coding pool as primary home. Its strength is agentic coding discipline applied to chain execution, not security domain knowledge. |
| `huihui_ai/baronllm-abliterated` | Cov 1.00, 11s — WIN | Already decided keep above. Run A resolved any doubt. |
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | Cov 0.00, 400 error — confirmed | Move to reasoning group. |

---

## 4. Final Proposed Security Group

```yaml
ollama-security:
  # Security domain specialists — know the field
  - huihui_ai/baronllm-abliterated:latest           # primary: 53K cybersec, 200+ domains, 28 TPS
  - hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M    # vuln research specialist, fast, 29 TPS

  # Blue team anchor — defensive, SOC, ATT&CK
  - sylink/sylink:8b                                # SOC/DFIR/ATT&CK purpose-built, depth 12

  # Uncensored offensive — red team and adversarial
  - supergemma4-26b-uncensored:Q4_K_M               # uncensored general quality, security:1.0
  - fredrezones55/.../HauhauCS-Aggressive:Q4        # aggressively uncensored, depth 11.5, 31 TPS

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

## 5. Role Corrections Summary

The fleet bench was read correctly for scores, but training purpose was not factored into placements. Two corrections beyond just adding/removing:

1. **SYLink → blueteam anchor, not redteam-deep**. Training is defensive (SOC, ATT&CK, IR). Its chain depth of 12 reflects SOC investigation multi-step patterns, not offensive TTPs. Correctly kept in security group but its primary workspace contribution should be `auto-blueteam`, not `auto-redteam-deep`.

2. **BaronLLM-abliterated → reinstate as auto-security primary**. Was primary before template issues. 53K domain examples is the deepest security-specific training in the group. Run A: 1.00/1.00 at 11s. Should lead `auto-security`.

3. **Foundation-Sec → reasoning group, not removal**. It reasons about security extremely well. Wrong format (thinking-mode, no tool_calls), wrong group (security agentic). Right domain knowledge for `auto-blueteam` analytical work.

4. **devstral-small-2 → security cross-list for deep workspaces only**. Not a security model. But agentic coding discipline maps to structured chain execution. Useful for `auto-purpleteam-deep` and `auto-redteam-deep` where its 15 TPS and depth 11 are assets.

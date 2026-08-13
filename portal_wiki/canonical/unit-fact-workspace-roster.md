---
id: unit-fact-workspace-roster
kind: what
title: 23 production + 93 eval workspaces
sources:
- type: code
  path: config/portal.yaml
  commit: ee9272eee208
last_generated_commit: ee9272eee208
claims:
- probe: workspaces.total
  pattern: '{value} total)'
confidence: high
tags:
- fact
- workspaces
created_at: 1784000421.2630541
updated_at: 1786638521.214427
---

# Workspace roster (23 production, 93 eval, 116 total)

## Production workspaces (acceptance/UAT scope, eval OFF)

| Workspace | Module | Model Hint |
|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-compliance` | compliance | `granite4.1:8b-ctx16k` |
| `auto-council` | general | `qwen3.6:27b-q4_K_M-ctx16k` |
| `auto-creative` | media | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` |
| `auto-daily` | general | `gemma4:26b-a4b-it-qat-ctx8k` |
| `auto-data` | research | `granite4.1:30b-ctx64k` |
| `auto-documents` | documents | `granite4.1:8b-ctx16k` |
| `auto-extract-uncensored` | documents | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` |
| `auto-general-uncensored` | general | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` |
| `auto-image` | media | `granite4.1:8b-ctx16k` |
| `auto-math` | general | `phi4-mini-reasoning:latest-ctx24k` |
| `auto-music` | media | `lfm2.5:8b-ctx8k` |
| `auto-reasoning` | general | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` |
| `auto-research` | research | `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` |
| `auto-video` | media | `granite4.1:8b-ctx16k` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` |
| `tools-specialist` | general | `granite4.1:8b-ctx8k` |

## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)

- `bench-agents-a1`
- `bench-agentworld`
- `bench-aquila-mini-35b-a3b`
- `bench-aquila-research`
- `bench-baronllm-q6k`
- `bench-bugtrace-ultra-27b`
- `bench-cybersecqwen-4b`
- `bench-cybersecqwen-4b-toolfix`
- `bench-deepseek-r1`
- `bench-deepwen-cad`
- `bench-devstral`
- `bench-devstral-small-2`
- `bench-devstral-small-2-ctx8k`
- `bench-dolphin-llama3`
- `bench-e2b-pentest`
- `bench-exec-exploit`
- `bench-exec-reasoning`
- `bench-exec-recon`
- `bench-fastcontext`
- `bench-foundation-sec-8b-reasoning`
- `bench-gemma4-12b`
- `bench-gemma4-12b-agentic`
- `bench-gemma4-12b-general`
- `bench-gemma4-26b-heretic`
- `bench-gemma4-26b-optiq`
- `bench-gemma4-26b-qat`
- `bench-gemma4-31b-crack`
- `bench-gemma4-31b-qat`
- `bench-gemma4-31b-qat-ctx8k`
- `bench-gemma4-e2b`
- `bench-gemma4-e2b-qat-ctx8k`
- `bench-gemma4-e4b`
- `bench-gemma4-e4b-qat`
- `bench-gemma4-e4b-qat-ctx8k`
- `bench-glm`
- `bench-glm-reap`
- `bench-glm-z1-rumination`
- `bench-glm-z1-rumination-ctx64k`
- `bench-glm47-flash-reap`
- `bench-gptoss`
- `bench-granite41-30b`
- `bench-granite41-8b`
- `bench-hermes3`
- `bench-huihui-gemma4-e2b-abliterated-ctx8k`
- `bench-huihui-qwen36-27b`
- `bench-huihui-qwen36-35b-a3b`
- `bench-jackrong-dsv4-4b`
- `bench-jackrong-dsv4-9b`
- `bench-laguna`
- `bench-lfm-micro-1p2b`
- `bench-lfm-micro-230m`
- `bench-lfm-micro-350m`
- `bench-lfm25-8b`
- `bench-lfm25-8b-uncensored`
- `bench-llama32-3b`
- `bench-llama32-3b-abliterated`
- `bench-llama32-3b-q8`
- `bench-magistral-small`
- `bench-meta-secalign-8b`
- `bench-mistral-small-3-2`
- `bench-mistral7b-uncensored`
- `bench-muse-glimmer-30b`
- `bench-nex-n2-mini`
- `bench-north-mini-code`
- `bench-omnicoder2`
- `bench-ornith-35b`
- `bench-phi4`
- `bench-qwable-3.6-35b`
- `bench-qwable-35b`
- `bench-qwen3-14b-abliterated`
- `bench-qwen3-coder-30b`
- `bench-qwen3-coder-next`
- `bench-qwen3-coder-next-abliterated`
- `bench-qwen3.6`
- `bench-qwen35-9b-heretic-vision`
- `bench-qwen35-abliterated`
- `bench-qwen36-27b`
- `bench-qwen36-27b-mtp`
- `bench-qwen36-27b-mtp-undrafted`
- `bench-qwen36-27b-optiq`
- `bench-qwen36-27b-ud`
- `bench-qwen36-35b-a3b`
- `bench-qwen36-35b-a3b-ud`
- `bench-qwen36-hauhaucs`
- `bench-qwopus-coder-mtp-v2`
- `bench-security-slm-1p5b`
- `bench-supergemma4-sec`
- `bench-superqwen-agentworld-ablit`
- `bench-sylink`
- `bench-sylink-8b`
- `bench-sylink-ctx8k`
- `bench-vulnllm-r-7b`
- `bench-vulnllm-r7b`

## Why

The roster is the workspace mapping in `config/portal.yaml`, split into the production workspaces that acceptance/UAT exercises and the eval/bench workspaces gated behind `PORTAL_ENABLE_EVAL=1`. The counts and the per-workspace model hints come straight from that file, so the roster cannot disagree with what routing serves.

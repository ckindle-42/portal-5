---
id: unit-fact-workspace-roster
kind: what
title: 22 production + 60 eval workspaces
sources:
- type: code
  path: config/portal.yaml
  commit: d16cb24ec652
last_generated_commit: d16cb24ec652
confidence: high
tags:
- fact
- workspaces
created_at: 1784000421.2630541
updated_at: 1784056264.227256
---

# Workspace roster (22 production, 60 eval, 82 total)

## Production workspaces (acceptance/UAT scope, eval OFF)

| Workspace | Module | Model Hint |
|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-compliance` | compliance | `granite4.1:8b-ctx16k` |
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
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k` |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` |
| `auto-video` | media | `granite4.1:8b-ctx16k` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` |
| `tools-specialist` | general | `granite4.1:8b-ctx8k` |

## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)

- `bench-agents-a1`
- `bench-agentworld`
- `bench-bugtrace-ultra-27b`
- `bench-cybersecqwen-4b-toolfix`
- `bench-devstral`
- `bench-devstral-small-2`
- `bench-e2b-pentest`
- `bench-exec-exploit`
- `bench-exec-reasoning`
- `bench-exec-recon`
- `bench-fastcontext`
- `bench-gemma4-12b`
- `bench-gemma4-12b-agentic`
- `bench-gemma4-26b-optiq`
- `bench-gemma4-26b-qat`
- `bench-gemma4-31b-crack`
- `bench-gemma4-31b-qat`
- `bench-gemma4-e2b`
- `bench-gemma4-e4b`
- `bench-gemma4-e4b-qat`
- `bench-glm`
- `bench-glm-reap`
- `bench-glm-z1-rumination`
- `bench-gptoss`
- `bench-granite41-30b`
- `bench-granite41-8b`
- `bench-huihui-qwen36-27b`
- `bench-huihui-qwen36-35b-a3b`
- `bench-laguna`
- `bench-lfm-micro-1p2b`
- `bench-lfm-micro-230m`
- `bench-lfm-micro-350m`
- `bench-lfm25-8b`
- `bench-lfm25-8b-uncensored`
- `bench-meta-secalign-8b`
- `bench-mistral7b-uncensored`
- `bench-nex-n2-mini`
- `bench-north-mini-code`
- `bench-omnicoder2`
- `bench-ornith-35b`
- `bench-qwable-35b`
- `bench-qwen3-14b-abliterated`
- `bench-qwen3-coder-30b`
- `bench-qwen3-coder-next`
- `bench-qwen3-coder-next-abliterated`
- `bench-qwen35-9b-heretic-vision`
- `bench-qwen35-abliterated`
- `bench-qwen36-27b`
- `bench-qwen36-27b-mtp`
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
- `bench-vulnllm-r7b`

---
id: unit-fact-workspace-roster
kind: what
title: 25 production + 53 eval workspaces
sources:
- type: code
  path: config/portal.yaml
  commit: 3de59b6c4ea5
claims:
- probe: workspaces.total
  pattern: '{value} total)'
confidence: high
tags:
- fact
- workspaces
created_at: 1784000421.2630541
updated_at: 1788392706.002791
---

# Workspace roster (25 production, 53 eval, 78 total)

## Production workspaces (acceptance/UAT scope, eval OFF)

| Workspace | Module | Model Hint |
|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx256k` |
| `auto-compliance` | compliance | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` |
| `auto-council` | general | `qwen3.6:27b-q4_K_M-ctx16k` |
| `auto-creative` | media | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` |
| `auto-daily` | general | `gemma4:26b-a4b-it-qat-ctx8k` |
| `auto-data` | research | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` |
| `auto-documents` | documents | `granite4.1:8b-ctx16k` |
| `auto-extract-uncensored` | documents | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k` |
| `auto-general-uncensored` | general | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` |
| `auto-image` | image | `granite4.1:8b-ctx16k` |
| `auto-math` | general | `phi4-mini-reasoning:latest-ctx24k` |
| `auto-music` | media | `lfm2.5:8b-ctx8k` |
| `auto-nemotron` | general | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx8k` |
| `auto-reasoning` | general | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` |
| `auto-research` | research | `portal5/xyz-aquila-mini:q4_k_m-ctx16k` |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` |
| `auto-uncensored-throwaway` | general | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` |
| `auto-video` | video | `granite4.1:8b-ctx16k` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` |
| `tools-specialist` | general | `granite4.1:8b-ctx8k` |

## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)

- `bench-agentworld`
- `bench-baronllm-q6k`
- `bench-cad-prior`
- `bench-e2b-pentest`
- `bench-exec-exploit`
- `bench-exec-reasoning`
- `bench-exec-recon`
- `bench-foundation-sec-8b-reasoning`
- `bench-gemma4-12b`
- `bench-gemma4-12b-agentic`
- `bench-gemma4-26b-heretic`
- `bench-gemma4-26b-optiq`
- `bench-gemma4-26b-qat`
- `bench-gemma4-31b-qat`
- `bench-gemma4-e2b`
- `bench-gemma4-e4b`
- `bench-gemma4-e4b-qat`
- `bench-gemma4-heretic-coder`
- `bench-glm`
- `bench-granite41-30b`
- `bench-granite41-8b`
- `bench-hauhaucs-coder`
- `bench-hermes3`
- `bench-huihui-qwen36-27b`
- `bench-huihui-qwen36-35b-a3b`
- `bench-laguna`
- `bench-lfm25-8b`
- `bench-lfm25-8b-uncensored`
- `bench-llama32-3b-abliterated`
- `bench-magistral-small`
- `bench-mistral-small-3-2`
- `bench-moecad`
- `bench-nex-n2-mini`
- `bench-north-mini-code`
- `bench-omnicoder2`
- `bench-ornith-35b`
- `bench-ornith15-coder`
- `bench-qwable-35b`
- `bench-qwen3-14b-abliterated`
- `bench-qwen3-coder-30b`
- `bench-qwen3-coder-next`
- `bench-qwen3-coder-next-abliterated`
- `bench-qwen35-9b-heretic-vision`
- `bench-qwen35-abliterated`
- `bench-qwen36-27b-optiq`
- `bench-qwen36-35b-a3b-ud`
- `bench-qwen36-cad`
- `bench-qwen36-hauhaucs`
- `bench-qwen38-27b`
- `bench-qwen38-flash-next-reap288`
- `bench-supergemma4-sec`
- `bench-vulnllm-r-7b`
- `bench-vulnllm-r7b`

## Why

The roster is the workspace mapping in `config/portal.yaml`, split into the production workspaces that acceptance/UAT exercises and the eval/bench workspaces gated behind `PORTAL_ENABLE_EVAL=1`. The counts and the per-workspace model hints come straight from that file, so the roster cannot disagree with what routing serves.

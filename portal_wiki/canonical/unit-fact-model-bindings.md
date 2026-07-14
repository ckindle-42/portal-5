---
id: unit-fact-model-bindings
kind: what
title: "model bindings \u2014 0 reachability gap(s)"
sources:
- type: code
  path: config/backends.yaml
  commit: d16cb24ec652
- type: code
  path: config/portal.yaml
  commit: d16cb24ec652
- type: code
  path: config/personas/
  commit: d16cb24ec652
last_generated_commit: d16cb24ec652
confidence: high
tags:
- fact
- model-bindings
- reachability
created_at: 1784000421.433863
updated_at: 1784056264.396721
---

# Model bindings (reachability-resolved)

What each production workspace/persona actually SERVES, not what it
claims. A row marked GAP means the intended model is unreachable via
the workspace's routing groups and silently falls back to the pool
default.

## Workspace model_hint reachability

| Workspace | model_hint | Reachable |
|---|---|---|
| `auto` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | yes |
| `auto-audio` | `gemma4:12b-it-qat-ctx8k` | yes |
| `auto-bigfix` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-cad` | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` | yes |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-compliance` | `granite4.1:8b-ctx16k` | yes |
| `auto-creative` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` | yes |
| `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | yes |
| `auto-data` | `granite4.1:30b-ctx64k` | yes |
| `auto-documents` | `granite4.1:8b-ctx16k` | yes |
| `auto-extract-uncensored` | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` | yes |
| `auto-general-uncensored` | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | yes |
| `auto-image` | `granite4.1:8b-ctx16k` | yes |
| `auto-math` | `phi4-mini-reasoning:latest-ctx24k` | yes |
| `auto-music` | `lfm2.5:8b-ctx8k` | yes |
| `auto-reasoning` | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | yes |
| `auto-research` | `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` | yes |
| `auto-security` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k` | yes |
| `auto-spl` | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` | yes |
| `auto-video` | `granite4.1:8b-ctx16k` | yes |
| `auto-vision` | `qwen3-vl:32b-ctx8k` | yes |
| `tools-specialist` | `granite4.1:8b-ctx8k` | yes |

## Persona model_pin reachability

| Persona | Workspace | model_pin | Reachable |
|---|---|---|---|
| `devstral_coder` | `auto-coding` | `devstral-small-2:latest-ctx8k` | yes |
| `gemma4jangvision` | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` | yes |
| `gemma_vision` | `auto-vision` | `gemma4:31b-it-qat-ctx8k` | yes |
| `glm-coder` | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | yes |
| `glm-thinker` | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` | yes |
| `magistralstrategist` | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | yes |

**0 reachability gap(s)** — clean.

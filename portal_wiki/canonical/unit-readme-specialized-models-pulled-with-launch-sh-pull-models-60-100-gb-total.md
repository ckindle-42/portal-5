---
id: unit-readme-specialized-models-pulled-with-launch-sh-pull-models-60-100-gb-total
kind: what
title: "README \u2014 Specialized models (pulled with `./launch.sh pull-models`, ~60\u2013\
  100 GB total)"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/cli/update.py
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.686558
updated_at: 1784946220.686558
---

The specialized model catalog lives in `config/backends.yaml`, grouped by routing
group, and is what the workspaces' `model_hint:` values reference. Verified
members per group:

- **Security:** JANG-CRACK 31B (pentest, `gemma-4-31b-jang-crack-Q4_K_M.gguf`),
  SuperGemma4-26B (red team), BaronLLM (security analyst, `huihui_ai/baronllm-abliterated`),
  sylink:8b (blue team — SOC triage, DFIR, ATT&CK); Foundation-Sec-8B sits in the
  reasoning group for analytical blue-team work.
- **Coding:** Qwen3-Coder-30B MoE, Laguna-XS.2 33B-A3B (`laguna-xs.2:Q4_K_M`, the
  `auto-coding` laguna variant), Devstral-Small-2, GLM-4.7-Flash REAP.
- **Reasoning:** DeepSeek-R1-0528-Qwen3-8B (auto-reasoning), GLM-Z1-Rumination-32B,
  GPT-OSS 20B, Tongyi-DeepResearch-abliterated.
- **Vision:** Qwen3-VL 32B (auto-vision), Gemma 4 31B dense QAT (`gemma4:31b-it-qat`),
  Gemma 4 E4B QAT (`gemma4:e4b-it-qat`).

Pull mechanics are registry-driven: `./launch.sh pull-models` pulls the active
(non-retired) entries from the `models:` block of `config/portal.yaml`, while the
`./launch.sh update` flow's default pull list in
`portal/platform/inference/cli/update.py` (`_DEFAULT_MODELS`) covers a broader
set that also includes `deepseek-coder-v2:16b-lite-instruct-q4_K_M`.

## Why

Cataloging specialized models in `config/backends.yaml` rather than hardcoding
them in the router keeps one authoritative list for routing, admission and pull
targets, so adding or retiring a lane is a config change, not a code change. The
split between the pull-models registry and the update default set reflects two
workflows: a deliberate operator pull versus a full upgrade that refreshes the
whole fleet.

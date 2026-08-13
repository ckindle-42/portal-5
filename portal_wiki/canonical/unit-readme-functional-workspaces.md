---
id: unit-readme-functional-workspaces
kind: what
title: "README \u2014 Functional Workspaces"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/router/workspaces.py
- type: code
  path: portal/platform/inference/config.py
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.679698
updated_at: 1784946220.679698
---

The functional workspaces are the everyday entries in the Open WebUI model
dropdown. Each is defined in `config/portal.yaml` under `workspaces:` with a
`model_hint:` that pins the served model and a `tools:` array that grants the
toolset. Selecting a workspace activates both at once. The current functional set,
with the pinned model, is:

| Workspace | Pinned model (`model_hint`) |
|---|---|
| `auto` | Qwen3.5-abliterated 9b (context 8k) |
| `auto-daily` | `gemma4:26b-a4b-it-qat` (web_search, documents, memory tools) |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M` (code sandbox tools) |
| `auto-reasoning` | DeepSeek-R1-0528-Qwen3-8B (context 64k) |
| `auto-council` | `qwen3.6:27b-q4_K_M` (no tools) |
| `auto-research` | `tongyi-deepresearch-abliterated` (web_search, web_fetch, kb_search) |
| `auto-vision` | `qwen3-vl:32b` |
| `auto-creative` | Qwen3.6-35B-A3B uncensored (HauhauCS) |
| `auto-documents` | `granite4.1:8b` (document create/read tools) |
| `auto-data` | `granite4.1:30b` (execute_python, create_excel) |
| `auto-math` | `phi4-mini-reasoning` |
| `auto-audio` | `gemma4:12b-it-qat` (transcribe tools) |
| `auto-music` | `lfm2.5:8b` (generate_music, speak, transcribe) |
| `auto-video` | shelved — retained in config but not operated |
| `auto-image` | `granite4.1:8b` (generate_image, ComfyUI tools) |
| `auto-cad` | `qwen3-coder:30b-a3b-q4_K_M` (render_mesh, render_openscad, convert_cad) |
| `auto-spl` | Qwen3-Coder-Next abliterated (classify_vulnerability, kb_search) |
| `auto-compliance` | `granite4.1:8b` (NERC CIP gap analysis) |
| `auto-bigfix` | `qwen3-coder:30b-a3b-q4_K_M` (BigFix relevance scripting) |
| `auto-security` | VulnLLM-R-7B (web_search, classify_vulnerability, sandbox) |
| `auto-general-uncensored` | `huihui_ai/Qwen3.6-abliterated:27b` (uncensored generalist) |
| `auto-extract-uncensored` | LFM2.5-8B-A1B uncensored (extraction, no tool loop) |
| `tools-specialist` | `granite4.1:8b` (execute_python, remember, recall) |

The `auto-coding` and `auto-security` families express variants (for example
`laguna`, `uncensored`, `pentest`, `purpleteam`) as persona `variant:` fields
instead of sibling workspaces.

## Why

Mapping a dropdown entry to a (model, toolset) pair is what makes the platform
usable without prompt discipline: the user picks an intent, and the workspace
carries the model weight class and the capability grants. Keeping that mapping in
`config/portal.yaml` lets operators add or retune a lane without touching code,
and `sync-config` pushes it into routing and the Open WebUI presets.

---
id: unit-HOWTO-6-security-analysis
kind: why
title: "HOWTO \u2014 6. Security Analysis"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/router/preinject.py
last_generated_commit: db75e444cdca521f9be63059be9180bb380a4a64
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.841096
updated_at: 1783195000.841096
---

**What:** One base workspace (`auto-security`) covering research, simulation, and execution tiers. The former sibling workspaces collapsed into `?variant=` query params (or a persona's `variant:` field) are resolved by `_resolve_workspace_variant` in `portal/platform/inference/router/preinject.py` instead of separate workspace ids. The complete variant catalog — including the newer `blueteam-orchestrated` and `blueteam-council` — is defined under `auto-security.variants` in `config/portal.yaml`; `unit-fact-security-variants` is the live index.

Verified variant summary from `config/portal.yaml`:

| Variant | Tier | Model hint | Tools |
|---|---|---|---|
| *(base)* | Research | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search, kb_list |
| `uncensored` | Research | `huihui_ai/baronllm-abliterated:latest-ctx8k` | execute_bash, execute_python, remember, recall |
| `redteam` | Simulation | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | none |
| `redteam-deep` | Simulation | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | none |
| `blueteam` | Research | `granite4.1:8b-ctx8k` | web_search, web_fetch, classify_vulnerability, kb_search, kb_list |
| `pentest` | Execution | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` | execute_bash, execute_python, web_search |
| `purpleteam` | Simulation, 2-hop | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` → `granite4.1:8b-ctx8k` | none |
| `purpleteam-deep` | Simulation, 4-hop | abliterated → granite → `qwen3-coder:30b-a3b-q4_K_M` → `qwen3.6:27b-q4_K_M` | none |
| `purpleteam-exec` | Execution, 4-hop | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` → same chain | execute_bash, execute_python, web_search |

The `pentest` variant runs inside the `portal5-attack` Kali image with `$LAB_TARGET_*` env vars pre-injected and a hard prompt constraint that it open with a live `execute_bash` call. Note the `pentest` model is the Qwen3.6-35B HauhauCS abliterated MoE, which replaced an earlier `gemma-4-abliterated:E2b-qat` pick after that model failed the tool-call reliability gate.

## Why

Collapsing the sibling workspaces into one base plus variants removed duplicate model registrations, prompt text, and tool grants that had drifted apart. The variant mechanism is a pure config transform applied at request time, so a tier change (an extra hop, a guardrail flip) is an edit to `config/portal.yaml`, not pipeline code, and the same resolution path serves both `?variant=` query params and persona `variant:` fields.

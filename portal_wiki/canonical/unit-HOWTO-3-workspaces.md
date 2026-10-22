---
id: unit-HOWTO-3-workspaces
kind: why
title: "HOWTO \u2014 3. Workspaces"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/config.py
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
- type: code
  path: portal/platform/inference/model_cards.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: tests/wfe/settings_audit.py
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.839686
updated_at: 1792668000
---

**What:** Each workspace routes to a specialized model and activates the relevant tools.

**How:** Workspaces are defined in `config/portal.yaml` under the `workspaces:` block — each entry declares `module`, `name`, `model_hint`, `tools`, and `expose_to_owui`. Select one from the model dropdown; the exposed ones are exactly those with `expose_to_owui: true`. `./launch.sh sync-config` regenerates the derived artifacts (`workspace_routing` in `config/backends.yaml`, `.mcp.json`, and the Open WebUI workspace presets under `imports/openwebui/workspaces/`) so `config/portal.yaml` stays the single source of truth.

`thinking_budget` is an optional positive integer on a workspace or a variant (`dab8ff79`). Streaming and non-streaming chat completions, and every chain hop, pass it through `_inject_omlx_options` or `_inject_ollama_options`. On oMLX it is forwarded as the top-level field `thinking_budget`. A value already present on the request is kept; the seat value is filled in only when the field is absent. Ollama does not receive the integer: `to_native_request` omits it from `/api/chat`. `card_thinking_level` maps it to the nearest name in that model's card `thinking_budget_levels`, and that name is sent as `think` only when the request has no `think` yet and the seat's `think` is not false. With no documented levels the integer is left unused and a debug line records that it was ignored. The OpenAI-shaped body keeps the integer so a later hop still sees the caller's value. Council payloads are built beside those injectors and do not receive this field. `settings_audit` treats a positive `thinking_budget` as a bound for `thinking_unbounded`, the same way it treats `predict_limit`.

For the full live roster (production + eval workspaces, module, model hint) use `unit-fact-workspace-roster` — do not maintain a second handwritten table here. A few flagship examples verified against `config/portal.yaml`:

| Workspace | model_hint (Ollama) | Key tools |
|---|---|---|
| `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward |
| `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_word_document, execute_python |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | execute_python, execute_nodejs, execute_bash |
| `auto-security` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | web_search, classify_vulnerability, execute_bash |
| `auto-documents` | `granite4.1:8b-ctx16k` | create_word_document, create_excel, create_powerpoint |
| `auto-music` | `lfm2.5:8b-ctx8k` | minimax_generate, minimax_status, speak, clone_voice, register_voice |
| `auto-vision` | `qwen3-vl:32b-ctx8k` | transcribe_audio, generate_image |

`auto-video` is exposed with `generate_video` / `animate_image` (shipped enabled — see the Video Generation unit). Eval workspaces (the `bench-*` set) additionally require `PORTAL_ENABLE_EVAL=1` at pipeline startup.

**Example — coding:** select `Portal Code Expert` and ask a coding question; `auto-coding` answers with Qwen3-Coder-30B and its sandbox tools (`execute_bash`, `execute_python`, `sandbox_status`) run code on request.

## Why

Workspaces are pure configuration, not code. Putting name, model hint, tool grants, and OWUI exposure in one YAML block means adding or tuning a lane never requires a pipeline code change, and the module-toggle layer can hide an entire workspace family at sync time. Mechanically deriving the presets keeps the dropdown and routing in lockstep, which is why `sync-config` idempotence is enforced by the test suite.

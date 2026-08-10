---
id: unit-known-limitations-baronllm-text-only-tool-output-auto-security-mcp-tools-non-functional
kind: what
title: "KNOWN_LIMITATIONS \u2014 baronllm text_only tool output \u2014 auto-security\
  \ MCP tools non-functional"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/router/tools.py
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: tests/uat_catalog/g_auto_security.py
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6662889
updated_at: 1784946220.6662889
---

- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (in the security pool; `auto-security`'s `model_hint` primary is now `VulnLLM-R-7B` per `config/portal.yaml`) once output tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. The pipeline's `_dispatch_tool_call` in `portal/platform/inference/router/tools.py` reads only the native `tool_calls` array, so tool intent in prose never triggered dispatch. UAT `g_auto_security.py` documents the `text_only` outcome from the 2026-06-18 `--audit-tools` probe.
- **Impact**: MCP tool use (e.g. `execute_python`, `classify_vulnerability`) was not dispatched for such requests; prose security analysis was unaffected.
- **Status**: RESOLVED 2026-06-20 (TASK_TOOLCALL_FIX_LOCKIN_V1). A corrected tool-calling chat template made baronllm emit structured `tool_calls`; the `--audit-tools` probe then returned `tool_call`. `supports_tools: true` is recorded in `config/backends.yaml` for both `huihui_ai/baronllm-abliterated` entries, backed by the live probe. `baronllm:q6_k` remains `supports_tools: false`.
- **Do not re-enable** `supports_tools: true` for a baronllm tag without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` and confirming outcome=`tool_call`. `_model_supports_tools` in `portal/platform/inference/router/validation.py` is what gates dispatch on the declared flag.

## Why

A model's `supports_tools` declaration must be backed by a live response probe, not by inspecting its Ollama template header. The pipeline treats the flag as authoritative — `_model_supports_tools` gates whether tool schemas are exposed and dispatch is attempted — so a false positive silently degrades every request into a narrated tool-call with no dispatch. The audit command exists to make that verification mechanical and repeatable before any flag is set.

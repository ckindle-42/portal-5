---
id: unit-known-limitations-baronllm-text-only-tool-output-auto-security-mcp-tools-non-functional
kind: what
title: "KNOWN_LIMITATIONS \u2014 baronllm text_only tool output \u2014 auto-security\
  \ MCP tools non-functional"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "baronllm text_only tool output \u2014 auto-security MCP tools non-functional"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6662889
updated_at: 1784946220.6662889
---

- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (formerly auto-security primary; VulnLLM-R-7B is now the model_hint primary as of SECURITY_FLEET_REVIEW_2026-06, though baronllm remains in the security pool) outputs tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. Ollama's llama.cpp backend does not parse this as a function-call delta. Result: the pipeline's `_dispatch_tool_call` path is never triggered for auto-security requests that attempt MCP tool use.
- **Evidence**: `audit-tools 2026-06-18` probe — outcome `text_only`, content: `{"name":"get_current_time","parameters}:{ "city": "Paris" }`. UAT TV-02 (execute_python proof) and TV-03 (classify_vulnerability) both show tool not dispatched. Previous `supports_tools: true` marking (TASK_TOOL_AUDIT_V2) was a false positive from Ollama template header inspection, not a live response probe.
- **Impact**: Auto-security cannot use `execute_bash`, `execute_python`, `classify_vulnerability`, or any pipeline-dispatched MCP tool. TV-02 grades as WARN (non-critical assertion). Prose security analysis and code audits still work (text generation is unaffected).
- **Resolution path**: (a) Fix baronllm's Ollama chat template to emit proper `tool_calls` structure — this requires inspecting the model's tokenizer_config and Ollama template to align with llama.cpp's tool-call parsing; OR (b) Replace baronllm with a model in the auto-security chain that passes the live probe (e.g., qwen3.5-abliterated:9b was confirmed tool_call in a prior audit).
- **Status**: ✅ RESOLVED 2026-06-20 (TASK_TOOLCALL_FIX_LOCKIN_V1). A corrected tool-calling chat template makes baronllm emit structured `tool_calls`. Fleet `--audit-tools` confirmed outcome=`tool_call` and the security chain scored 8/8 1.00 WIN. Resolution path (a) — template fix — was taken; no model swap required. `supports_tools` flipped to `true` in `config/backends.yaml` (both entries), backed by the live probe. The same template fix also recovered HauhauCS (no_tool → tool_call).
- **Do not re-enable** `supports_tools: true` for baronllm without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` or the direct Ollama probe and confirming outcome=`tool_call`. *(This gate was satisfied by the 2026-06-20 fleet audit.)*

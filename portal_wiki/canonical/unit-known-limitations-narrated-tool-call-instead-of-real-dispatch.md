---
id: unit-known-limitations-narrated-tool-call-instead-of-real-dispatch
kind: what
title: Model Narrates a Fake Tool Call Instead of Invoking the Real One (Resolved)
sources:
- type: code
  path: portal/platform/inference/router/tools.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
- type: code
  path: tests/unit/test_pipeline.py
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- known-limitations
- resolved
- tool-calling
- verified-v1
created_at: 1785451583.192746
updated_at: 1785458075
---

- **ID**: P5-TOOL-NARRATION-001
- **Status**: RESOLVED 2026-07-30.
- **Description**: Under a multi-tool payload, a tool-capable model sometimes narrates a
  plausible-looking pseudo tool-call in plain text — e.g.
  `<function=execute_python>...</function></tool_call>` (note the mismatched/absent opening
  `<tool_call>` tag) — instead of emitting Ollama's real structured `tool_calls` field. The
  pipeline's `_dispatch_tool_call` (`portal/platform/inference/router/tools.py`) only ever
  reads the model's native `tool_calls` array, so this narrated text passes straight through
  to the user as if it were a normal, successful answer.
- **Reproduced directly** (bypassing the harness/pipeline entirely, isolating the model): the
  same model + prompt + a single-tool payload against Ollama's `/api/chat` succeeds every
  time with a clean `tool_calls` response. The exact same request with the workspace's full
  multi-tool payload (4+ tools) fails intermittently — 4 repeated identical calls: 3 succeeded
  with real `tool_calls`, 1 narrated fake text. This is genuine sampling-driven unreliability
  that worsens with more tools in context, not a wiring or schema bug.
- **Affected UAT cases at v8.0.0**: `T-01`/`T-02`/`T-03` (Code Sandbox exact-execution,
  `auto-coding`, `qwen3-coder`) and the Document Generation family (`T-04`/`T-05`/`T-06`/`WS-10`,
  `auto-documents`, `granite4.1`) both show this pattern — the latter confirmed NOT a document-
  tooling regression (the real `create_word_document` tool works perfectly when dispatched
  directly; see the MCP v2 migration audit) but the same narration-instead-of-dispatch failure
  under retry/backend-instability conditions.
- **Resolution**: The pipeline now recognizes explicit side-effect requests before model
  dispatch. `_select_explicit_required_tool()` maps conservative execution and artifact-creation
  intents to one tool only (Python/Bash/Node execution or Word/Excel/PowerPoint creation), but
  only when that tool is already in the resolved workspace/persona whitelist. Both streaming
  and non-streaming paths then expose only that schema and set `tool_choice=required`.
- **Why this fix**: The direct reproduction proved the same model was reliable with one tool
  and intermittent with the full multi-tool payload. Deterministic narrowing removes the
  ambiguity at its source without buffering the streaming hot path and without forcing tools
  for ordinary code-writing, prose-documentation, or document-reading prompts.
- **Safety boundary**: Client `tool_choice=none`, `portal_no_tools`, and non-matching prompts
  retain their prior behavior. A selected tool must be allow-listed; the selector never grants
  a capability. Unit coverage includes the affected UAT prompt shapes and negative cases.

## Why

The direct reproduction proved the same model was reliable with one tool and intermittent with the full multi-tool payload, so the failure is sampling-driven ambiguity under schema load, not wiring. Narrowing the exposed schema to one required tool for explicit side-effect intents removes the ambiguity at its source without buffering the streaming hot path, and the allow-list plus retained `tool_choice=none` behavior keeps the selector from ever granting a capability it did not already have.

---
id: unit-known-limitations-narrated-tool-call-instead-of-real-dispatch
kind: what
title: Model Narrates a Fake Tool Call Instead of Invoking the Real One (Open)
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  section: Model Narrates a Fake Tool Call Instead of Invoking the Real One (Open)
- type: code
  path: portal/platform/inference/router/tools.py
last_generated_commit: ''
confidence: high
tags:
- known-limitations
- tool-calling
- open
created_at: 1785451583.192746
updated_at: 1785451583.192746
---

- **ID**: P5-TOOL-NARRATION-001
- **Status**: OPEN — active problem, not accepted flakiness.
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
- **Why not fixed here**: A live-content fix requires the streaming pipeline
  (`portal/platform/inference/router/streaming.py`) to detect the pattern in the model's
  *content* stream and treat it as a dispatch failure — but content is forwarded to the client
  chunk-by-chunk as it streams, before the full text (and therefore the pattern) is knowable.
  Detecting this safely means buffering full content before forwarding, a real architectural
  change to a delicate hot path this project explicitly gates behind a live `smoke_stream.sh`
  run before any commit — not something to improvise mid-session.
- **Next action**: Design a proper fix before implementing: options include (a) buffering
  content for pattern-detection only on tool-enabled workspaces (bounded scope, still a real
  streaming-behavior change needing the live gate), (b) a narrower `tool_choice` scope for
  requests that specifically require tool execution rather than blanket-forcing it workspace-
  wide, or (c) generation-parameter tuning to reduce narration likelihood. Needs a deliberate
  design decision, not a one-line patch.

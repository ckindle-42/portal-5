---
id: unit-known-limitations-antares-gate-e1-gated-download
kind: what
title: "KNOWN_LIMITATIONS \u2014 Antares-1b: broken special-token handling (not arch,\
  \ not a gate)"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786309400.0
updated_at: 1786311400.0
---

- **ID**: P5-ANTARES-GATE-E1
- **Status**: Open, honest-BLOCKED — root cause required two corrections before landing on the
  real one. TASK-BATCH-BENCH-001 Part E finding.
- **Correction history** (kept because each wrong turn is a real lesson): pass 1 concluded
  "gated, unavailable" from `ollama list` alone, without attempting a pull — wrong, ungated
  community GGUF conversions exist. Pass 2, after actually pulling and probing two independent
  quants and seeing garbage chat output (`@@@@@@@@@@@@@@@@`) on both, concluded "arch mismatch"
  (`granitemoehybrid` mapped down to plain `granite`) — also wrong, caught by a direct question
  prompting a proper isolation test.
- **Actual root cause (verified)**: `ollama generate --raw` (bypasses the chat template
  entirely, sends plain text) produces **perfectly coherent output** — "The capital of France
  is" → "Paris. 2. The largest city in the world by population is Tokyo..." — proving the
  underlying weights, quantization, and `granite`-mapped forward pass are all fine. The garbage
  appears *only* when the model's own embedded chat template is applied. Isolated further:
  feeding the exact literal special-token markup the template emits
  (`<|start_of_role|>user<|end_of_role|>The capital of France is<|end_of_text|>\n<|start_of_role|>assistant<|end_of_role|>`)
  through `--raw` reproduces the identical garbage — so the bug is specifically in how
  Granite-4's `<|start_of_role|>`/`<|end_of_role|>`/`<|end_of_text|>` special tokens are
  registered/embedded in these GGUF conversions, not in the base model weights or in llama.cpp's
  architecture support for `granite`/`granitemoehybrid`. Reproduced identically across two
  independently-uploaded quants (`hf.co/HolkViking/antares-1b-Q4_K_M-GGUF`,
  `hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF`), which points at either a shared upstream
  conversion-tool bug for this token family, or a subtly broken special-token embedding row in
  the base model that every converter faithfully reproduces.
- **Why still blocked**: `TASK_ANTARES_ROLE_PROBE_V1.md`'s Phase 0.4 tool-call smoke test goes
  through `/api/chat` (the template path), so it fails the same way regardless of the corrected
  diagnosis — Experiments A and B both need coherent chat-formatted tool-calling to run.
  Hand-authoring a working custom Ollama `TEMPLATE` (bypassing the broken embedded one) would
  fix this, but is real reverse-engineering work — deferred as a follow-on, the same call made
  for Fara1.5-27B's XML tool-call dialect in this same batch-bench task, not attempted here.
- **Unblocking**: either a GGUF conversion with correctly-registered special tokens, or a
  hand-authored Ollama `TEMPLATE` override proven against the `--raw` isolation test above
  (garbage → coherent) before trusting any chat-mode result.

## Why

Two wrong conclusions in a row on the same finding is exactly the failure mode this note exists to prevent recurring: the first (assumed gate) skipped verification entirely, the second (assumed arch) stopped at the first plausible-looking `ollama show` signal instead of isolating chat-template vs. raw-completion behavior. The `--raw` isolation test that finally pinned this down is cheap and repeatable — recording it here means a future session (or the deferred custom-TEMPLATE follow-on) starts from a verified root cause instead of either stale wrong answer.

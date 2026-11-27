---
id: unit-known-limitations-omlx-qwen38-oq4e-mtp-runaway-reasoning
kind: what
title: oMLX Qwen3.8-27B-oQ4e-mtp side-car runaway reasoning on auto-coding prompt
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: tests/unit/test_omlx_backend.py
claims:
- probe: repo.symbol.exists
  path: tests/unit/test_omlx_backend.py
  symbol: test_auto_coding_base_seat_routes_to_ollama_gguf_not_omlx_alias
  equals: true
confidence: high
tags:
- known-limitations
- omlx
- routing
- qwen3.8

---

#### oMLX `Qwen3.8-27B-oQ4e-mtp` side-car — runaway reasoning on the `auto-coding` prompt (2026-11-27)

- **ID**: P5-OMLX-QWEN38-MTP-001
- **Status**: MITIGATED for `auto-coding` (2026-11-27); OPEN for the unaudited aliased workspaces below.
- **Description**: `auto-coding` was seated on `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` (Ollama GGUF, `realuse_s5s7s10_20261030b`, 15/16, `think: true`), but `config/backends.yaml` aliased that tag in `omlx-general` and `omlx-reasoning` (priority 10) to the oMLX MTPLX side-car `Qwen3.8-27B-oQ4e-mtp`, which had never been evaluated for `auto-coding`. On the live `auto-coding` prompt (`owui_system_prompt`, user turn `"Give your best complete answer for your specialisation (auto-coding)."`, seat sampling `1.0/0.95/20/0/presence 0`, `max_tokens 12000`, no tools):
  - **Ollama GGUF (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k`)**: `finish=stop`, 4,699 tokens, 29 reasoning lines, 17.6k-char answer.
  - **oMLX `Qwen3.8-27B-oQ4e-mtp`**: `finish=length` on 7/7 runs (including 6 in a `presence_penalty` 0.0 vs 1.5 A/B — presence penalty does not help), `content=""`, degraded reasoning (`"We need respond to user…"`), writes the entire program inside reasoning, and never closes thinking.
  - **QAT `s4-auto-coding-core` through OWUI**: 8,346 tokens then 31,312 tokens of runaway generation (hitting the 900 s Pipeline cap) on `Qwen3.8-27B-oQ4e-mtp`.
- **Mitigation**: `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` is registered in `ollama-coding` with no alias in `omlx-coding`, so `auto-coding` (`workspace_routing: [coding, general]`) resolves to its evaluated Ollama GGUF in the `coding` group before `omlx-general` is consulted. Guarded by `test_auto_coding_base_seat_routes_to_ollama_gguf_not_omlx_alias` in `tests/unit/test_omlx_backend.py`.
- **Other workspaces aliased to `Qwen3.8-27B-oQ4e-mtp` (unaudited for this failure mode)**:
  - `auto-daily::deep` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` via `omlx-general`, `think: false`)
  - `auto-coding::qwen38coder` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` via `omlx-coding`, `think: false`)
  - `auto-reasoning::deep` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` via `omlx-reasoning`, `think: true` — highest risk because thinking is enabled)
  - `compliance-council-qwen38` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` via `omlx-general`, `think: false`)
  - `bench-qwen38-cad` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` via `omlx-general`, `think: false`)
  - Note: `auto-compliance` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` via `omlx-reasoning`, `think: false`) was proven live on `Qwen3.8-27B-oQ4e-mtp` and is intentionally kept on oMLX.

## Why

A shadow-shift alias in `omlx-general` silently routed `auto-coding` to an unevaluated oMLX side-car conversion that fails to close its thinking block under the seat's prompt and sampling. Scoping the fix to `ollama-coding` restores the evaluated GGUF arm for `auto-coding` without disturbing `auto-daily::deep`, `auto-compliance`, or the `auto-coding::*` variants, and naming the remaining aliased seats makes their unaudited exposure explicit.

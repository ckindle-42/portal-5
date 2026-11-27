---
id: unit-known-limitations-omlx-qwen38-oq4e-mtp-runaway-reasoning
kind: what
title: oMLX Qwen3.8-27B-oQ4e-mtp runaway reasoning — chat template reasoning_effort default (RESOLVED)
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: tests/unit/test_omlx_backend.py
- type: doc
  path: docs/findings/QWEN38_MTP_RUNAWAY_ROOT_20261127.md
claims:
- probe: repo.symbol.exists
  path: tests/unit/test_omlx_backend.py
  symbol: test_auto_coding_base_seat_restored_to_omlx_mtp_with_gguf_fallback
  equals: true
- probe: repo.symbol.exists
  path: tests/unit/test_omlx_backend.py
  symbol: test_parity_default_and_precedence
  equals: true
confidence: high
tags:
- known-limitations
- omlx
- routing
- qwen3.8

---

#### oMLX `Qwen3.8-27B-oQ4e-mtp` side-car — runaway reasoning was the chat template's `reasoning_effort` default (RESOLVED 2026-11-27)

- **ID**: P5-OMLX-QWEN38-MTP-001
- **Status**: RESOLVED (2026-11-27). The weights and Lightning MTP were never at fault; the Ollama GGUF stays registered as the seat's fallback.
- **Root cause**: the checkpoint's `chat_template.jinja` line 47 defaults `reasoning_effort` to `xhigh` when a request omits it, injecting a 38-token "Reasoning effort is set to xhigh…" preamble whenever thinking is on. Ollama 0.40.18's `renderer=qwen3.8` emits no effort preamble when a request omits one. Same request to both engines: 169 vs 131 prompt tokens. Live A/B on 2026-11-27 15:37Z (quiet host, seat sampling 1.0/0.95/20, max_tokens 12000, MTP on): template default `xhigh` → `finish=stop` 0/3, 12,000 median tokens, 31 tok/s; `chat_template_kwargs reasoning_effort=medium` → 3/3, 8,144 median tokens, 38 tok/s; raw `/v1/completions` with the byte-exact Ollama prompt → 3/3, 6,774 median tokens, 38 tok/s. Full analysis: `docs/findings/QWEN38_MTP_RUNAWAY_ROOT_20261127.md`.
- **Template audit (2026-11-27, `/Volumes/data01/omlx-models/*/chat_template.jinja`)**: only the Qwen3.8-27B* checkpoints carry the `xhigh` default — `Qwen3.8-27B-oQ4e-mtp`, `Qwen3.8-27B-4bit`, `Qwen3.8-27B-opencode-adapted`, `Qwen3.8-27B-pi-adapted`. Qwen3.5-9B-oQ4e-mtp, the gemma-4 and Nemotron conversions, Laguna, Tongyi, VulnLLM-R and the Inkling checkpoints do not (Inkling's `reasoning_effort` is a float knob, not a string tier — a blanket default in the request builder would break those seats, which is why the parity tier is per-model config).
- **Fix**: per-model `reasoning_effort_default: medium` in `config/backends.yaml` on every declared entry of an affected checkpoint (`Qwen3.8-27B-oQ4e-mtp` in `omlx-coding`, `omlx-general` and `omlx-reasoning`, the `:opencode`/`:pi` LoRA profiles, and `Qwen3.8-27B-4bit`). `portal/platform/inference/router/validation.py` `_inject_omlx_options` applies it at the lowest precedence: a caller top-level `reasoning_effort`, a caller-supplied `chat_template_kwargs` effort, an explicit caller `"none"`, and a seat-declared workspace `reasoning_effort` all win; models without the template default get nothing. No model names in Python.
- **Routing**: `auto-coding` serves the oMLX MTP seat again — `omlx-coding` (priority 10) shadows `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` to `Qwen3.8-27B-oQ4e-mtp`; the evaluated Ollama GGUF tag stays registered in `ollama-coding` as the seat's automatic fallback (same 96k window). `general-deep`, `auto-compliance`, and the `auto-coding::*` variants keep their serving unchanged.
- **Guarded by**: `test_auto_coding_base_seat_restored_to_omlx_mtp_with_gguf_fallback` and `test_parity_default_and_precedence` in `tests/unit/test_omlx_backend.py`.

## Why

The 2026-11-27 mitigation routed `auto-coding` to its Ollama GGUF arm because the oMLX side-car "failed to close its thinking block" — but the failure was a prompt divergence, not a model defect: the oMLX checkpoint's chat template silently upgrades unset `reasoning_effort` to `xhigh`, and under `xhigh` the model plans expansively inside `<think>` until the token budget dies. Rendering the same prompt the evaluated Ollama arm renders (the `medium` tier) restores `finish=stop` 3/3 at MTP speed (~38 tok/s vs ~12 on the GGUF), so the workaround is reverted and the limitation closes. The parity tier lives in `config/backends.yaml` — the file an operator edits to scale — because which checkpoints need it is a property of their shipped chat templates, discovered by the audit above; any newly imported checkpoint with the same default needs the same one-line declaration.

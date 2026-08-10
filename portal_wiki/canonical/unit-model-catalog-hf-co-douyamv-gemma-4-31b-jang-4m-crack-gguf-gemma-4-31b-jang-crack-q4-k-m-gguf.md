---
id: unit-model-catalog-hf-co-douyamv-gemma-4-31b-jang-4m-crack-gguf-gemma-4-31b-jang-crack-q4-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6398652
updated_at: 1784946220.6398652
---

`hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` is the douyamv community quant (33K downloads) of dealignai's Gemma-4-31B-JANG_4M-CRACK abliterated+uncensored fine-tune (~20GB Q4_K_M, Gemma license, 4M context, vision+text). `config/backends.yaml` registers it in the `general` group with `supports_tools: false`, but in the `security` and `vision` groups with `supports_tools: true` — the tool-calling value applies where it is routed for agentic security work. `config/portal.yaml` selects it as the `model_hint` for `bench-gemma4-31b-crack`, whose description records the audit-tools 2026-06-16 `finish_reason=tool_calls` confirmation, the pentest bench 0.933 vs supergemma4 0.867 win, and its promotion to auto-pentest primary.

## Why

The doc body said `supports_tools` was confirmed true by audit-tools; re-grounding shows `config/backends.yaml` actually splits the flag — `false` in `general`, `true` in `security` and `vision` — and corrects the blanket claim to the per-group reality. The pentest bench figures, audit confirmation, and promotion status are preserved because `config/portal.yaml`'s bench workspace description records them; the doc's 33K-download figure is kept as catalog metadata.

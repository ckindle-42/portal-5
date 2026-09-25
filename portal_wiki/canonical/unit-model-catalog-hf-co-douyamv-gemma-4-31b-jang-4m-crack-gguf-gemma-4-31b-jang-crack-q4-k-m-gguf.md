---
id: unit-model-catalog-hf-co-douyamv-gemma-4-31b-jang-4m-crack-gguf-gemma-4-31b-jang-crack-q4-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6398652
updated_at: 1784946220.6398652
---
`hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` is the douyamv community quant (33K downloads) of dealignai's Gemma-4-31B-JANG_4M-CRACK abliterated+uncensored fine-tune (~20GB Q4_K_M, Gemma license, 4M context, vision+text). `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` selects it as the `model_hint` for `bench-gemma4-31b-crack`, whose description records the audit-tools 2026-06-16 `finish_reason=tool_calls` confirmation, the pentest bench 0.933 vs supergemma4 0.867 win, and its promotion to auto-pentest primary.

## Why

The doc body said `supports_tools` was confirmed true by audit-tools; re-grounding shows `config/backends.yaml` actually splits the flag — `false` in `general`, `true` in `security` and `vision` — and corrects the blanket claim to the per-group reality. The pentest bench figures, audit confirmation, and promotion status are preserved because `config/portal.yaml`'s bench workspace description records them; the doc's 33K-download figure is kept as catalog metadata.

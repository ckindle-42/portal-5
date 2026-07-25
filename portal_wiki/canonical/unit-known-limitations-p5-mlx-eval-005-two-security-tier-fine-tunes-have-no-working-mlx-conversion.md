---
id: unit-known-limitations-p5-mlx-eval-005-two-security-tier-fine-tunes-have-no-working-mlx-conversion
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-005 \u2014 Two security-tier fine-tunes\
  \ have no working MLX conversion"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-MLX-EVAL-005 \u2014 Two security-tier fine-tunes have no working MLX\
    \ conversion"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6709208
updated_at: 1784946220.6709208
---

- **Description**: `supergemma4-26b-uncensored` (auto-security's
  `purpleteam-exec`/`redteam-deep` variants) and `huihui_ai/gemma-4-abliterated:E2b-qat`
  (auto-security's `pentest` variant) were searched across multiple HF uploaders (mlx-community,
  Jiunsong, aa221241, EZCon). Every MLX conversion found for these specific
  fine-tunes is a multimodal/vision-language checkpoint (`language_model.*`
  prefixed weights) that crashes on plain text-only `mlx_lm` load with
  `ValueError: Received N parameters not in model`.
- **Impact**: These two stay GGUF-only for the foreseeable future.
- **Do not** spend further time searching for a working MLX conversion for
  either unless a new text-only-compatible upload appears.

---

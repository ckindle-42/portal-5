---
id: unit-known-limitations-speculative-decoding-mtp-retired-with-the-mlx-proxy-commit-3a0c58e
kind: what
title: "KNOWN_LIMITATIONS \u2014 Speculative Decoding / MTP \u2014 RETIRED with the\
  \ MLX proxy (commit 3a0c58e)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Speculative Decoding / MTP \u2014 RETIRED with the MLX proxy (commit 3a0c58e)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.673012
updated_at: 1784946220.673012
---

- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired; chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. The bench-only MTP GGUF candidates remain in the catalog as bench entries; there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as `chat_url` — `/api/chat` would allow full `options` passthrough but requires changing payload/response shapes.

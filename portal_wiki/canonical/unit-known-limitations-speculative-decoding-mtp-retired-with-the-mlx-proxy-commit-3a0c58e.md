---
id: unit-known-limitations-speculative-decoding-mtp-retired-with-the-mlx-proxy-commit-3a0c58e
kind: what
title: "KNOWN_LIMITATIONS \u2014 Speculative Decoding / MTP \u2014 RETIRED with the\
  \ MLX proxy (commit 3a0c58e)"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: launch.sh
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/README.md
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.673012
updated_at: 1784946220.673012
---

- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired (commit `3a0c58e`); chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists — `coding_task/TASK_DOC_STEADY_STATE_V1.md` records the collapse of the three live MLX-proxy limitation sections into this single retirement note.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. Bench-only MTP GGUF candidates remain as bench entries in `config/portal.yaml` (e.g. `bench-qwen36-27b-mtp`, created via `./launch.sh apply-mtp-drafts`); there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as the chat URL — it would allow full `options` passthrough but requires changing payload/response shapes.

## Why

When the proxy died, three sections describing its speculative-decoding limitations became instructions for infrastructure that no longer exists, which is worse than a stale doc — it actively misleads anyone reading them as current constraints. Collapsing them into one retirement note preserves the decision record (the draft-model wiring and why it was removed) while making the current truth unambiguous: MTP work, if any, belongs on Ollama's native speculative path.

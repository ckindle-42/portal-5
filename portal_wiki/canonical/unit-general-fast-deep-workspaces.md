---
id: unit-general-fast-deep-workspaces
kind: mixed
title: "General Fast / Deep workspaces — matched-context pair on oMLX"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
claims: []
confidence: high
tags:
- authored-v1
- general
- workspaces
- omlx
created_at: 1791244800.0
updated_at: 1791244800.0
---

`general-fast` (Qwen3.6-35B-A3B MoE) and `general-deep` (Qwen3.8-27B dense, MTP)
are two non-routed general-purpose workspaces picked from the OWUI model picker.
A chat started on Fast is switched to Deep in the picker when the answer is not
good enough; the stateless pipeline lets Deep re-read the whole history.

## Rules

- **Matched context.** Both carry the same `context_limit`; Deep must be >= Fast.
  Change both in one commit. On oMLX the value is a declared budget only: oMLX
  serves the model's native window and the pipeline neither truncates nor
  rejects above it (a 66k-token prompt was served on a 98,304 workspace).
- **Binding.** The `-ctx96k` hints are aliased to the oMLX directories in the
  `omlx-general` group; the same tags exist in Ollama (num_ctx 98304 baked) as
  the honest fallback. A fallback loads a second 21 GB model and can starve
  oMLX (HTTP 507) — unload it before measuring.
- **Thinking off** on both; sampling is the vendor/Unsloth instruct profile.
- **Spreadsheets.** `read_excel` costs ~6 tokens per cell and returns at most 500
  rows; the prompt tells the model to stop reading whole sheets above ~2,500
  cells.

## Spreadsheet path

`execute_python` runs in the lab image (`portal5-attack`, now with pandas and
openpyxl; the non-lab default is `portal5-sandbox-data`). The shared workspace
is mounted read-only at `/workspace` (DinD-side bind `/workspace-src`) and
anything written to `/out` is published through the OWUI files API. The
documents read tools accept a bare filename (OUTPUT_DIR, then `uploads/`).

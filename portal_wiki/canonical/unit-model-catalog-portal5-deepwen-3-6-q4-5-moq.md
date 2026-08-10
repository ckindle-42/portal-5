---
id: unit-model-catalog-portal5-deepwen-3-6-q4-5-moq
kind: what
title: "MODEL_CATALOG \u2014 `portal5/deepwen-3.6:q4.5-moq`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: eecaf33560f0be8d5fa9c2cf20bf1fbdbf93443a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786390650.0
updated_at: 1786390650.0
---

`portal5/deepwen-3.6:q4.5-moq` is the TASK-BATCH-BENCH-002 Part D intake of Deepwen-3.6 (quimmedes/Deepwen-3.6, a Qwen3.6-35B-A3B fine-tune for procedural geometry / hard-surface / 3D-asset workflows, arch `qwen35moe`) — a CAD-lane candidate benched head-to-head against the `auto-cad` module's incumbent, Qwen3-Coder-30B-A3B. `ollama pull hf.co/quimmedes/Deepwen-3.6:Q4.5-MoQ` and `:BF16` both 400'd — Ollama's `hf.co` puller validates the tag against its own quant-scheme enum and rejects the uploader's custom "MoQ" (Mixture-of-Quantizations) naming; the no-tag pull hangs indefinitely (can't auto-pick among multiple MoQ variants in the repo). Not gated. Worked around via direct `huggingface_hub.hf_hub_download` of `Deepwen-3.6-Q4.5-MoQ.gguf` (21.2GB, matches the card) followed by `ollama create` from the local file — GGUF metadata parsed cleanly (arch `qwen35moe`, 34.7B params, template, tool-call format) with no hand-written Modelfile needed, unlike the gated-repo `baronllm`/`xyz-aquila-mini` precedent. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` probe against a `render_openscad`-style tool call. `config/portal.yaml` gives it the `bench-deepwen-cad` workspace, cloning `auto-cad`'s tool loop (`render_openscad`/`convert_cad`, `tool_choice: required`, the CAD OUTPUT RULE system prompt). BENCH RESULT 2026-08-10: TPS 40.4 t/s (clears floor) but Q-score 0.00 — 2/5 generic-prompt runs empty, one with garbled mid-stream Unicode injection. Confirmed on the real CAD tool loop: the OpenSCAD enclosure task degenerated into unrecoverable token garbling with no `render_openscad` call; the trimesh task emitted a raw unparsed `<tool_call>` XML block as plain content instead of calling `execute_python` — a template/format mismatch, not a tool-selection failure. The same OpenSCAD prompt against the `auto-cad` incumbent (Qwen3-Coder-30B-A3B) succeeded cleanly with a verified STL+PNG render. **Declined** — the Q4.5-MoQ conversion is unstable at generation time; the model never got far enough into either the OpenSCAD or trimesh sub-path to test the original domain-mismatch hypothesis. A different quant rung (Q6/Q8-MoQ) may be worth a follow-on probe before writing off the base model.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-deepwen-cad` workspace binding. The MoQ-tag workaround detail is kept because it is the same class of problem as Ling-3.0-flash's TurboQuant gate in this same task (a custom quant-methodology upload that stock Ollama's puller can't resolve by tag) — a future session hitting a `400: not a valid quantization scheme` on another MoQ-tagged repo should find this unit rather than re-diagnosing the puller behavior from scratch. The generation-instability finding is kept in detail because it changes the actionable next step from "the model is domain-mismatched for OpenSCAD" (the original hypothesis) to "this specific Q4.5-MoQ quant rung is broken" — a future session should try a different MoQ rung before concluding the base model is unsuitable.

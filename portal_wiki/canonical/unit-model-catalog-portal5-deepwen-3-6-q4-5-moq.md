---
id: unit-model-catalog-portal5-deepwen-3-6-q4-5-moq
kind: what
title: "MODEL_CATALOG \u2014 `portal5/deepwen-3.6:q4.5-moq`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786390650.0
updated_at: 1786396200.0
---

`portal5/deepwen-3.6:q4.5-moq` is the TASK-BATCH-BENCH-002 Part D intake of Deepwen-3.6 (quimmedes/Deepwen-3.6, a Qwen3.6-35B-A3B fine-tune for procedural geometry / hard-surface / 3D-asset workflows, arch `qwen35moe`) — a CAD-lane candidate benched head-to-head against the `auto-cad` module's incumbent, Qwen3-Coder-30B-A3B. `ollama pull hf.co/quimmedes/Deepwen-3.6:Q4.5-MoQ` and `:BF16` both 400'd — Ollama's `hf.co` puller validates the tag against its own quant-scheme enum and rejects the uploader's custom "MoQ" (Mixture-of-Quantizations) naming; the no-tag pull hangs indefinitely (can't auto-pick among multiple MoQ variants in the repo). Not gated. Worked around via direct `huggingface_hub.hf_hub_download` of `Deepwen-3.6-Q4.5-MoQ.gguf` (21.2GB, matches the card) followed by `ollama create` from the local file — GGUF metadata parsed cleanly (arch `qwen35moe`, 34.7B params, template, tool-call format) with no hand-written Modelfile needed. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` probe. `config/portal.yaml` gives `bench-deepwen-cad` a `model_hint` of the **derived** tag `portal5/deepwen-3.6:q4.5-moq-ctx32k` (see below), cloning `auto-cad`'s tool loop.

**Bench history — an initial wrong verdict, root-caused and corrected.** First pass: TPS 40.4 t/s (clears floor) but Q-score 0.00, garbled tokens, malformed tool-call XML — initially written up as a broken Q4.5-MoQ quant conversion. That was wrong. Root cause: this is `P5-OLLAMA-OPTIONS-001` (already documented in `KNOWN_LIMITATIONS.md` — should have been checked before this workspace was created, per CLAUDE.md's own "check KNOWN_LIMITATIONS.md before adding tasks" rule) — Ollama's OpenAI-compatible `/v1/chat/completions` endpoint (what the pipeline uses) silently ignores the entire `options` sub-object, so the workspace's `context_limit: 8192` had **zero effect**. Confirmed both by a pipeline DEBUG-log warning matching the known limitation's own text and by direct isolation testing (`num_ctx=8192` via `/api/chat` reliably breaks tool-call JSON on this model/arch; `num_ctx=32768` reliably fixes it). `auto-cad` itself already works around this exact limitation — its `model_hint` (`qwen3-coder:30b-a3b-q4_K_M-ctx8k`) is a pre-baked ctx tag, the documented mitigation pattern this workspace's initial config (cloned from `auto-cad` but not fully following its pattern) missed. Fixed via the documented `./launch.sh apply-model-params` command (requires `PORTAL_ENABLE_EVAL=1` — `get_workspace_dict` excludes eval-module workspaces otherwise, which is why the first `apply-params` run silently processed zero workspaces), producing `portal5/deepwen-3.6:q4.5-moq-ctx32k` and rewriting `model_hint` automatically.

**Post-fix re-test.** Raw completion and simple chat are fully coherent (same raw-vs-templated isolation method as the Antares finding in V1 — see `unit-model-catalog-portal5-xyz-aquila-mini-q4-k-m`'s sibling report for that precedent). Under the real production request shape (full 13-tool schema, `tool_choice: required`, the CAD OUTPUT RULE system prompt), the model produces long, technically correct, coherent reasoning — verified correct gyroid-surface implicit-function math on the trimesh task, correct dimensional breakdown on the OpenSCAD task — but never converges to an actual tool call on either sub-task (`finish_reason: stop` after 3346-5858 completion tokens, not a length cutoff). The same OpenSCAD prompt against `auto-cad`'s incumbent succeeds cleanly with a verified STL+PNG render. **Verdict: declined for this lane** — not a broken quant, but a genuine tool-call-convergence failure under `tool_choice: required` plus the full production tool schema; the model's underlying reasoning and domain knowledge are sound. The original OpenSCAD-vs-trimesh domain-mismatch hypothesis remains untested, since the model never reaches either sub-path's completion.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-deepwen-cad` workspace binding. The MoQ-tag pull workaround is kept because it is the same class of problem as Ling-3.0-flash's TurboQuant gate in this same task. The corrected-verdict history is kept in full, including the wrong first conclusion, because the actual defect (`context_limit` being silently no-op'd through Ollama's `/v1` endpoint) is a real process gap that could recur on any new eval workspace that sets `context_limit` without running `apply-model-params` — a future session hitting a similarly garbled/empty result on a fresh bench workspace should check this before concluding the model itself is broken.

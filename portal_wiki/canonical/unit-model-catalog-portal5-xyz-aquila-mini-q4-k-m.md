---
id: unit-model-catalog-portal5-xyz-aquila-mini-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `portal5/xyz-aquila-mini:q4_k_m`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786306800.0
updated_at: 1786306800.0
---

`portal5/xyz-aquila-mini:q4_k_m` is the TASK-BATCH-BENCH-001 Part A intake of XYZ-Aquila-mini (XYZAILab, 35B-A3B MoE ~3B active, post-trained from Qwen3.6-35B-A3B via the AxisAgentic bounded-exploration pipeline) — a purpose-built deep-search/web-research agent candidate. The Ollama `hf.co` puller repeatedly failed with a server-side "context deadline exceeded" pulling the 21GB Q4_K_M blob specifically (smaller quants of the same repo pulled fine; both blobs verified cached and hash-valid; HF CDN/Xet resolution confirmed fast via direct probing) — root-caused as a puller limitation on this build/blob-size combination, not a network or repo problem. Imported instead via the repo's documented gated-repo workaround: `huggingface_hub.hf_hub_download` followed by `ollama create` from a local Modelfile (the same pattern as `baronllm:q6_k`), same Q4_K_M quant, no quality substitution. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` tool-call probe (clean, well-formed `tool_calls`, correctly typed arguments) rather than inferred from the model card. `config/portal.yaml` gives it the `bench-aquila-mini-35b-a3b` workspace `model_hint`. TPS bench: 49.9 t/s average (5/5 runs), clearing the 20 t/s floor. Capability bench (C1/C4 vs `auto-research` baseline): C1 tied (both cap=0.00); C4 shows a real delta (Aquila fmt=1.00/cap=0.89 vs baseline fmt=0.67/cap=0.22). An MLX build exists (`mlx-community/XYZ-Aquila-mini-OptiQ-4bit`) but is not pre-staged on the running oMLX server, which serves only a fixed pre-registered model pool (no on-demand HF loading like Ollama) — bench_omlx_v3 returned a clean 404; recorded `mlx-blocked (server: model not staged)` per the no-build-here constraint, GGUF-only result stands. The V10 candidate-probe harness (`bench_candidates_v10.py`) has a fixed `PROBE_PLAN` for an earlier, different candidate set with no generic per-workspace entry point, so it does not apply to this candidate; the C4 capability delta is the closest in-fleet tool-chain-adjacent signal captured. PROMOTE_POLICY=confirm — this is an evaluation intake, not a production routing change.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-aquila-mini-35b-a3b` workspace binding and the full intake narrative (pull failure root cause, workaround method, bench results, MLX-blocked reason). The institutional detail is kept because it explains why this model's registration entry deviates from the standard `ollama pull hf.co/...` path used by nearly every other fleet model, and because the honest `mlx-blocked`/v10-inapplicable findings prevent a future session from re-attempting either path without first re-checking whether the underlying constraint (server pre-staging, harness scope) has changed.

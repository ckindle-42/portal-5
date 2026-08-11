---
id: unit-model-catalog-muse-glimmer-30b-mlx
kind: what
title: "MODEL_CATALOG \u2014 `muse-glimmer:30b-mlx`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786390650.0
updated_at: 1786390650.0
---

`muse-glimmer:30b-mlx` is the TASK-BATCH-BENCH-002 Part A intake of Muse-Glimmer-30B (meta-models/Muse-Glimmer-30B, 29.6B dense + ViT-G/14 perception encoder, Apache 2.0) — a local-first multimodal agentic model that ships DFlash speculative decoding, run through the native Ollama MLX engine (0.32.7 supports the `muse_glimmer` architecture directly, sidestepping the fixed-pool oMLX server that returned `mlx-blocked` for the V1 Aquila-mini candidate since it needs no separate mmproj wrangling). Pulled clean with no arch errors (GATE-0b). `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` tool-call probe rather than inferred from the card. `config/portal.yaml` gives it the `bench-muse-glimmer-30b` workspace `model_hint`. Loading it initially hit a real infra ceiling: the box's `OLLAMA_GPU_OVERHEAD` was permanently fixed at 40GiB (`/Library/LaunchDaemons/com.portal5.ollama.plist`), capping any single Ollama model at ~15.5GiB regardless of oMLX's actual loaded state — root-caused as a static Metal-working-set carve-out, not a stale-memory reading (freeing oMLX's loaded models and even a full daemon restart left the number unchanged). Corrected by lowering the overhead to 20GiB (real oMLX coexistence headroom, sized off oMLX's own observed footprint, without starving Ollama) — a permanent plist fix, not a one-off workaround. TPS bench: 25.6 t/s average (5/5 runs), clearing the 20 t/s floor. Native vision confirmed via an unlabeled bar-chart fixture (accurate grounded description of relative heights/trend). Capability bench (C1/C4 vs `auto-coding` baseline): C1 tied (both cap=0.00, a probe-difficulty artifact not a differentiator); C4 shows a real gap the other direction from most V1 candidates — Muse-Glimmer 0.33/0.0/0.33 per-probe vs baseline's clean 1.0/1.0/1.0 (correct plan/fence format, materially weaker content). DFlash spec-decode: a controlled 8-run-per-arm same-prompt A/B (`draft_num_predict` 15 vs 0) measured only a 1.9% decode-TPS delta (20.38 vs 19.99 t/s, both within stdev) — far below the card's claimed 1.5–1.8x, though output was bit-identical across all runs and both arms so correctness holds. Verdict: TPS/tools/vision all pass, but no coding/agentic edge over the incumbent and no real DFlash speedup on this serving path — not a primary-lane promotion candidate on current evidence. PROMOTE_POLICY=confirm.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-muse-glimmer-30b` workspace binding and the full bench narrative. The institutional detail on the `OLLAMA_GPU_OVERHEAD` fix is kept because it is a permanent, box-level infra change (not scoped to this one bench) that directly determines whether any future 20GB+-class single-model bench on this host can load at all — a future session hitting the same "model requires N GiB but only 15.5 GiB available (after 40.5 GiB overhead)" error should find this unit rather than re-diagnosing it as a live-memory or stale-cache problem.

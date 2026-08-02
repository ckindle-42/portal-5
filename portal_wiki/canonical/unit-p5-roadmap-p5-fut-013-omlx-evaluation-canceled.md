---
id: unit-p5-roadmap-p5-fut-013-omlx-evaluation-canceled
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-013: OMLX Evaluation \u2014 CANCELED"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: "P5-FUT-013: OMLX Evaluation \u2014 CANCELED"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.592072
updated_at: 1784946220.592072
---

Full bake-off completed 2026-04-25. Decision: **RETIRE**. See `OMLX_DECISION.md` for full results. KV cache persistence not functional (warm TTFT 31% *slower* than cold). mlx-proxy retains the production inference role.

**Update 2026-05-28 (TASK_OMLX_REEVAL_V2):** oMLX v0.3.12 full re-evaluation completed. KV cache STILL broken (warm 2× slower than cold on 3B and 30B). MTP speedup clears 1.5× gate (1.55×-1.65×). 30B model now loads (memory fix works). 70B borderline (HTTP 507 on cold load). Decision: PROBE_AGAIN_NARROWLY. Status: REMAINS RETIRED. See OMLX_DECISION.md "Re-evaluation 2026-05-28" section and `tests/benchmarks/results/omlx_reeval_20260528T145902Z.md` for detail. Next re-evaluation trigger: MTP stability probe (TASK_OMLX_MTP_STABILITY_V1).

**Update 2026-08-02 (P5-FUT-013 Phase-0 v3):** oMLX v0.5.4 six-gate re-evaluation — ALL GATES PASS. KV cancel trigger cleared on agentic-length prefixes (3.5–7.0× warm TTFT, `cached_tokens` verified; legacy short-prefix cell flat because the paged cache uses 256-token blocks — part of the original RETIRE verdict was methodology). Decode 1.32–1.46× over production GGUF, 2.2–2.5× with verified Lightning MTP. Tool calling: Qwen/Gemma ✅, Llama-family ❌. Grammar ✅ with one reproducible gemma livelock edge. Batching 1.6–3.1×, zero failures. Decision: **PROCEED to Phase 1 (dual-backend; Ollama retained as fallback tier)**. P5-FUT-013 superseded. See OMLX_DECISION.md "Re-evaluation v3 2026-08-02" and `tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`.

---

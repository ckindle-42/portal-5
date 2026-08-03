---
id: unit-design-omlx-dual-backend-plumbing
kind: mixed
title: "DESIGN — oMLX dual-backend plumbing (P5-FUT-013 Phase 1, B1)"
sources:
- type: code
  path: portal/platform/inference/router/backend_introspect.py
- type: code
  path: portal/platform/inference/cluster_backends.py
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: config/backends.yaml
- type: code
  path: tests/benchmarks/bench_omlx_v3.py
- type: code
  path: tests/unit/test_omlx_backend.py
- type: doc
  path: OMLX_DECISION.md
  section: "Re-evaluation v3 2026-08-02 (P5-FUT-013 Phase-0)"
- type: doc
  path: tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md
last_generated_commit: f79250e4
confidence: high
tags:
- design
- inference
- omlx
created_at: 1785719000.0
updated_at: 1785719000.0
---

# oMLX dual-backend plumbing (Phase 1 / B1, landed 2026-08-02)

**Why:** the 2026-08-02 Phase-0 re-evaluation (all six gates PASS — see
`OMLX_DECISION.md` §"Re-evaluation v3" and the reeval results MD) decided
**PROCEED to Phase 1**: oMLX as the Apple-Silicon primary tier, Ollama retained
as the fallback tier. B1 is the serving-foundation slice: everything needed for
a later per-workspace traffic shift, with **zero traffic shift on landing**
(the `omlx-local` backend registers in holding group `omlx`, reachable only
via the tier-3 absolute-fallback net).

**What, per mechanism:**

- `Backend.type = "omlx"` (`cluster_backends.py`) — third-party oMLX server
  over plain OpenAI HTTP, health-probed via `/v1/models`. Explicitly NOT the
  retired in-house MLX proxy (3a0c58e): no custom process/watchdog management
  lives here, and the regression guards (`mlx_metadata`, proxy URL, group
  named `mlx`) all stay intact — the holding group is named `omlx` for that
  reason.
- `health_path:` per-backend YAML override — generalizes `health_url` beyond
  the two type-derived defaults.
- `priority:` per-backend — within-group candidate ordering (descending,
  shuffle only among equals). This is the oMLX-primary/Ollama-fallback
  mechanism for B2: all-zero priorities preserve legacy shuffle semantics.
- `aliases:` + `Backend.resolve_model()` — canonical workspace `model_hint`
  (e.g. a GGUF tag) → engine-native model id (e.g. an oMLX directory name),
  so an engine swap stays a `config/backends.yaml` edit (Rule 1) with no
  workspace changes.
- `_inject_omlx_options` (`validation.py`) — plain-OpenAI injection only
  (`max_tokens`, `stream_options.include_usage`, top-level
  `temperature`/`top_p`): no `options` sub-dict, no `keep_alive` (oMLX uses
  server-side EnginePool pinning/TTL), no `num_ctx` (oMLX per-model
  settings replace the `-ctxNk` derived-tag workaround, P5-OLLAMA-OPTIONS-001).
- `router/backend_introspect.py` — `model_still_running(url)` seam replacing
  hardcoded `/api/ps` at the three timeout-disambiguation sites (streaming
  ×2, non-streaming ×1). Type is resolved from the lifespan registry
  singleton so streaming signatures stay untouched; unknown URLs keep the
  legacy Ollama probe. oMLX semantic is deliberately degraded until B3 wires
  the admin API: reachable ⇒ busy, unreachable ⇒ down.
- Evidence + tests: `tests/benchmarks/bench_omlx_v3.py` is the Phase-0 gate
  harness (protocol shapes preserved from the deleted bench_omlx.py @
  10075f1c); `tests/unit/test_omlx_backend.py` (13 tests) covers health URLs,
  overrides, alias resolution, priority ordering, injection surface, and the
  introspector seam.

**Gates at landing:** 873 unit ✅, ruff ✅, pipeline rebuilt (7/7 backends
healthy incl. `omlx-local`), `smoke_stream.sh` ✅, `ci_local.sh` 2652 ✅,
BR ratchet covered by this unit.

**Next (B2, see PUNCHLIST.md):** per-group oMLX entries with `priority: 10`
and per-model `aliases:` (auto-coding first, incl. a Laguna MLX download);
handler hint-resolution switches from `model_hint in backend.models` to
`backend.resolve_model(hint)`; oMLX warmup path for `keep_alive`-pinned
workspaces (current warmup posts Ollama-native `/api/generate`).

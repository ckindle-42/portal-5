---
id: unit-design-omlx-dual-backend-plumbing
kind: mixed
title: "DESIGN \u2014 oMLX dual-backend plumbing (P5-FUT-013 Phase 1, B1+B2)"
sources:
- type: code
  path: portal/platform/inference/router/backend_introspect.py
- type: code
  path: portal/platform/inference/cluster_backends.py
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
- type: code
  path: scripts/persona_intent_audit.py
- type: code
  path: config/backends.yaml
- type: code
  path: tests/benchmarks/bench_omlx_v3.py
- type: code
  path: tests/unit/test_omlx_backend.py
- type: code
  path: tests/unit/test_seed_facts.py
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- design
- inference
- omlx
- verified-v1
created_at: 1785719000.0
updated_at: 1785723200.0
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

**Gates at landing:** 873 unit ✅, ruff ✅, pipeline rebuilt (all backends
healthy incl. `omlx-local`), `smoke_stream.sh` ✅, `ci_local.sh` 2652 ✅,
BR ratchet covered by this unit.

## B2 — Shadow then shift, auto-coding first (landed 2026-08-02)

**What:** `auto-coding` now shadow-shifts to oMLX. A second `group: coding`
backend entry (`omlx-coding`, `priority: 10`) sits alongside `ollama-coding`
(`priority: 0`) — B1's design meant no `workspace_routing` change was
needed, since `auto-coding`'s `[coding, general]` groups picked up the new
entry automatically. `aliases:` translate both the base hint
(`qwen3-coder:30b-a3b-q4_K_M-ctx16k` → `Qwen3-Coder-30B-A3B-Instruct-4bit`)
and the `laguna` variant hint (`laguna-xs.2:Q4_K_M-ctx64k` →
`Laguna-XS.2-4bit`, downloaded this session from `mlx-community/Laguna-XS.2-4bit`
— it ships `modeling_laguna.py`/`configuration_laguna.py` custom-code, so
oMLX serves the never-upstreamed Laguna architecture via HF
`trust_remote_code`, unlike the retired mlx_lm proxy which needed a
hand-written plugin). `handlers.py`/`non_streaming.py` hint resolution
switched from `model_hint in backend.models` to `backend.resolve_model()`
so aliases actually match. `lifespan.py::_warmup_auto_model` branches on
`backend.type` — oMLX gets a `/v1/chat/completions` warmup instead of
Ollama's `/api/generate`+`keep_alive`.

**Bug found and fixed along the way:** two independent copies of a
`_group_models()` helper (`portal/platform/wiki/adapters/seed_facts.py` and
`scripts/persona_intent_audit.py`) computed "models reachable via group X"
with a plain dict assignment per backend entry — `groups[name] = {...}`.
That silently *replaced* rather than *unioned* when a second backend
declared the same `group:`, exactly the pattern B2 introduces by design.
Landing `omlx-coding` alongside `ollama-coding` briefly corrupted the
generated `unit-fact-model-catalog` (coding group reported a handful of
models instead of the full catalog) and produced 6 false "unreachable" gaps in
`unit-fact-model-bindings` / the `AV. persona intent` validate check. Fixed
both call sites to `groups.setdefault(name, set()).update(...)` — a group
now means "everything reachable through it," which is what every caller
already assumed.

**Live-verified through the full pipeline** (not just oMLX directly):
`POST /v1/chat/completions {"model": "auto-coding", ...}` returned
`"model": "Qwen3-Coder-30B-A3B-Instruct-4bit"` — confirms alias resolution
+ priority routing work end-to-end, not just in unit tests.

**Known finding, not a blocker:** `Qwen3-Coder-30B-A3B-Instruct-4bit` hit
the same "unconstrained→constrained livelock on cold load" bug class
already documented for gemma in Phase-0 (upstream draft filed) — the
first tool-schema-bearing request after a fresh model load produced
garbled output once, self-recovered on every retry immediately after. The
oMLX warmup added this session does not carry tool schemas, so it doesn't
pre-trigger this. See `PUNCHLIST.md` B2 for the full note and follow-up
options.

**Gates:** 2658 unit ✅, ruff ✅, `smoke_stream.sh` ✅, `ci_local.sh` ✅,
pipeline rebuilt + restarted with all backends healthy.

**Next (B3+, see PUNCHLIST.md):** security-core `/api/chat` → `/v1/chat/completions`
migration; ~1 week of Prometheus TTFT/TPS comparison before expanding to
`auto-vision` and `auto-security` migratable variants.

## Why

oMLX is a third-party OpenAI-compatible server, not the in-house MLX proxy
that was retired at `3a0c58e`, so the two must not be conflated in the
docs: the retired proxy's regression guards (group never named `mlx`,
no custom process/watchdog management) are exactly why the holding group
is `omlx` and why B1 shipped with zero traffic shift. Every mechanism
described here is grounded in the code that implements it —
`cluster_backends.py` for the `omlx` type and `priority:`/`aliases:`,
`validation.py` for `_inject_omlx_options`, `backend_introspect.py` for
the `model_still_running(url)` seam, and `config/backends.yaml` for the
`omlx-local`/`omlx-coding` entries — so the Phase-1 and B2 landing records
re-derive from live config rather than from the decision notes that
proposed them.

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
  path: scripts/validation/inference.py
- type: code
  path: tests/benchmarks/bench_omlx_v3.py
- type: code
  path: tests/unit/test_omlx_backend.py
- type: code
  path: tests/unit/test_seed_facts.py
claims: []
confidence: high
tags:
- design
- inference
- omlx
- verified-v1
created_at: 1785719000.0
updated_at: 1793217575.0
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
  retired in-house MLX proxy (75c24a9): no custom process/watchdog management
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
- `_inject_omlx_options` (`validation.py`) — no `options` sub-dict, no
  `keep_alive` (oMLX uses server-side EnginePool pinning/TTL), no `num_ctx`
  (oMLX per-model settings replace the `-ctxNk` derived-tag workaround,
  P5-OLLAMA-OPTIONS-001). Updated by `TASK_SAMPLING_PROFILE_AUDIT_V1`
  (2026-08-15, Finding 6): originally forwarded only `max_tokens`/
  `stream_options.include_usage`/top-level `temperature`/`top_p` — every
  other workspace sampling key was silently dropped for oMLX-served traffic
  even though oMLX's own `ChatCompletionRequest` schema (verified against
  the live installed `omlx` package) genuinely wires `top_k`/`min_p`/
  `presence_penalty`/`seed`. Now forwards the full set, with
  `repeat_penalty` renamed to oMLX's `repetition_penalty` field and `think`
  mapped to `chat_template_kwargs.enable_thinking` (oMLX has no bare
  `think` field) rather than passed through as-is.
- `router/backend_introspect.py` — `model_still_running(url)` seam replacing
  hardcoded `/api/ps` at the three timeout-disambiguation sites (streaming
  ×2, non-streaming ×1). Type is resolved from the lifespan registry
  singleton so streaming signatures stay untouched; unknown URLs keep the
  legacy Ollama probe. oMLX semantic is deliberately degraded until B3 wires
  the admin API: reachable ⇒ busy, unreachable ⇒ down.
- Evidence + tests: `tests/benchmarks/bench_omlx_v3.py` is the Phase-0 gate
  harness (protocol shapes preserved from the deleted bench_omlx.py @
  1198334b); `tests/unit/test_omlx_backend.py` (13 tests) covers health URLs,
  overrides, alias resolution, priority ordering, injection surface, and the
  introspector seam.

**Gates at landing:** 873 unit ✅, ruff ✅, pipeline rebuilt (all backends
healthy incl. `omlx-local`), `smoke_stream.sh` ✅, `ci_local.sh` 2652 ✅,
BR ratchet covered by this unit.

## Host supervision — brew LaunchAgent + liveness watchdog (2026-08-29)

The oMLX **process** is supervised on the host by Homebrew's
`homebrew.mxcl.omlx` LaunchAgent (`brew services`, tap `jundot/omlx`),
peer to the way Ollama runs under its own plist. This is host ops, wholly
outside `portal/platform/inference/` — the pipeline still does zero process
management, so the retired-MLX-proxy regression guard ("no custom
process/watchdog management") is intact.

`brew services` `KeepAlive` only restarts oMLX on a clean **exit**. In
production oMLX has instead **wedged** — process alive, RSS collapsed, no
answer on `:8085` — which launchd never notices and which makes every
`omlx-*` backend group report unhealthy (a dropped `backends_healthy` count
in `./launch.sh status`) until a manual `brew services restart
jundot/omlx/omlx`. Closed by
`scripts/omlx-watchdog.sh` + `deploy/launchd/com.portal5.omlx-watchdog.plist`
(`StartInterval` 120s): probes `GET :8085/v1/models`, restarts the brew
service after two consecutive failures (one failure can be a cold model
load), logs to `~/.portal5/logs/omlx-watchdog.log`. `_ensure_native_services`
installs/bootstraps the watchdog and kicks the brew service on `./launch.sh
up`; `_cmd_status` now shows an `oMLX :8085` row under NATIVE SERVICES.

## Host supervision — settings.json context floor (2026-08-29)

oMLX clamps every request to `~/.omlx/settings.json` `sampling.max_context_window`
regardless of the per-request context the pipeline sends (it has no
`--max-context-window` serve flag). A stale `32768` there silently truncated the
`auto-coding` / laguna / heavy coding lanes well below the window
`config/portal.yaml` grants them (`qwen3-coder:30b-a3b-q4_K_M-ctx256k` = 262144),
producing the mid-tool-loop restart-and-stub failure the adaptive UAT surfaced.
`_ensure_native_services` now raises `sampling.max_context_window` and
`sampling.max_tokens` to a 262144 floor (the fleet's largest declared window) on
`./launch.sh up`, restarting the brew service only when it actually changed the
file — idempotent, same pattern as the watchdog bootstrap above. The memory guard
still protects against genuine OOM; this only stops the silent truncation.

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
pre-trigger this. See `docs/PUNCHLIST.md` B2 for the full note and follow-up
options.

**Gates:** 2658 unit ✅, ruff ✅, `smoke_stream.sh` ✅, `ci_local.sh` ✅,
pipeline rebuilt + restarted with all backends healthy.

**Next (B3+, see PUNCHLIST.md):** security-core `/api/chat` → `/v1/chat/completions`
migration; ~1 week of Prometheus TTFT/TPS comparison before expanding to
`auto-vision` and `auto-security` migratable variants.

## Fleet fallback rule — one oMLX checkpoint + one Ollama GGUF fallback per family

**Rule (operator, 2026-10-28).** Each model family keeps **one oMLX checkpoint
plus one Ollama GGUF fallback**. The `priority: 10` oMLX entry shadows the
Ollama entries in its group; when oMLX is unhealthy or rejects, candidate
selection falls through to the GGUF tag, so a user always gets an answer. Extra
quant variants are bloat unless a planned test needs them. The intake side of
the same rule is explicit: a new dense intake gets an oMLX counterpart, which is
what the `-oQ4e-mtp` MTP side-car checkpoint entries already do in practice.

**Families are the union of the alias graph and the id's own lineage.** An alias
key is the canonical GGUF `model_hint` and its value the oMLX checkpoint that
serves it, so each edge already states the fallback pairing — and, because the
pipeline resolves hints through `aliases`, an edge is also the only path by which
the GGUF tag is actually reached. But the operator's rule counts *models*, so a
family additionally joins every id that normalises to the same lineage key: drop
the org/namespace prefix (and the flattened `org--name` form) and the `.gguf`
extension, lowercase, then strip `-ctxNk`/`ctxNk` windows, quantisation phrases
(`q4_k_m`, `q8_0`, `UD-Q4_K_XL`, `oQ4e`) and format tokens (`mlx`, `gguf`, `qat`,
`mtp`, `dflash`/`draft`, `ud`, `it`/`instruct`, and bit-width/precision markers
such as `4bit` or `mxfp8`), and compare the remaining letter/digit runs as a set.
A family is then a connected component over three node kinds — checkpoint,
weights tag, lineage key — so `gemma-4-26b-a4b-it-QAT-4bit` and
`mlx-community--gemma-4-26b-a4b-it-4bit` are one model, as are
`gemma4:26b-a4b-it-q4_K_M` and `gemma4:26b-a4b-it-qat`. `abliterated`,
`uncensored`, `heretic`, `distill` and `merged` are deliberately *not* stripped:
those are different models, not quants. The tokeniser is `_lineage_key` in
`scripts/validation/inference.py`, with pair-by-pair SAME/DIFF coverage in
`tests/unit/test_validation_fleet_fallback.py`; there is no model name in the
code. Weights identity (`_weights_tag`) is case-insensitive and drops `:latest`
and `-ctxNk`, because those tags share one GGUF file (P5-OLLAMA-OPTIONS-001's
baked-window workaround), so `gemma4:26b-a4b-it-qat-ctx8k` and `-ctx16k` are one
weights tag, not two.

**What the check reports** (`HY. fleet fallback rule` in
`scripts/validation/inference.py`, registered under `scripts/validation/`): an
oMLX seat that no alias reaches — a same-lineage GGUF twin that was never aliased
does not count, because the alias is the fallback path; more than one oMLX
checkpoint in a family; more than one distinct GGUF weights tag in a family. All
three WARN rather than FAIL while consolidation is in progress, so
`validate_system.py` prints the worklist without gating on it. A model entry may
carry the optional `keep_reason:` field (accepted by `cluster_backends.py` and
documented in the `config/backends.yaml` header) to exempt that one entry: a
two-variant family with one marked entry passes, a three-variant family with one
marked entry still reports the other two. DFlash/draft helpers are exempt by rule
— they are speculative-decoding scaffolding, not served families of their own.

**First full run (2026-10-28):** 19 oMLX seats, 92 families, 33 alias edges, and
nine WARN findings — `gemma4:26b-a4b-it-qat` (two checkpoints *and* two GGUF
weights: the operator's canonical example), `qwen3.6:27b-q8_0` (four GGUF weights),
`qwen3.6:35b-a3b-q4_K_M`, `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`,
`llama3.2:3b`, `gemma4:12b-it-qat`, `gemma4:e4b-it-qat`,
`mistral-small3.2:24b`, `omnicoder2:9b-q4_k_m`. That list is the consolidation
worklist; the alias-reach finding on
`Huihui-Qwen3.6-27B-abliterated-MLX-4bit` was closed by aliasing its registered
twin `huihui_ai/Qwen3.6-abliterated:27b`, and the Qwen3.8-27B DFlash2 seat is the
one oMLX-only checkpoint, recorded with a `keep_reason:`. Re-derive the list from
the live config instead of trusting this snapshot.

**MTP intake rule** (`HZ. MTP intake rule`, same module): every Lightning MTP
twin the fleet has run is a 27-30B side-car over the plain oMLX build it
replaces — `Qwen3.8-27B-oQ4e-mtp` (dense: ~1.45x, 60-65% accept),
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` (MoE ~3B active: ~1.33x,
76-87% accept) and the deleted `Qwen3.6-27B-oQ8-mtp`. The rule generalises that
profile: an oMLX seat is *qualifying* when its id parses to 24-32B total params
and is dense or a <=4B-active MoE, and it must either have an `-mtp` twin
checkpoint in its family (same `_families` component), or declare
`mtp: none` + `mtp_reason:` on the entry. The twin replaces the plain build of
its family (replace-in-place); keeping both needs `keep_reason:` on the plain
entry, like the Qwen3.8-27B DFlash2 seat. A new twin must clear the evidence
bar the existing ones set: real `mtp.*` tensors in the checkpoint (plain
`mlx-community` conversions ship none — the no-op is silent), a live speed A/B
of >=1.3x over the non-MTP baseline, a draft accept rate >=60%, and a tool-call
probe before `supports_tools: true`. All findings are WARN, never FAIL; the
twin itself, DFlash/draft helpers and out-of-band sizes are exempt.

## Why

oMLX is a third-party OpenAI-compatible server, not the in-house MLX proxy
that was retired at `75c24a9`, so the two must not be conflated in the
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

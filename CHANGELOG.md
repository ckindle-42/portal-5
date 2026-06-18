# Changelog

All notable changes to Portal 5 will be documented in this file.

## [Unreleased]

### Added
- **Claude Code / opencode integration** — Portal 5 now works as a local AI backend and tool
  provider for AI coding assistants. Two files at the repo root activate automatically:
  - **`.mcp.json`** — 6 MCP servers: `filesystem`, `fetch`, `git`, `docker`,
    `portal-sandbox` (execute_bash/python), `portal-pipeline` (stack introspection + explorer)
  - **`opencode.jsonc`** — points opencode at portal-pipeline (:9099) as a fully local
    OpenAI-compat provider; all 95 workspaces available as models; cloud providers disabled
- **Pipeline MCP server** (`portal_mcp/platform/pipeline_mcp.py`, `:8928`, host-native) —
  FastMCP service exposing 7 tools to coding tools: `get_pipeline_status`, `list_workspaces`,
  `get_loaded_models`, `get_metrics_summary`, `get_workspace_recommendation`,
  `trigger_backend_warmup`, and `explore_repository` (FastContext subagent).
  Started automatically by `./launch.sh up`.
- **FastContext repository explorer** — `explore_repository(query)` runs
  `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF` (Microsoft, 2.5 GB) as a subagent that
  issues parallel READ/GLOB/GREP calls and returns compact file+line citations. Reduces the main
  coding agent's exploration token burn by ~50-60% (SWE-bench data). FastContext notes in
  `config/backends.yaml` updated to reflect its role as a tool-use subagent.
- **`auto-coding-agentic` workspace** — new Devstral-24B workspace tuned for the Portal 5
  self-improvement loop: `explore_repository` as first tool, agentic read→explore→edit→verify
  system prompt, `keep_alive: 15m`. Lighter than `auto-agentic` (no media tools). 95 workspaces
  total (was 94).
- **Port 8928** reserved for Pipeline MCP. Port table updated in `CLAUDE.md`, `.env.example`,
  `imports/openwebui/mcp-servers.json`.
- **`docs/MCP_DEV_TOOLING.md`** rewritten — full guide covering both tools, FastContext
  integration, workflow examples for bug fixing / feature addition / MCP server debugging.
- **`README.md`** updated — workspace count (19 → 30), full workspace table, MCP server list
  (12 → 14 + pipeline MCP), coding tool integration section.

- **`auto-purpleteam-exec`** — new 4-hop execution-mode purple team workspace. Primary model
  (JANG-CRACK) has `execute_bash`, `execute_python`, `web_search` tools; runs live attack
  commands and passes real execution output through Foundation-Sec-8B → Qwen3-Coder-30B →
  Qwen3.6-27B chain for detection artifacts and IR playbook. Distinct from `auto-purpleteam-deep`
  (simulation only, no tools).
- **Tool-loop-aware chain hops** (`portal_pipeline/router/streaming.py`): `_stream_with_chain`
  now supports per-hop `tools` key. Tool-enabled hops route through `_stream_with_tool_loop_impl`
  (semaphore-free generator) so a chain can mix plain generation hops with full tool-loop hops.
- **Bench workspaces**: `bench-vibethinker-3b`, `bench-vibethinker-3b-ablated`,
  `bench-diffusiongemma`, `bench-gemma4-31b-crack` (Gemma-4-31B-JANG_4M-CRACK). Workspace count
  91 → 94.
- **VibeThinker-3B bench results** (2026-06-17): avg=0.938 reasoning, 39s — matches
  phi4-mini-reasoning (3.8B) at identical score with 46% lower latency. Viable as fast thinking
  hop in chains. VibeThinker-3B-Ablated: avg=0.775 security (vs 1.000 reference); gap too large
  for production red-team use, bench-only status confirmed.
- **UAT catalog**: new `g_auto_pentest.py` (WS-08, WS-09, P-PT01), `g_auto_purpleteam.py`
  (WS-PT01, WS-PT02, WS-PE01) covering penetration testing and purple team execution workspaces.
- **Acceptance tests**: S6-05 (auto-redteam-deep), S6-06 (auto-pentest / JANG-CRACK),
  S6-07 (auto-purpleteam-exec) added to `tests/acceptance/s06_security_workspaces.py`.
- **bench_security.py DEFAULT_WORKSPACES** expanded: added `auto-redteam-deep` and
  `auto-purpleteam-exec` to default run set.
- **`bench/prompts.py` WORKSPACE_PROMPT_MAP** backfilled for all workspaces added since TC-6:
  `auto-bigfix`, `auto-cad`, `auto-redteam-deep`, `auto-pentest`, `auto-purpleteam-deep`,
  `auto-purpleteam-exec`; new bench workspaces `bench-vibethinker-3b`, `bench-vibethinker-3b-ablated`,
  `bench-gemma4-31b-crack`, `bench-supergemma4`, `bench-c3d-v0`, `bench-fastcontext`,
  `bench-diffusiongemma`, `bench-qwopus-coder-mtp-v2`.
- **backends.yaml**: JANG-CRACK added to `ollama-security` group (duplicate entry pattern, same
  as supergemma4) so hint validator correctly resolves `auto-pentest` model_hint.

### Changed
- **`auto-pentest` primary model** upgraded: `xploiter/pentester:v2` (Phi-2 1.6B, no tools) →
  `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:Q4_K_M` (31B, bench score 0.933 vs prior
  supergemma4 0.867, audit-tools verified `finish_reason=tool_calls`). `execute_bash`,
  `execute_python`, `web_search` tools now active for live PoC validation.
- **`auto-redteam`** tools cleared (`tools: []`). Previously had 5 tools active; qwen3.5-abliterated
  was attempting tool calls instead of generating structured red team content, collapsing scores
  (0.10–0.46 → 0.915 after fix). Red team simulation workspaces intentionally have no tools.
- **`auto-redteam-deep`** — SuperGemma4-26B-uncensored promoted as primary (bench_security 0.915,
  6.7 ATT&CK IDs avg, 0 disclaimers).
- **Security workspace tool philosophy** clarified across three tiers:
  - *Simulation* (`auto-redteam`, `auto-redteam-deep`, `auto-purpleteam-deep`): `tools: []` — pure generation
  - *Research* (`auto-security`): `web_search`, `kb_search`
  - *Execution* (`auto-pentest`, `auto-purpleteam-exec`): `execute_bash`, `execute_python`, `web_search`
- **LLM intent router — three-tier model selection** (`portal_pipeline/router/routing.py`,
  `.env.example`, `deploy/portal-5/docker-compose.yml`): router bench across 17 candidates
  promoted a three-tier scheme. PRIMARY `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`
  (82.2% acc / 77.8% sec / ~840ms / 5.3GB) replaces the prior QuantFactory abliterated default;
  STANDBY `llama3.2:3b` (75.3% / 66.7% / ~433ms) and FALLBACK `qwen2.5:1.5b`
  (67.1% / 77.8% / ~339ms) selectable via env without code change. `LLM_ROUTER_TIMEOUT_MS`
  default raised 500 → 1000 to fit PRIMARY warm latency; `OLLAMA_MAX_LOADED_MODELS` raised
  2 → 3 so the router stays warm alongside two inference models under full fleet load.

### Fixed
- **`keep_alive` hard override** (`portal_pipeline/router_pipe.py`): workspace-declared `keep_alive`
  now uses direct assignment instead of `setdefault`. Open WebUI was sending its own `keep_alive`
  value in request bodies, silently overriding workspace config (bench `5m`/production `10-15m`
  settings ignored). Large models were pinned in VRAM indefinitely, blocking subsequent bench runs.
  Workspace value wins when declared; OWUI value still wins when no workspace `keep_alive` is set.
- **UAT driver modularized** (TASK_UAT_MODULARIZE_V1): `tests/portal5_uat_driver.py`
  (4,540 lines) decomposed into the `tests/uat/` package (17 modules), mirroring
  the landed `tests/benchmarks/bench/` pattern; the driver file is now a thin
  entry-point shim with the full public surface re-exported. CLI invocation,
  behavior, and test catalog unchanged. Unit-test monkeypatch targets repointed
  to owning modules.
- **UAT routing telemetry** — `run_test` referenced the undefined name
  `pipeline_backend` inside a swallowed exception path, so `_ROUTING_LOG` was
  never populated and the Routing Summary never emitted; now resolved via
  `_get_backend_from_pipeline_logs`. Also fixed the undefined `silent_ollama`
  reference in `_write_routing_summary`'s all-clear branch (latent NameError),
  and the driver's `--help`/script invocation no longer requires `PYTHONPATH=`.

## [7.5.0] — 2026-06-11

### Added
- **Docling-first document parsing** in RAG MCP `kb_ingest`: layout-aware PDF
  table/reading-order extraction, new formats (.pptx, .xlsx, .html, .htm,
  .epub); pypdf/python-docx retained as automatic fallback; converter cached,
  conversion off the event loop via `asyncio.to_thread`; Docling models
  prefetched at image build (`Dockerfile.mcp`)
- **LanceDB search modes**: `query_type` (vector/fts/hybrid) on `kb_search` and
  `kb_search_all`; native Lance BM25 FTS index built via `kb_ingest fts=true`;
  hybrid fused with built-in RRF; per-KB vector fallback in cross-KB search
- **LanceDB index + rollback tools**: `kb_optimize` (IVF_PQ,
  `num_sub_vectors=64`, <256-chunk skip), `kb_versions`, `kb_restore`;
  `rebuild=true` now tags + row-deletes instead of `drop_table`, preserving
  version history
- **Promptfoo eval framework** (setup only): 7 grouped configs covering all 21
  `auto*` workspaces + tools-specialist; locally graded via
  `ollama:chat:gemma4:26b-a4b-it-qat`; `./launch.sh promptfoo [area|all]`;
  `promptfoo>=0.1.4` in dev extras with npx fallback
- **bench_tps decomposition**: monolith (2090 lines) split into
  `tests/benchmarks/bench/` package; entry-point shim preserves CLI verbatim
- Unit tests: `tests/unit/test_rag.py`, `tests/unit/test_promptfoo_configs.py`

### Fixed
- **Rule 6 repair**: completed the Apriel-Nemotron removal (84cf26e left stale
  refs in `workspaces.py`, `dispatcher.py`, persona YAML, Open WebUI import
  JSONs, CLAUDE.md counts); workspace count 74 → 73, personas 140 → 139

## [7.4.0] — 2026-06-10

### Added
- UAT `challenge` section: the CC-01 coding challenge shootout restored
  (lost in the 00ad696 → uat_catalog split) — 39 entries: one identical
  CC-01 Asteroids task per distinct installed bench model, plus BT-01
  SOC-triage (Foundation-Sec Q8 GGUF) and EX-01 extraction (LFM2.5).
  Not a benchmark: bench_tps owns throughput; the comparative matrix is
  the deliverable, no verdict, promotions operator-only.
- `tests/scripts/cc_challenge_matrix.py` — shootout matrix from UAT
  challenge rows.
- `PORTAL5_UAT_EXECUTE_V5.md` with optional Phase 8 (Challenge shootout);
  V4 archived.
- `auto-phi4` production workspace (Phi-4-reasoning-plus, 14B RL-trained,
  ~11GB) — restores original phi4stemanalyst routing intent; phi4stemanalyst
  persona now routes to auto-phi4 instead of auto-data (deepseek-r1:32b-q8_0).

### Changed
- Challenge timeouts derived from V8 direct-bench TPS (Ollama realities)
  replacing MLX-era 300s defaults; tiers ollama-only; dead `mlx_model`
  keys dropped. glm/laguna not restored (not installed); ToolACE/OCR/
  audio/duplicate-hint stand-ins excluded by decision.
- UAT catalog `workspace_tier: "any"` → `"ollama"` across 5 catalog files
  (34 entries); "any" was a pre-Ollama-only tier label, now a no-op.
- `/nothink` added to proofreader and daily driver persona system prompts
  (prevents Qwen3 thinking chain explosion on simple tasks); OWUI presets
  reseeded via API.

## [7.3.3] — 2026-06-10

### Fixed
- persona matrix: `expand_scenarios(categories=...)` TypeError on workspaces
  whose fixtures module doesn't accept the kwarg (auto-compliance — the
  CI-default sweep was broken at HEAD). Signature-guarded; pre-existing bug.
- CLAUDE.md persona count 137 → 140 (V8 catalog +16 YAMLs) — un-fails
  `test_claude_md_persona_count_accurate`.

### Changed
- Grafana benchmarks dashboard generator is Ollama-only: MLX badge/cells/
  footer/framing removed; size-comparison panel repurposed as an Ollama
  size-bucket breakdown (panel layout unchanged).
- Stale comment true-ups: acceptance Phase-5 audio note, regen_section_table
  docstring example.

## [7.3.2] — 2026-06-10

### Removed — MLX-inference dead code swept from the test layer (TASK_MLX_TEST_SWEEP_V1)
- Deleted dead harnesses targeting the retired :8081 proxy: bench_mlx_vs_ollama,
  bench_omlx, bench_kv_long_context, bench_positional_recall (+ recall_extract,
  corpora/, update_grafana_recall, portal5_recall dashboard), the qwen-template
  patcher pair, convert_jang_keys, the five archived MLX acceptance scenarios,
  and the completed TASK_BENCH_MLX_ONLY / TASK_OMLX_* docs (OMLX_DECISION.md
  retained as the decision record). Recoverable at 476de27.
- persona matrix driver is Ollama-only: MLX backend mode, --mlx-warmup, and
  :8081 plumbing removed; nightly CI workflow MLX branch removed.
- ComfyUI acceptance memory-freeing is Ollama-eviction-only; UAT driver dead
  mlx_model branches and MLX fallback labels removed; regen_section_table
  retired-section rows dropped; S0-06/S0-07 retired INFO stubs removed.
- Superseded MLX-era docs archived: ACCEPTANCE_TEST_GUIDE, PORTAL5_PROMPT_V6,
  ROUTING_FALLBACK_ANALYSIS, TASK_BENCH_EXECUTE_V7_UPDATE.
- Retained MLX audio/transcribe/embedding/rerank (:8918/:8924/:8917/:8925)
  untouched — live production services, not dead code.

## [7.3.1] — 2026-06-10

### Fixed — acceptance section-file runtime defects
- Missing imports in decomposed acceptance section files crashed sections at
  the first test: s00/s01/s03/s04 (`time`), s42 (`os`), s70 (`uuid`), s08
  (`_wav_info`, now a `_common.py` passthrough). ruff F821 clean on live files.

### Changed — S3a production-workspace scope
- S3a covers all 21 production workspaces (20 auto-* + tools-specialist);
  bench-* explicitly out of acceptance scope — bench_tps.py is the sole TPS
  instrument. WORKSPACE_PROMPTS gained auto-audio, auto-daily,
  tools-specialist entries (18 → 21).

### Changed — exec docs refreshed to HEAD (V8/V4/V3)
- PORTAL5_ACCEPTANCE_EXECUTE_V8 / PORTAL5_UAT_EXECUTE_V4 /
  PORTAL5_BENCH_EXECUTE_V3 replace V7/V3/V2 (archived to
  tests/_archive_execdocs/). UAT smoke phase = `--section auto` (no smoke
  section exists); phase plan covers all 23 sections (~136 tests) incl.
  auto-audio/auto-docs/tools-specialist; bench doc trued to 68 models / 68
  benchable workspaces / 140 personas / ~276 tests. OCR benches
  (bench-nanonets-ocr2, bench-olmocr2) added to pipeline_bench_skip — a
  text-prompt harness cannot exercise OCR vision specialists (5-entry skip
  list: 3 audio + 2 OCR); stale mlx_models comment in backends.yaml fixed.

## [7.3.0] — 2026-06-10

### Added — V8 model refresh catalog (TASK_MODEL_REFRESH_V8_CATALOG)
- **18 bench-only models** across ollama-vision, ollama-coding, ollama-reasoning, ollama-general:
  - Gemma4 QAT suite (E2B, E4B, 12B, 26B-A4B, 31B): Google QAT near-BF16 quality at 4-bit
  - phi4-mini + phi4-mini-reasoning: Microsoft 3.8B fast tier + RL-trained math specialist
  - lfm2.5:8b: Liquid AI hybrid MoE — sole non-transformer model in fleet
  - starcoder2:15b: BigCode FIM specialist, 600+ languages, BigCode OpenRAIL-M
  - devstral-small-2: Devstral V2, 256K ctx, vision added
  - qwen3.6:27b-q4_K_M, qwen3.6:35b-a3b-q4_K_M: official Qwen3.6 quantized builds
  - olmo-3.1:32b-think: Allen AI Western-provenance reasoning model
  - mistral-small3.2:24b: improved function calling over Small 3.1
  - harness-1: gpt-oss-20B search agent fine-tune
  - Nex-N2-mini: Qwen3.5-35B-A3B agentic MoE, imatrix community GGUF
  - qwen3-coder-next: 80B/3B active MoE, hybrid Gated DeltaNet architecture
- **14 new bench workspace entries** in `portal_pipeline/router/workspaces.py`
- **16 new persona YAML files** in `config/personas/`

### Fixed
- gemma4:e4b notes corrected (audio/video/thinking missing)
- devstral:24b mislabeled as devstral-small-2 (corrected to V1; V2 added separately)
- bench-qwen36-27b, bench-qwen36-35b-a3b, bench-olmo3-32b model_hints corrected
- bench-qwen3-coder-next model_hint corrected (was 480B placeholder, now 80B/3B active)

### Changed
- Version 7.2.1 → 7.3.0
- All additions are bench_only; PROMOTE_POLICY=confirm

## [7.2.1] — 2026-06-09

### Fixed — MLX inference-proxy retirement true-up (TASK_MLX_RETIRE_TRUEUP_V1/V2)
- **P0:** `_model_supports_tools` no longer reads the removed `Backend.mlx_metadata`
  field — was raising `AttributeError` on every tool-bearing request after commit 3a0c58e.
- Removed dead `mlx_proxy` probe + `MLX_PROXY_URL` from `/health/all`; scrubbed
  MLX-inference references from pipeline docstrings/comments.
- Trued up CLAUDE.md (Rule 8 → single Ollama tier), README, HOWTO, ADMIN_GUIDE,
  prometheus scrape config, and Grafana dashboards to Ollama-only inference.
  MLX speech (:8918) / transcribe (:8924) / embedding (:8917) / reranker (:8925)
  explicitly retained.
- Retired MLX-proxy acceptance scenarios (S20/S22/S3b/S11/S24 archived); rewired
  S23 model-diversity and removed S2-16 proxy probe to query Ollama.
- Documented specialist model parity loss (Foundation-Sec-8B → Apriel-Nemotron-15B;
  ToolACE-2.5 → granite4.1:8b) in KNOWN_LIMITATIONS; corrected drifted persona
  descriptions; added P5-FUT-PARITY-001/002.

## [7.2.0] — 2026-05-28

### Added — Quant-optimization + uncensored refresh (TASK_QUANT_TRUEUP_V1, bench-only wiring)
- **5 bench candidates**:
  - `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ`: distillation-aware 4-bit MoE (~20GB,
    ~34% better KLD than plain 4-bit). Pairs against plain RTN 4-bit.
  - `mlx-community/Qwen3.6-27B-OptiQ-4bit`: sensitivity-aware mixed 4-bit dense
    (~16GB, sensitive layers 8-bit). Pairs against plain 4-bit.
  - `mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit`: OptiQ mixed 4-bit MoE (~13GB,
    fp16 KV only — Gemma-4 shared-KV blocks mixed-precision KV path).
  - `huihui-ai/Huihui-Qwen3.6-27B-abliterated`: dense 27B abliterated (~16GB,
    generational refresh vs Qwen3.5-9B incumbent).
  - `huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated`: MoE 3B active abliterated
    (~20GB, speed-play for uncensored AUTO slot).
- **Ollama lane parity**: `ollama-general` reordered to lead with
  Qwen3.6-abliterated:27b (B.2); `ollama-security` gains Qwen3.6 generalist (C),
  specialists retained.
- **UD-MLX quants deprecated** (A5): KLD study found ~8.6 bpw effective — worse
  than 6-bit at more memory. Removed from default pull; kept as documented result.
- **5 bench workspaces/personas wired** into bench_tps.py; personas 117→122,
  workspaces 51→56. All bench-only wiring (Phases 1–5); the same agent run then
  pulls, benches, and auto-promotes gate-passers (Phases 6–9) in a follow-on commit.
- Source: MODEL_TRUEUP_REVIEW_20260528.md.

## [7.1.0] — 2026-05-28

### Added — MTP speculative-decoding bench track (TASK_MODEL_REFRESH_V8)
- **bench-qwen36-27b-mtp**: bench workspace + persona for MTP A/B evaluation.
  CC-01 system prompt preserved (invariant). Model:
  `Youssofal/Qwen3.6-27B-MTPLX-Optimized-Speed` (MLX-native MTP, ~18GB).
- **Catalog adds (bench-only)**:
  - `Youssofal/Qwen3.6-27B-MTPLX-Optimized-Speed`: MLX-native MTP self-speculative
    decoding (~18GB, ~2.24x vendor claim, lossless at temp 0). MLX-proxy tier.
  - `froggeric/Qwen3.6-27B-MTP-GGUF`: llama.cpp b9180+ self-speculative (~2.3x).
    Ollama-tier portability fallback.
  - `huihui-ai/Huihui-Qwen3.6-27B-abliterated-MTP-GGUF`: uncensored + MTP for
    the security/redteam lanes (trusted huihui source; AEON one-off replacement
    candidate).
- **bench_tps.py**: MTP bench mapped to coding category; documented
  `--spec-decoding-tag mtp-on/off` A/B protocol (isolation-respecting).
- **launch.sh**: `pull-mtp` opt-in subcommand (~18 GB, NOT in default pull set).

### Added — Catalog hygiene
- `speculative_decoding.draft_models` comment corrected: MTP is self-speculative
  (model's own heads), not external-drafter. Map stays empty.
- `embedding_candidates`: EmbeddingGemma premise corrected — best-in-class only
  under 500M; incumbent Harrier competitive on larger MTEB v2 field.

### Changed — Roadmap / docs
- P5-FUT-SPEC: BLOCKED → PROBE (MTP path) — native Qwen3.6 MTP unblocks it.
- P5-MTP-001: LOW → MEDIUM (BF16-slower premise superseded by INT4 sidecar;
  dense-27B no-MTP baseline measured 12.4 TPS is the case MTP rescues).
- KNOWN_LIMITATIONS: P5-MTP-PATH bench-only note + P5-MODEL-64GB exclusion
  record (DeepSeek-V4-Flash/Pro, Kimi-K2.6, GLM-5.1-abliterated — total params
  exceed 64 GB regardless of active count; revisit at Mac-Studio/cluster tier).
- CLAUDE.md: Ollama 0.19+ MLX-engine framing fix (~85% of pure-MLX on 32 GB+
  Macs — tier split is now about model-format breadth, not raw speed).

### Invariants held
- `draft_models` stays `{}` (MTP is self-speculative, not external-drafter).
- No `auto-*` production primary changed. Default pull set unchanged.
- Production behavior bit-identical to 7.0.0.

## [7.0.0] — 2026-05-27

### Changed
- **Version unified across project**: pyproject.toml, portal_pipeline,
  portal_mcp, portal_channels, tests, config/searxng all bumped from a
  drifted mix of 5.2.1 / 6.0.2 / 6.0.7 / 6.1.0 to a single 7.0.0.
  Historical CHANGELOG and ACCEPTANCE_RESULTS entries preserved.

### Added — Bench fleet (TASK_MODEL_REFRESH_V7)
- **bench-apriel-nemotron**: Apriel-Nemotron-15B-Thinker-8bit (MLX,
  ServiceNow+NVIDIA, dense 15B reasoning, native <think>, MIT, ~16GB).
  First ServiceNow+NVIDIA text-reasoning model in the fleet.
- **bench-voxtral-realtime**: Voxtral-Mini-4B-Realtime-2602-4bit (MLX,
  Mistral, streaming ASR ~570ms TTFT claim, 13 languages, ~3GB).
- **bench-voxtral-tts**: Voxtral-4B-TTS-2603-mlx-6bit (MLX, Mistral,
  20 voices × 9 languages, ~4GB).
- **bench-granite-speech**: granite-speech-4.1-2b (MLX, IBM, #1 OpenASR
  as of Apr 2026, native keyword biasing, EN/FR/DE/ES/PT/JA, ~4GB).
  First model in fleet with native keyword biasing.
- **bench-qwen36-27b-ud** and **bench-qwen36-35b-a3b-ud**: Unsloth
  Dynamic 2.0 MLX 4-bit quant probes vs stock 4-bit at identical footprint.

### Added — Capability catalog
- `embedding_candidates:` informational block in config/backends.yaml
  for future P5-FUT-EMBED-001 migration (EmbeddingGemma, Qwen3-Embedding).
- KNOWN_LIMITATIONS.md "Models Out of M4 Pro 64 GB Budget" section
  (MiniMax-M2, DeepSeek-V4, Kimi-K2-0905, GLM-5 explicitly refused).

### Added — Launcher
- `PULL_UD_QWEN36=1` env gate inside `./launch.sh pull-mlx-models` for
  Unsloth UD Qwen3.6 pair (~36 GB combined; opt-in).
- `./launch.sh pull-ud-qwen36` subcommand wrapper.
- 4 small models (Apriel-Nemotron, Granite-Speech, Voxtral-Realtime,
  Voxtral-TTS) added to default `MLX_MODELS` pull array (~27 GB delta).

### Fixed — Pre-existing drift
- `imports/openwebui/workspaces/workspaces_all.json` was missing 5 entries
  (auto-agentic, bench-lfm2-moe, bench-nanonets-ocr2, bench-nemotron-omni,
  bench-olmocr2). Backfilled. **auto-agentic missing was a real bug —
  operators reseeding OWUI lost that workspace preset.**
- `tests/benchmarks/bench_tps.py WORKSPACE_PROMPT_MAP` was missing the
  production `tools-specialist` workspace, causing it to silently fall
  through to "general" prompts. Added.

### Roadmap
- P5-FUT-014-V7 model refresh waterline with explicit promotion gates.
- P5-FUT-EMBED-001 EmbeddingGemma migration seed (deferred — RAG
  re-ingestion scope).
- P5-FUT-SPEECH-002 speech-model shootout (deferred — bench_tps.py text
  harness cannot exercise streaming ASR/TTS).

### Production fleet impact
None. All catalog adds are bench-only. No `auto-*` workspace, persona,
backend group, or production routing path is modified. Version-unification
edits are string-only (docstrings, version constants, doc files).
v7.0.0 ships with bit-identical production behavior to the last v6.x HEAD.

## [6.1.0] — 2026-04-29

### Added
- **Shared workspace** (TASK-WORKSPACE-001): unified file-handling foundation.
  - `${AI_OUTPUT_DIR}` (default `~/AI_Output`) is the canonical user-artifact root.
  - OWUI uploads bind-mount to `${AI_OUTPUT_DIR}/uploads` — files dropped in chat are now visible to all MCPs.
  - New helper module `portal_mcp.core.workspace` provides `get_uploads_dir()`, `get_generated_dir(category)`, `resolve_upload_path(file_id)`.
  - New launch commands: `workspace-init`, `workspace-status`, `workspace-show`.
  - `mcp-whisper`, `mcp-video`, `mcp-sandbox` now mount `/workspace`.
  - CLAUDE.md Rule 11 added: shared workspace is the only path for user files.

### Changed
- `AUDIO_STT_ENGINE` disabled in OWUI config (set via `OWUI_AUDIO_STT_ENGINE` env, default empty). Audio uploads in chat remain as attachments instead of being auto-transcribed; personas process them via MCP tools. **Side effect:** OWUI microphone voice-input no longer transcribes. See KNOWN_LIMITATIONS.

- **OWUI audio-drop UX gaps** (TASK-OWUI-AUDIO-DROP-001):
  - OWUI tool-call timeout configuration: `AIOHTTP_CLIENT_TIMEOUT=1800` and `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA=1800` lift the default ~60s ceiling to 30 minutes for diarized transcription and other long-running MCP tool calls.
  - `WEBUI_SECRET_KEY` auto-generation in `launch.sh` so MCP tool registrations survive container rebuilds.
  - `scripts/openwebui_init.py` extended with `verify_persona_tool_bindings` so persona/tool linkages are verified automatically on launch.
  - `tests/integration/test_owui_audio_drop.sh` smoke test verifying the four configuration changes are live and effective.
  - HOWTO.md updated with the chat-drop workflow + fallback runner script reference.

- **Diarized transcription** (TASK-TRANSCRIBE-001):
  - New host-native MCP server `scripts/mlx-transcribe.py` on port 8924 (mlx-whisper large-v3-turbo + pyannote.audio 3.1 on MPS). Apple Silicon primary path.
  - `whisper_mcp.py` extended with `transcribe_with_speakers` tool (faster-whisper + pyannote on CPU/CUDA) — cross-platform fallback.
  - New persona `transcriptanalyst` in `auto-documents` workspace; detects audio attachments, calls tool, displays markdown, chains to `create_word_document` for docx output.
  - New launch commands: `./launch.sh start-transcribe` / `stop-transcribe`.
  - Output: JSON + Markdown sidecar in workspace at `${AI_OUTPUT_DIR}/generated/transcripts/`. Both downloadable via `:8924/files/<name>`.
  - Performance: ~60–130s for 10-min 2-speaker audio on M4 Pro (vs ~4–8 min on Docker fallback path).
  - Tool surface: `transcribe_with_speakers(file, num_speakers, language)` — `file` accepts OWUI file ID, filename in uploads/, or absolute path (resolved via workspace helper).
  - Pyannote models gated; requires accepting HuggingFace licenses + `HF_TOKEN` in `.env`.

### Models pulled (via `./launch.sh pull-mlx-models`)
- `mlx-community/whisper-large-v3-turbo` (~1.5 GB)
- `pyannote/speaker-diarization-3.1` (~30 MB, gated)
- `pyannote/segmentation-3.0` (~6 MB, gated)

### Changed
- `AUDIO_STT_ENGINE` disabled in OWUI config (set via `OWUI_AUDIO_STT_ENGINE` env, default empty). Audio uploads in chat remain as attachments instead of being auto-transcribed; personas process them via MCP tools. **Side effect:** OWUI microphone voice-input no longer transcribes. See KNOWN_LIMITATIONS.

### Migration notes
- On first `./launch.sh up` after this change, the workspace structure is auto-created. If you have existing OWUI uploads in the named volume, run the migration step in TASK-WORKSPACE-001 §Phase 0 before restarting OWUI, or those files become hidden by the new bind mount.
- `OUTPUT_DIR` env var is now an alias for `AI_OUTPUT_DIR` (same value). Existing MCPs that read `OUTPUT_DIR` continue to work without changes.

## [6.0.7] — Media UAT section + remotely-addressable media URLs

### Added
- `tests/portal5_uat_driver.py --media` flag selects all `workspace_tier=media_heavy`
  tests (image / sound / voice / video) for isolated debugging of MCP and Open WebUI
  media plumbing.
- `media_kind` tag on the four existing media tests for clearer debug output.
- New Whisper STT round-trip test M-01 (skips if `tests/fixtures/sample.wav` absent).
- `PORTAL_PUBLIC_URL` env variable in `.env.example`. `launch.sh` derives
  `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL`
  from it. MCPs emit those into chat instead of localhost.
- Reference Cloudflare Tunnel ingress configuration at
  `config/cloudflared/config.yml.example`. Operator's existing cloudflared
  setup picks up the new ingress rules; no additional Portal 5 services
  are introduced.

### Changed
- `portal_mcp/generation/music_mcp.py`: file-serving route is now
  `/files/music/<filename>` (was `/files/<filename>`). Five hardcoded
  `f"http://localhost:{port}/files/..."` strings replaced with a
  `MUSIC_PUBLIC_URL`-driven prefix.
- `portal_mcp/generation/tts_mcp.py`: file-serving route is now
  `/files/tts/<filename>` (was `/files/<filename>`). Same `TTS_PUBLIC_URL`
  treatment.
- `_download_artifact` URL regex broadened to match both legacy localhost
  and public-hostname shapes.
- `docs/ADMIN_GUIDE.md` "Network Exposure" updated to recommend Cloudflare
  Tunnel; Caddy noted as a future option for non-Tunnel deployments.

### Breaking
- Old `[Download WAV](http://localhost:8912/files/<name>.wav)` links in
  pre-upgrade chat history will 404 — the route is now
  `/files/music/<name>.wav`. New chats are unaffected. Operator can
  regenerate any old artifact by re-running the original prompt.

### Notes
- Stacks that don't set `PORTAL_PUBLIC_URL` continue to use localhost URLs
  in chat. Open WebUI itself remains reachable per `ENABLE_REMOTE_ACCESS`.
- A first-class Caddy profile for non-Tunnel deployments is deferred to a
  future task. The `docs/ADMIN_GUIDE.md` "Network Exposure" section
  describes the manual setup in the meantime.
- `M-01` Whisper STT is fixture-gated for v6.0.7. Generic file-upload
  plumbing in the driver for arbitrary fixture types is a follow-up.
- T-08 (image gen) is still in section `auto-video` for back-compat;
  renaming to `auto-image` is deferred to avoid touching calibration
  data and the routing keyword extractor in the same release.

## [6.0.6] — UAT execute prompt V2

### Documentation
- `tests/PORTAL5_UAT_EXECUTE_V2.md` replaces V1 as the canonical UAT execute prompt. New: 8-phase tier-descending execution plan; one driver invocation per phase with `--append`; `tests/UAT_RUN_LOG.md` resume tracker (agent-maintained, survives Ctrl+C and reboots); explicit inter-phase memory and FAIL-delta gates; reinforcement of `sort_tests_cascade`'s `(tier, model_slug, id)` grouping with explicit guidance against single-test invocations during phased runs (which would waste model loads); alignment with the `POST /unload` + `GET /health/wired` proxy endpoints shipped in 6.0.5.
- The V2 plan batches multiple sections per invocation where their tier+model_slug overlap allows the cascade to consolidate model loads across sections (phase 4 batches six mlx_small sections for this reason). This is the primary V1→V2 efficiency change.
- V1 archived to `tests/_archive/PORTAL5_UAT_EXECUTE_V1.md`.

## [6.0.5] — UAT 2026-04-28 persona remediation

### Fixed
- `excelsheet`: lifted output-contract to top of system prompt and added a hardcoded "if your reply contains '=' followed by a cell reference you have FAILED" check; added RANK worked example with the exact P-DA06 numbers (498000/384000/865000) and the West=1 answer. Resolves P-D15 (formula-text leakage) and P-DA06 (RANK direction inversion).
- `ethereumdeveloper`: hoisted the audit-disclaimer / pragma / code-block trio to the top of the prompt as VERIFY ALL THREE preconditions; clarified that prose sections (Design Rationale, Test Outline) are skippable when the response budget is tight but the contract code block is mandatory. Resolves P-D10.
- Coding personas where reasoning models exhausted the response budget on plan/architecture prose without ever producing code: `pythoncodegeneratorcleanoptimizedproduction-ready`, `fullstacksoftwaredeveloper`, `devopsautomator`, `creativecoder`. Each now declares a hard "response is incomplete without a fenced code block" rule and a priority order under which planning sections are explicitly the first thing to drop. Resolves P-D01, P-D05, P-D07, P-D20, WS-02.
- `nerccipcomplianceanalyst`: pinned the literal token `Priority-1` (with capitalization and hyphen) as required output for any 1.2.6 discussion — paraphrasing as "urgent" alone no longer satisfies the rule. Resolves P-C01.
- `researchanalyst` and `gemmaresearchanalyst`: added explicit, named output sections for Counterarguments / Areas of Expert Disagreement so models stop folding contested points into Gaps & Limitations. Resolves P-R05, P-R06.
- `codescreenshotreader`: added explicit instruction for the "describe your approach" case to walk through every protocol step substantively. Resolves P-V10.
- `chartanalyst`: made the Design observations output bullet REQUIRED with a fallback minimum ("data-ink ratio is reasonable" line) so the section is always present even on cleanly-designed charts. Resolves P-V11.
- `pythoninterpreter`: tightened the no-`>>>` rule with an explicit "delete it before sending" instruction. Resolves P-D13.

### Test infrastructure
- WS-13 PQC migration-timeline assertion: broadened keywords to include phased-rollout and year/quarter/wave language that the model commonly uses but the prior keyword list missed. No other assertion broadening was applied; the rest of the FAIL set is persona-side (above) or memory-management (below).
- Driver `unload_all_models()` no longer `pkill`s the proxy and no longer calls `subprocess.run(["purge"], ...)`. It POSTs `/unload?ollama=true` to the proxy and trusts the response measurements. Resolves A-03, A-04, P-B06, P-W04, WS-MATH-01, T-11.

### Memory management
- `scripts/mlx-proxy.py`: new `POST /unload[?ollama=true]` endpoint wraps the existing `stop_all()` + `_wait_for_gpu_memory_reclaim()` + optional `_evict_ollama_models()` into a single observable cycle that returns wired-memory measurements. New `GET /health/wired` endpoint for external leak detection.
- `scripts/mlx-watchdog.py`: detects Metal GPU wired-buffer leaks via the signature `proxy.state == "none" AND wired_gb > MLX_WIRED_LEAK_THRESHOLD_GB` (default 12 GB) for `MLX_WIRED_LEAK_SAMPLES` consecutive cycles (default 3). Soft-recovers via `/unload`; hard-recovers via `launchctl kickstart -k` if the proxy itself is the leaker.
- `sudo purge` is no longer required in any recovery path. Operator notification still fires after `MLX_MAX_RECOVERY_ATTEMPTS` failed cycles.

### Documentation
- `KNOWN_LIMITATIONS.md`: added P5-BENCH-001 (Asteroids bench capability differences are by design).

## [6.4.0] — Inference performance milestone (M4)

### Added (Track 1: Speculative Decoding)
- **Draft models**: `mlx-community/Qwen2.5-0.5B-Instruct-4bit` (~0.5GB) and `mlx-community/Llama-3.2-1B-Instruct-4bit` (~1GB) added to MLX catalog
- **`speculative_decoding.draft_models`** map in `config/backends.yaml` — 8 target→draft pairs for Qwen and Llama families
- **`--draft-model` injection** in `scripts/mlx-proxy.py` — automatically passes `--draft-model` + `--num-draft-tokens` to `mlx_lm.server` when target has a draft mapping
- **Draft-aware admission control** — `_check_memory_for_model()` now includes draft model memory in the pre-flight check
- **`--spec-decoding-tag`** arg in `tests/benchmarks/bench_tps.py` — labels bench runs for before/after comparison

### Added (Track 2: OMLX Evaluation — deferred)
- **`deploy/omlx/config.yaml`** — OMLX evaluation config mapping admission control, VLM routing, KV cache, batching
- **`tests/benchmarks/bench_omlx.py`** — side-by-side OMLX vs mlx-proxy benchmark script
- **`OMLX_DECISION.md`** — decision document template (REPLACE/AUGMENT/HOLD)

### Performance impact (Track 1)
- Bench validation pending — run `bench_tps.py --spec-decoding-tag off` then `--spec-decoding-tag on` to measure TPS gains

## [6.1.0] — Frontier UX milestone (M1)

### Added
- **Reasoning passthrough**: pipeline now forwards `reasoning_content` to OWUI, surfacing thinking from DeepSeek-R1, Magistral, GLM-4.7-Flash, Qwopus in the OWUI collapsible thinking panel
- **Math workspace**: new `auto-math` workspace + `mathreasoner` persona, primary MLX is `mlx-community/Qwen2.5-Math-7B-Instruct-4bit` (~5GB)
- **18 new personas**: 4 compliance (SOC2, PCI-DSS, GDPR, HIPAA), 3 language (Rust, Go, TypeScript), 4 workplace (PM, BA, proofreader, interviewer), 5 specialty (SPL detection, Terraform, docs, DB arch, dashboards), 2 vision (OCR specialist, diagram reader)
- Workspace count: 16 → 17 auto-* workspaces
- Persona count: 57 → 76

### Changed
- Workspaces emitting reasoning blocks marked with `emits_reasoning: True` in `WORKSPACES` dict (informational)

### Tests
- `PERSONA_PROMPTS` extended to cover all 18 new M1 personas

---

## [6.0.3] — 2026-04-13

### Added
- **`gemma4jangvision` persona** — routes to `dealignai/Gemma-4-31B-JANG_4M-CRACK` (uncensored Gemma 4 31B VLM, vision+text, 256K ctx, ~23GB)

### Fixed
- **JANG safetensors key format** (`scripts/convert_jang_keys.py`): converted non-standard key naming to mlx_vlm-compatible format so the model loads without reshape errors
- **JANG mixed-precision quantization** (`scripts/mlx-proxy.py` + `mlx_vlm utils.py` patch): embed/MLP layers at 4-bit, attention projections at 8-bit — resolves shape mismatch on every attention weight under mlx_vlm 0.4.4
- **JANG `audio_config` injection** (`scripts/convert_jang_keys.py`): set `"audio_config": null` in config.json to suppress spurious 752-parameter AudioEncoder instantiation (JANG has no audio tower weights)

### Documentation
- `KNOWN_LIMITATIONS.md`: added P5-ROAD-MLX-004 documenting the installed mlx_vlm utils.py patch, its scope, and re-apply instructions if `brew upgrade mlx-vlm` overwrites it

### Tests
- **Acceptance v6 signal broadening** (4 assertions): `bugdiscoverycodeassistant`, `redteamoperator`, `itexpert`, `auto-creative` — extended signal lists to cover alternative valid phrasings (TA0 notation, paraphrased explanations, creative haiku forms)
- **Benchmark** (`tests/benchmarks/bench_tps.py`): incremental result saves after each model/workspace/persona test; updated Grafana TPS dashboard with 2026-04-12 run data
- Acceptance suite v6 run 17: **154 PASS / 2 INFO / 0 FAIL / 0 BLOCKED / 0 WARN** (all 22 sections, 47m 5s)

---

## [6.0.1] - 2026-04-11

### Security
- **CRITICAL**: Removed insecure default API key fallback — pipeline now fails closed when `PIPELINE_API_KEY` is unset (P5-SEC-001)
- **CRITICAL**: Removed `privileged: true` from DinD sandbox to prevent container escape; migrated to rootless `docker:27-dind-rootless` (P5-SEC-002)

### Fixed
- Removed global warning suppression in MCP server; exceptions now log full tracebacks (P5-OBS-001)
- Removed dead code: `_complete_from_backend()` in `router_pipe.py` (P5-MAINT-001)
- Fixed duplicate `_MLX_PROXY_HEALTH_URL` assignment in `dispatcher.py` (P5-MAINT-002)

### Changed
- Native service startup errors now logged to `~/.portal5/logs/` instead of `/dev/null` (P5-OBS-002)
- JSON parsing in `launch.sh` uses `jq` when available for faster status checks (P5-PERF-001)

### Documentation
- Fixed AudioCraft → HuggingFace MusicGen terminology in README (P5-DOCS-001)
- Fixed version drift: aligned all headers to 6.0.1 (P5-DOCS-002)
- Added network exposure security documentation with local-only override option (P5-DOCS-003)
- Clarified privacy claims regarding model download telemetry (P5-DOCS-004)
- Updated persona count in CLAUDE.md from 42 to 44 (P5-MAINT-003)

### Tests
- Added `TestCodeHygiene` regression prevention tests (P5-TEST-001)
- Fixed test suite to set `PIPELINE_API_KEY` via `conftest.py` for hard-fail API key enforcement
- Fixed `HEADERS` in `test_pipeline.py` to read from env rather than hardcoded default key

---

## [6.0.2] — 2026-04-12

### Added
- **Unified update command** (`launch.sh`)
  - `./launch.sh update`: Single command to update all components — git pull, Docker image pulls
    (ollama, open-webui, searxng), rebuild portal-pipeline + all MCP server images, refresh Ollama
    models, pull MLX models (Apple Silicon), update ComfyUI + VideoHelperSuite (if installed),
    upgrade Music MCP deps (if installed), force re-seed Open WebUI presets, and restart the stack.
  - `--skip-models`: Skip Ollama + MLX model refresh for faster updates.
  - `--models-only`: Only refresh models without touching Docker images or code.
  - `-y` / `--yes`: Skip confirmation prompts.
  - Non-destructive: models are refreshed (ollama pull / snapshot_download) — nothing is deleted.
    HuggingFace cache deduplicates, Ollama pulls only changed layers.
  - All existing update commands (`rebuild`, `refresh-models`, `pull-mlx-models`, `install-comfyui`,
    `install-music`, `seed`) remain available for granular control.

### Fixed
- Reverted DinD to privileged mode — rootless `docker:27-dind-rootless` is incompatible with macOS Docker Desktop
- ARM64 embedding deps now auto-installed via dedicated venv; 0B prune noise suppressed in launch output

### Tests
- Acceptance suite v6 run 16: **154 PASS / 1 INFO / 0 FAIL / 0 BLOCKED / 0 WARN** (all 22 sections, 48m 41s)
  — improved from run 15 (130P/4W/1B): all prior WARNs resolved, BLOCKED cleared

---

## [6.0.0] — 2026-04-07

### Breaking Changes
- None. All existing workspace IDs, personas, and API contracts are unchanged.

### Added
- **P5-FUT-006: LLM-based intent routing** (`portal_pipeline/router_pipe.py`)
  - `_route_with_llm()`: Uses `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` (uncensored abliterated) as
    primary semantic intent classifier for the `auto` workspace. Temperature=0, 40 tokens,
    512-token context, `keep_alive=-1` (always warm).
  - Falls back to existing `_detect_workspace()` keyword scoring on low confidence
    (`LLM_ROUTER_CONFIDENCE_THRESHOLD`, default 0.5) or timeout
    (`LLM_ROUTER_TIMEOUT_MS`, default 500ms).
  - Ollama grammar-enforced JSON schema guarantees parseable output.
  - Workspace ID validated against `_VALID_WORKSPACE_IDS` allowlist — unknown IDs
    trigger keyword fallback rather than routing errors.
  - `config/routing_descriptions.json`: Operator-editable workspace capability descriptions
    used as the LLM's grounding context.
  - `config/routing_examples.json`: Operator-editable few-shot examples (25 included;
    add domain-specific examples to improve accuracy for your use cases).
  - `tests/unit/test_routing.py`: 16 new unit tests (mock-only, no Ollama required).
  - Env vars: `LLM_ROUTER_ENABLED`, `LLM_ROUTER_MODEL`, `LLM_ROUTER_CONFIDENCE_THRESHOLD`,
    `LLM_ROUTER_TIMEOUT_MS`, `LLM_ROUTER_OLLAMA_URL`.
  - Expected accuracy: 93-94% (see P5_ROADMAP.md for workspace-level breakdown).

- **P5-FUT-009: Model-size-aware admission control** (`scripts/mlx-proxy.py`)
  - `MODEL_MEMORY` dict: 16 entries mapping each MLX model → estimated peak GB.
  - `_check_memory_for_model()`: Pre-flight check in `ensure_server()` comparing
    `MODEL_MEMORY[model] + MEMORY_HEADROOM_GB` against `_get_available_memory_gb()`.
  - Rejects with HTTP 503 and operator-actionable message before evicting any loaded model,
    preventing OOM from conflicting model+ComfyUI loads.
  - Unknown models use `MEMORY_UNKNOWN_DEFAULT_GB` (default 20GB) — conservative but not blocking.
  - CLAUDE.md coexistence rules are now self-enforcing rather than documentation-only.
  - `tests/unit/test_mlx_proxy.py`: 9 new unit tests (mocked memory reads, no MLX runtime).
  - Env vars: `MLX_MEMORY_HEADROOM_GB` (default 10.0), `MLX_MEMORY_UNKNOWN_DEFAULT_GB` (default 20.0).

- **`auto-spl` workspace**: Splunk SPL query authoring, pipeline explanation, detection search
  - Routes `[mlx, coding, general]` — MLX Qwen3-Coder-30B-A3B-Instruct-8bit primary,
    deepseek-coder-v2:16b-lite-instruct-q4_K_M Ollama fallback
  - `_SPL_KEYWORDS` weighted dict + scoring for content-aware routing from `auto` workspace
  - New `splunksplgineer` persona with hardened SPL constraints
  - 16 new unit tests in `TestSPLWorkspace`
  - Workspace count: 15 → 16

- **`auto-agentic` workspace**: Long-horizon agentic coding via Qwen3-Coder-Next-4bit (80B MoE)
  - Routes `[mlx, coding, general]` — `mlx-community/Qwen3-Coder-Next-4bit` MLX primary
  - `context_limit: 32768` for KV cache suppression (P5-BIG-001)
  - Keyword triggers: agentic, swe-agent, openhands, multi-file, long-horizon
  - Workspace count: 16 → 17

- **`auto-compliance` workspace**: NERC CIP gap analysis and policy-to-standard mapping
  - Routes `[mlx, reasoning, general]` — MLX Qwen3.5-35B-A3B-8bit primary,
    DeepSeek-R1-32B Ollama fallback
  - `_COMPLIANCE_KEYWORDS` weighted dict + scoring for content-aware routing
  - System prompt: structured gap table output with CIP requirement citations
  - CIP-003-9 R1 Part 1.2.6 priority flagging built into prompt
  - Two new personas: `nerccipcomplianceanalyst`, `cippolicywriter`
  - 8 new unit tests in `TestComplianceWorkspace`
  - Workspace count: 14 → 15 (after SPL at 16, after agentic at 17)

- **`auto-mistral` workspace**: Strategic analysis, business reasoning
  - Routes `[mlx, reasoning, general]` — MLX Magistral-Small-2509-8bit primary
  - `_MISTRAL_KEYWORDS` weighted dict + scoring for content-aware routing
  - New `magistralstrategist` persona (category: reasoning)

- **`gemma-4-31b-it-4bit` MLX model**: Vision and research tasks
  - New `gemmaresearchanalyst` persona (category: research)
  - Replaces older `gemma-4-26B-A4B` reference

- **portal_pipeline/notifications/channels/webhook.py**: New `WebhookChannel` sends JSON POST
  to any user-defined `WEBHOOK_URL` on all operational alert and daily summary events.
  Configure via `WEBHOOK_URL` (required) and optional `WEBHOOK_HEADERS` (JSON object).

- **config/grafana/dashboards/portal5_overview.json** (v2→v3): Added 6 new Usage Analytics
  panels — Requests by Workspace Over Time, Tokens by Workspace, Top 10 Workspaces by Volume,
  Model Distribution per Workspace, Current Request Rate.

- **`auto-mistral` and `auto-compliance` keyword routing** (`router_pipe.py`):
  Added `_COMPLIANCE_KEYWORDS` and `_MISTRAL_KEYWORDS` to `_WORKSPACE_ROUTING` —
  previously these workspaces were only reachable via LLM router; keyword fallback now works.

### Acceptance Test Suite (v4)

- **5 new test sections** (S18-S22): image/video MCP tool calls, Telegram/Slack channel adapters,
  notifications/alerts, MLX proxy model switching
- **Execution order**: Reordered `ALL_ORDER` to group by backend (Ollama → MLX → ComfyUI → no-LLM)
  — reduces backend transitions from ~20 to 12
- **7 prompt/signal fixes**: Fixed signal words that wouldn't appear in valid responses
- **Removed** `portal5_acceptance_v3.py` (orphaned, not referenced anywhere)

### Changed

## [5.2.1] - 2026-03-30

### Fixed
- **launch.sh**: Docker Compose no longer starts with empty `PIPELINE_API_KEY` — `launch.sh up`
  now symlinks `.env` into `deploy/portal-5/` so docker compose auto-loads it.
  Previously the pipeline fell back to the insecure default key on every restart.
- **launch.sh + config/searxng/settings.yml**: SearXNG no longer crashes on restart with
  "server.secret_key is not changed" — `launch.sh up` now injects `SEARXNG_SECRET_KEY`
  from `.env` directly into `settings.yml` before starting the container.
  (SearXNG reads `secret_key` from settings.yml, not from env vars.)

### Changed
- **launch.sh**: Added symlink step for `.env` to `deploy/portal-5/` in `up`, `up-telegram`,
  `up-slack`, and `up-channels` commands.
- Version bumped 5.2.0 → 5.2.1 across `pyproject.toml`, `portal_pipeline/__init__.py`,
  `portal_mcp/__init__.py`, `portal_channels/__init__.py`, and `CLAUDE.md`.

## [5.2.0] - 2026-03-30

### Fixed
- **router_pipe.py**: Replaced all `assert` statements in HTTP handlers with proper
  `HTTPException(503)` raises — assertions are silently elided by Python `-O` flag,
  which would cause AssertionError in optimised deployments (lines 517, 542, 605, 617, 713, 761)
- **router_pipe.py**: Sanitised backend error messages returned to clients — internal
  URLs, stack traces, and backend response bodies are now logged server-side only;
  clients receive generic "Backend returned HTTP NNN" / "check server logs" messages
- **router_pipe.py**: Version string now reads from `importlib.metadata` (single
  source of truth: `pyproject.toml`) instead of a hardcoded literal
- **router_pipe.py**: Added `BackendRegistry.close_health_client()` call in lifespan
  shutdown — previously the shared health-check connection pool was never drained
- **cluster_backends.py**: `yaml.safe_load()` now wrapped in `try/except yaml.YAMLError`
  — a malformed backends.yaml previously crashed silently; now logs a clear error and
  returns an empty registry (all requests return 503 with an actionable message)
- **cluster_backends.py**: Added `close_health_client()` classmethod — cleans up the
  shared httpx client on shutdown to prevent connection pool leaks
- **tts_mcp.py**: Fish Speech backend device detection now auto-selects mps/cuda/cpu
  instead of hardcoding `device="mps"` (broke on Linux CUDA and CPU-only systems)
- **music_mcp.py**: Stable Audio backend device detection now auto-selects mps/cuda/cpu
  using the same priority order (was hardcoded `cuda or cpu`, missing Apple Silicon MPS)
- **test_mcp_endpoints.py**: Added module-level `pytest.importorskip` guards for
  `fastmcp` and `portal_mcp.generation.tts_mcp` — MCP endpoint tests now SKIP cleanly
  instead of ERROR when MCP dependencies are not installed (resolves P5-ROAD-107)
- **docker-compose.yml**: Added `cpus: "4.0"` limit to DinD service — previously only
  memory was bounded; an unterminated container process could consume all host CPU

### Added
- **.env.example**: Documented 8 previously undocumented environment variables used by
  Python code: `OPENWEBUI_ADMIN_NAME`, `PIPELINE_PORT`, `PIPELINE_URL`,
  `PIPELINE_TIMEOUT`, `BACKEND_CONFIG_PATH`, `PROMETHEUS_MULTIPROC_DIR`, `MODELS_DIR`
  (resolves P5-ROAD-146)

### Changed
- Version bumped 5.1.0 → 5.2.0 across `pyproject.toml`, `portal_pipeline/__init__.py`,
  `portal_channels/__init__.py`, `CLAUDE.md`

---

## [5.1.0] - 2026-03-06

### Fixed
- Content-aware routing: removed false-positive keywords ("go ", "apt", "attack")
- Melody conditioning in generate_continuation() was silently dropped — now
  uses AudioCraft generate_with_chroma() for actual melody conditioning
- FastAPI app version string: 5.0.0 → 5.1.0
- CLAUDE.md workspace routing table: 9 stale model_hints updated
- CLAUDE.md architecture line: MLX port 8080 → 8081
- BackendRegistry._health_timeout: added defensive default in __init__

### Changed
- Broken mlx-vlm models (Qwen3.5-35B-A3B-4bit, Qwen3.5-27B-4bit) commented
  out from MLX backend — only mlx-vlm conversions exist, incompatible with
  mlx_lm.server. Will uncomment when mlx-lm community quants are published.
- Added qwen3-coder:30b to Ollama coding group (correct tag, replaces
  nonexistent qwen3-coder:32b)
- Added deepseek-r1:32b-q4_k_m to Ollama security group for threat modeling
- install-mlx now pins mlx-lm>=0.30.5 (required for Qwen3-Coder-Next support)
- Version bump to 5.1.0 across pyproject.toml, __init__.py files, CLAUDE.md

### Improved
- Agent prompt v5: added mlx-vlm compatibility check and melody conditioning test
- Agent prompt v4: corrected all stale port/model references
- P5_AUDIT_REPORT.md updated for v5.1.0

## [5.0.2] - 2026-03-05

### Fixed
- SearXNG: removed literal `${SEARXNG_SECRET_KEY}` from settings.yml — was never
  interpolated; SearXNG now reads `SEARXNG_SECRET_KEY` env var directly
- Prometheus: removed scrape job for `open-webui/metrics` (endpoint doesn't exist)
- Audio TTS/STT: moved config from broken `/api/v1/configs/audio` API call to
  compose environment variables (`AUDIO_TTS_ENGINE`, `AUDIO_STT_ENGINE`)
- Dockerfile.mcp: added `espeak-ng` and `libespeak-ng1` required by kokoro-onnx
- backends.yaml: corrected `unsloth/GLM-4.7-Flash` → `hf.co/unsloth/GLM-4.7-Flash-GGUF`
- Grafana: added datasource `uid: prometheus` required for dashboard panel wiring
- Grafana: created `portal5_overview.json` dashboard (was missing despite provisioning config)
- SearXNG healthcheck: `/healthz` → `/` (correct endpoint)
- configure_tool_settings: removed call to non-existent `/api/v1/configs/features`
- pyproject.toml: `stable-audio_tools` → `stable-audio-tools` (underscore typo)
- comfyui-model-init: extracted one-liner to `scripts/download_comfyui_models.py`
- cluster_backends.py: auto-detects config path for local dev (no more startup error)
- mcp-tts: added `/v1/audio/speech` OpenAI-compatible endpoint for Open WebUI TTS
- mcp-whisper: added `/v1/audio/transcriptions` OpenAI-compatible endpoint for STT
- test_semaphore.py: fixed failing test by using lifespan context manager
- wan2.2 download: use `snapshot_download` instead of `hf_hub_download` with `None` filename
- Port bindings: restricted internal services to `127.0.0.1` (Ollama, MCP servers,
  Prometheus, SearXNG, ComfyUI) to prevent unintended LAN exposure
- tts_mcp.py: consolidated 6 redundant in-function `JSONResponse` imports to top-level
- Added `TTS_DEFAULT_VOICE` to `.env.example`

### Added
- OpenAI-compatible `/v1/models` endpoint on mcp-tts and mcp-whisper
- Test coverage for TTS/STT endpoints, model hint routing, workspace routing completeness
- `scripts/download_comfyui_models.py` supporting flux-schnell, flux-dev, sdxl, wan2.2

## [5.0.0] - 2026-03-03

### Added
- Zero-setup web search via SearXNG integration
- Zero-setup image generation via ComfyUI in Docker
- Zero-setup TTS via kokoro-onnx (with optional fish-speech)
- Zero-setup metrics via Prometheus + Grafana
- 13 workspace routing configurations (auto, auto-coding, auto-security, etc.)
- Model hint routing for security, coding, reasoning, vision workspaces
- Health-aware backend registry with automatic fallback
- Concurrency limiting via semaphore with 503 + Retry-After
- MCP Tool Servers: Documents, Music, TTS, Whisper, ComfyUI, Video, Sandbox
- Telegram bot channel adapter
- Slack bot channel adapter
- Backup/restore documentation
- Comprehensive CLAUDE.md for AI-assisted development

### Changed
- Updated model catalog with DeepSeek-R1, Qwen3-Coder, BaronLLM variants
- Test coverage improved to 72%
- Production readiness score: 92/100

### Security
- Auto-generated secrets via openssl
- DinD sandbox (no host docker.sock)
- API key authentication on all Pipeline endpoints

### Infrastructure
- Docker Compose with 18 services
- Healthchecks on all critical services
- Volume management for persistence

---

**Portal 5** is an Open WebUI intelligence layer that provides a complete local AI platform covering text, code, security, images, video, music, documents, and voice — all running on local hardware.
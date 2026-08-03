# PUNCHLIST — Next-Run Task List (2026-08-02)

Generated at the close of the Phase-0 oMLX re-evaluation + context-inject fix
session. Ordered by leverage. Each item has What / Why / Where / Acceptance so a
fresh run can pick it up cold. Evidence paths are cited inline.

**Session output landed (uncommitted at HEAD 0cb2ac61):**
- `tests/benchmarks/bench_omlx_v3.py` — Phase-0 gate harness (all six gates PASS)
- `tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md` + 10 gate JSONs
- `OMLX_DECISION.md` v3 section; `portal_wiki/canonical/unit-p5-roadmap-p5-fut-013-...md`
  updated (P5_ROADMAP.md re-rendered by the wiki loop)
- context-inject fix: `config.py` (5 WorkspaceSpec fields), `config_validate.py`
  (+1 bool key), `test_config_schema.py` (regression test). Gates: 859 unit ✅,
  ruff ✅, `ci_local.sh` 2638 ✅.
- Environment: omlx 0.3.12→0.5.4 (`--with-grammar` + manual xgrammar rpath/RECORD
  patch); oMLX server RUNNING on :8085 (models: 3B/coder-30B-4bit/gemma-e4b-4bit/
  Qwen3.6-27B-oQ8-mtp w/ mtp_enabled:true); `~/.omlx/model_settings.json.phase0bak`
  backup exists; vendor debug patch lives in oMLX's `engine/batched.py`
  (wiped by any brew reinstall — harmless).

---

## A. Immediate (this week)

### A1. ✅ DONE (2026-08-02) — committed + live-verified end-to-end
- Commits: `6c0c7440` (Phase-0 artifacts), `b7e09c07` (schema fields),
  `b54113d9` (two latent contract failures found by the live probe:
  module-vs-instance `tool_registry` import masked by never-raises;
  `auto_writeback` category rejected by memory-server enum → now `fact` +
  provenance tag).
- Live proof on the rebuilt pipeline: writeback `stored`, recall `hit` with
  the injected block visibly consumed by the model ("Looking at the 'Relevant
  context from prior sessions'..."), rag dispatching (miss = empty KB),
  metrics flowing on :9099/metrics.
- **Residual tuning item:** first recall after idle can exceed the 1.5s
  `AUTO_CONTEXT_TIMEOUT_MS` (cold embedding server) and the tool circuit
  breaker then suppresses the immediate follow-up — both self-recover.
  Consider warming :8917 at pipeline startup or raising the timeout to ~3s.

### A2. ✅ DONE (2026-08-02) — Phase-0 leftovers
- Dead symlinks: 23 removed from `/Volumes/data01/omlx-models`.
- Upstream filings DRAFTED (not posted — public attribution):
  `tests/benchmarks/results/UPSTREAM_DRAFTS_omlx_20260802.md`
  (gemma grammar livelock; brew xgrammar patch gap). Post with
  `gh issue create -R jundot/omlx ...` when ready.
- Gate-6 probes: Qwen3-VL-32B vision **PASS** (auto-vision migratable);
  supergemma4 VLM-shaped **PASS** incl. tool_calls (P5-MLX-EVAL-005 retired
  on the oMLX path — redteam/purpleteam variants migratable);
  Phi-4-reasoning-plus **FAIL** (degenerate output, template mismatch —
  phi4stemanalyst stays on pool default). Details appended to the reeval MD.
- Housekeeping note: kill oMLX by PORT (`lsof -ti :8085`), never
  `pkill -f "omlx serve"` (process is `omlx-server`). Any `brew upgrade omlx`
  must re-verify `import xgrammar` + `GrammarCompiler initialized` log line.

---

## B. Phase 1 — Dual-backend integration (the big one; decision: PROCEED)

Full context: `OMLX_DECISION.md` §"Re-evaluation v3" +
`tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md` (scope guards).

### B1. ✅ DONE (2026-08-02) — Registry plumbing, no traffic shift
- `Backend` (`cluster_backends.py`): `type: "omlx"` (health → `/v1/models`),
  `health_path:` override, `priority:` (within-group ordering — the
  oMLX-primary/Ollama-fallback mechanism; all-zero = legacy shuffle),
  `aliases:` (canonical hint → engine-native id) + `resolve_model()`.
- `_inject_omlx_options` (`validation.py`): plain-OpenAI surface only
  (max_tokens/stream_options/temperature/top_p; no `options` sub-dict, no
  keep_alive). Dispatch at `handlers.py:920` + `non_streaming.py:306`.
- `router/backend_introspect.py`: `model_still_running(url)` seam replaces
  hardcoded `/api/ps` at 3 timeout sites (streaming ×2, non_streaming ×1);
  type resolved via lifespan registry singleton, unknown → legacy Ollama
  probe. oMLX semantic: reachable ⇒ busy, unreachable ⇒ down (admin-API
  loaded-state is B3 scope).
- `config/backends.yaml`: `omlx-local` registered in **holding group `omlx`**
  (no workspace_routing reference → tier-3 fallback only, no traffic shift).
  7 models with Phase-0 probe evidence; Phi-4 marked do-not-migrate.
- Guardrails honored: group named `omlx` NOT `mlx` (retirement guard
  `test_backend_registry_loads_all_groups` intact); 7 `unit-model-catalog-*`
  units + MODEL_CATALOG.md section created (parity test intact);
  `mlx_metadata`/`_MLX_PROXY_HEALTH_URL` still absent (3a0c58e guards intact).
- Gates: 873 unit ✅ (13 new in `tests/unit/test_omlx_backend.py`),
  ruff ✅, pipeline rebuilt (7/7 backends healthy incl. omlx-local),
  `smoke_stream.sh` ✅, `ci_local.sh` 2652 ✅.

### B2. NEXT — Shadow then shift, auto-coding first (NOT STARTED)
Resume notes — everything needed to pick this up:
- **Design decision made in B1:** engine selection is per-group
  `priority:` + per-model `aliases:` on backend entries; workspaces keep ONE
  `model_hint` (the GGUF tag), the oMLX entry for that group carries
  `aliases: {<gguf-hint>: <omlx-native-id>}` and higher priority. When oMLX
  is unhealthy, candidates fall to Ollama automatically with the existing
  `_hint_fallback` metric firing honestly.
- **Concrete first move:** add `group: coding` oMLX entry (same URL as
  omlx-local or fold into one entry per group — mirror the ollama-* pattern
  of one entry per group per engine), `priority: 10`,
  `aliases: {"qwen3-coder:30b-a3b-q4_K_M-ctx16k": "Qwen3-Coder-30B-A3B-Instruct-4bit",
  "laguna-xs.2:Q4_K_M-ctx64k": <laguna MLX id once downloaded>}`.
- **Hint-resolution check:** handlers resolve `model_hint in backend.models`
  BEFORE prioritize — must switch to `backend.resolve_model(hint)` so aliases
  match (B1 added the method; call sites are `handlers.py:~868-905` and
  `_prioritize_hinted_backend` at `handlers.py:104`). Then target_model =
  resolved native id.
- **Laguna prerequisite:** no Laguna MLX conversion is on disk (deleted in
  July cleanup) — download before aliasing the laguna variant.
- **Watch:** oMLX EnginePool + pipeline `keep_alive` warmup calls
  (`lifespan.py:183-261`) — warmup posts to `/api/generate` (Ollama-native);
  oMLX workspaces must skip Ollama warmup or get an oMLX warmup path
  (plain chat completion). Check `_LLM_ROUTER_OLLAMA_URL` usages.
- **Then:** ~1 week of real-use metrics comparison (Prometheus per-backend
  TTFT/TPS), then auto-vision (Gate-6 ✅) + auto-security migratable variants
  (supergemma4 ✅, redteam/purpleteam).
- **Security core migration (paired with B2):** 6 `/api/chat` call sites →
  `/v1/chat/completions` with configurable base URL:
  `blue.py:1304`, `exec_chain.py:4089/4445`, `refusal.py:38/120`,
  `drift_gate.py:313`, `agentic_blue_eval.py:288`, `core/__init__.py:167`,
  `intake.py:78` (the last two use `/api/generate`).
- **Acceptance:** parity-or-better live metrics; `smoke_stream.sh` green;
  per-model rollback = one-line YAML (delete the alias).

### B2. Shadow then shift — auto-coding first
- Route `auto-coding` (+ `laguna` variant — oMLX natively accelerates Laguna)
  to oMLX with Ollama as second candidate. Compare Prometheus TTFT/TPS per
  backend for ~1 week of real use. Then `auto-vision` (Gate-6 PASS) and
  `auto-security` migratable variants — including redteam/purpleteam
  (supergemma4 Gate-6 PASS on the VLM engine). Still excluded: Llama-family,
  phi4-reasoning (Gate-6 FAIL), qwen3-coder-next (unprobed).
- Migrate the 6 Ollama-native `/api/chat` call sites in security core
  (`blue.py:1304`, `exec_chain.py:4089/4445`, `refusal.py`, `drift_gate.py`,
  `agentic_blue_eval.py`) to `/v1/chat/completions` with configurable base URL.
- **Acceptance:** parity-or-better live metrics; `smoke_stream.sh` green; per-
  model rollback = one-line YAML.

### B3. Model management + ops
- `cli/models.py` omlx path (HF download → model dir); convert `-ctxNk` needs to
  oMLX profiles for migrated models; freeze new `ollama create` ctx variants.
- `launch.sh install-omlx` (brew) + launchd service (same pattern as
  mlx-speech/transcribe); `sync-config` emits oMLX model-dir/settings; reserve
  oMLX host-native port in `.env.example` (next free: 8933+).
- Migrate ONLY ~15 production primaries, NOT the 65-workspace bench fleet.
- Router model: stays on Ollama initially, OR dedicated always-grammar oMLX
  instance (gemma livelock needs an unconstrained→constrained transition that
  router-only workloads never produce — verified in Gate 4).
- **Do NOT migrate:** Llama-family models (tool output doesn't parse — Gate 3),
  phi4-reasoning (Gate-6 FAIL — degenerate output), qwen3-coder-next (GGUF
  sharded bug; MLX conversion deleted with the July cleanup — re-download and
  probe before deciding), gemma-4-abliterated E2B-qat (the other
  P5-MLX-EVAL-005 fine-tune — same VLM-shape theory as supergemma4 but
  unprobed; its conversion was also deleted).
- Version-pin omlx; upgrades gated through `bench_omlx_v3.py` + `smoke_stream.sh`.

### B4. Exploit the new capabilities
- Enable Lightning MTP per-model for coding/security primaries (acceptance
  varies by workload — oMLX data shows prose gains inconsistent; gate per
  workspace). Candidate: oQ an `auto-coding` MTP checkpoint (oMLX oQ can merge
  donor MTP heads for Qwen3.5/3.6 and Gemma-4).
- SpecPrefill + prefix cache for personas (static system prompts) and the tool
  loop — measure hop-2+ TTFT reduction (headline agentic-latency metric).
- Pin router + daily drivers; TTLs on bench models; memory guard sized for
  ComfyUI co-residency (`portal/modules/media/tools/_admission.py` budget table).
- Optional: raise `iogpu.wired_limit_mb` to 59392 (sudo, persistent) for
  30B+co-residency headroom (oMLX recommended; Phase 0 ran fine at the 47GB cap).

### B5. Re-decide full replacement (~4 weeks of dual run)
- Retire Ollama to GGUF-only-straggler duty, or keep dual permanently (also the
  Linux/NVIDIA portability story). Data, not vibes.

---

## C. Review-derived backlog (from the 2026-08-02 top-down review, ordered)

1. **RAG/memory scope reconciliation** (decision doc, not code): rag_mcp
   (full LanceDB hybrid RAG) + memory_mcp duplicate declared out-of-scope OWUI
   features. Bless "agent-toolable vs chat-attached" in a WHY unit or retire.
   Note: after A1, auto-daily actively uses the memory path — reconciliation
   should reflect that reality. Also: memory_mcp is single-user hardcoded
   (`DEFAULT_USER = "default"`) — flag before any multi-user OWUI.
2. **Dead-weight GC pass:** tool_preselect README false-integration claim +
   six always-zero collectors (`metrics.py:223-261`); `_stream_with_secondary_
   chain` + dead handler branches; `_tool_workspace_strip` /
   `_stream_content_yielded_total` dead collectors; `doc_ledger.py` + validate
   check AK (empty no-op) + its HOWTO references; stale monolith-era docstring
   line refs across router/; 73 committed artifacts under security `results/`.
3. **Verify blueteam variant metadata keys** — `auto-security::blueteam-
   orchestrated` (`expert_model`/`reasoning_model`/`tool_model`) and
   `::blueteam-council` (`council_models`…) are not WorkspaceSpec fields;
   variants are free-form so nothing drops them, but confirm a live consumer
   exists (security blue orchestration) or they are drift litter. (Found by
   the item-#1 schema sweep, 2026-08-02.)
4. **Streaming consolidation** (after B2): three reasoning-promotion
   implementations → one; substring protocol sniffing → parsed framing;
   deduplicate the two timeout-recovery blocks. Keep `smoke_stream.sh` green
   at every step.
5. **Persona/wiki GC:** bench personas → separate registry (34/138 are
   creative_coder clones); drop or consume `preferred_models` (89% carry it,
   nothing reads it); prompts.chat imports review (30 files); wiki orphan
   units (453 of 996) + 37 `unit-claude-*` mirrors; retire AK/doc_ledger
   (empty) — pairs with item 2.
6. **mitre/detections depth or honest relabel:** ~73 techniques vs advertised
   ATT&CK+D3FEND+CWE; two ATT&CK stores coexist (mitre_mcp embedded dict vs
   siem/mitre_attack_techniques.json, 697); two SPL validators
   (`growth_loop.py:145` vs `detections_mcp.py:175`) — keep the better one.
7. **Security module repositioning:** decide bench-platform vs production;
   then make layout + validation mass (54% of 70 checks) reflect it.

## D. Explicit do-nots
- Do NOT revive the retired mlx-proxy (regression guards; archived 3a0c58e).
- Do NOT enable `PORTAL_EMERGENT` / Stage-2 live actuation (deliberate gates).
- Do NOT clear/overwrite bench checkpoints without a timestamped backup
  (CLAUDE.md non-negotiable; applies to `tests/benchmarks/results/` sweeps too).
- Do NOT add `gemma4:*-mlx` Ollama tags to backends.yaml (P5-MLX-EVAL-002 gates).
- Do NOT migrate Llama-family models to oMLX until tool output parses (Gate 3).
- Do NOT treat `preferred_models` as selecting a served model (advisory only).

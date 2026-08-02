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

### A1. Commit session work + live-verify context_inject end-to-end
- **What:** commit the landed diff (two logical commits: `test(benchmarks): oMLX
  v3 Phase-0 re-evaluation — all gates pass` and `fix(pipeline): restore
  WorkspaceSpec context-injection fields dropped by schema`); then rebuild the
  pipeline image and live-probe auto-daily.
- **Why:** unit proof is done, but the pipeline container (image 2026-07-30)
  runs pre-fix code; the feature has never fired live. CLAUDE.md pre-testing
  rule: no stale-image conclusions.
- **Where:** `portal/platform/inference/router/context_inject.py`,
  `handlers.py:724-726` (Phase 8 calls), `non_streaming.py:455-458` (writeback).
- **How:** `docker compose build portal-pipeline && docker compose up -d
  portal-pipeline`; send an auto-daily chat containing "remember that my
  callsign is BlueFox-7"; then a second session asking "what is my callsign?";
  confirm `recall`/`kb_search`/`remember` dispatches in pipeline logs and
  `_auto_context_inject_total{source="memory|rag|writeback"}` increments on
  :9099/metrics.
- **Watch:** auto-daily behavior change is INTENTIONAL but real — memory/RAG
  blocks now appear in its system context. If injection misbehaves live, the
  kill switch is `AUTO_MEMORY_ENABLED=false` / `AUTO_RAG_ENABLED=false` env on
  the pipeline (no revert needed).
- **Effort:** ~1h including rebuild.

### A2. Phase-0 leftovers (cheap, do before Phase 1)
- **Dead symlinks:** 24 dangling symlinks in `/Volumes/data01/omlx-models`
  (targets in cleaned `~/.cache/huggingface`). Remove or re-point; they are
  inert but pollute discovery. ~10 min.
- **File upstream with oMLX:** (a) gemma-4-e4b grammar livelock —
  unconstrained→constrained request sequence emits infinite whitespace,
  100% reproducible, self-recovering (curl repro in session log); (b) xgrammar
  brew post-install gap — `patch_xgrammar` did not leave a working install
  (jundot/omlx#1005 follow-up: RECORD missing + rpath absent after
  `brew reinstall --with-grammar`; manual fix steps in the results MD).
- **Gate-6 probes (opportunistic, models already on disk):**
  - `Qwen3-VL-32B-Instruct-8bit` on oMLX VLMEngine vs production `auto-vision`
    GGUF — decides whether vision migrates in Phase 1.
  - `supergemma4-26b-abliterated-multimodal-mlx-4bit` (P5-MLX-EVAL-005 says no
    working text-only MLX conversion — but it is VLM-shaped and oMLX serves
    VLMs; if it loads, auto-security redteam variants become migratable).
  - `Phi-4-reasoning-plus-MLX-4bit` vs the GGUF crash refugee
    (P5-MODEL-PHI4REASONING-001) — could un-block the phi4stemanalyst persona.
  - Acceptance: each probe = load via VLM/Batched engine + 3 standard prompts +
    tool probe; record in `tests/benchmarks/results/omlx_v3_gate6_*.json`.
- **Housekeeping:** `~/.omlx/model_settings.json` currently `mtp_enabled:true`
  (matches backup; fine). Any `brew upgrade omlx` MUST re-verify
  `import xgrammar` + `GrammarCompiler initialized` log line (see results MD
  anomaly #1). Kill oMLX by PORT (`lsof -ti :8085`), never `pkill -f "omlx
  serve"` (process is `omlx-server`).

---

## B. Phase 1 — Dual-backend integration (the big one; decision: PROCEED)

Full context: `OMLX_DECISION.md` §"Re-evaluation v3" +
`tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md` (scope guards).

### B1. Registry plumbing (no traffic shift)
- Add `type: "omlx"` to `cluster_backends.py` (health via `/v1/models`; do NOT
  resurrect the retired `mlx-apple-silicon` type or `mlx_metadata` — regression
  guards in `tests/unit/test_pipeline.py` must stay green). Generalize
  `health_url` to an optional per-backend YAML override.
- Per-model optional `backend:` field in `backends.yaml` so candidate chains
  span engines (oMLX primary → Ollama fallback using existing failover).
- Replace ollama-only option injection (`handlers.py:920`,
  `non_streaming.py:306`) with per-type injection; oMLX requests get
  `stream_options.include_usage` only.
- `BackendIntrospector` seam for the `/api/ps` timeout-disambiguation
  (`streaming.py:475/978`, `non_streaming.py:497`, `monitor.py`): Ollama impl =
  `/api/ps`; oMLX impl = admin active-models API, else local in-flight tracking.
- **Acceptance:** unit tests for type parsing/health/candidate selection;
  `pytest tests/unit -q` green; no production traffic routed to oMLX yet.

### B2. Shadow then shift — auto-coding first
- Route `auto-coding` (+ `laguna` variant — oMLX natively accelerates Laguna)
  to oMLX with Ollama as second candidate. Compare Prometheus TTFT/TPS per
  backend for ~1 week of real use. Then `auto-security` migratable variants
  (not the two GGUF-only fine-tunes, not Llama-family).
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
  the two P5-MLX-EVAL-005 fine-tunes (until Gate-6 VLM probe), phi4-reasoning
  (until Gate-6 probe), qwen3-coder-next (GGUF sharded bug; MLX exists — probe).
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

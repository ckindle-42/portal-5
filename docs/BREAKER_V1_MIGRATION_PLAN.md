# Breaker v1.0 — Migration, Rename & Trim/Refactor Plan

Status: **planning blueprint only — not executed.** Portal 5 stays on `main` until the
operator gives explicit go-ahead. Every path, count, service name, LaunchAgent label and
config key below was audited against the live repo at HEAD `729e219d5` (2026-11-24).
Where the dispatch brief assumed something the repo contradicts, the correction is in
§1.3, not silently folded in.

Breaker v1.0 is a **clean, trimmed, refactored cut into a brand-new blank `breaker`
repository** — not a copy of the Portal 5 tree. The migration is therefore three
operations in one: (a) selective copy of the living product, (b) a mechanical
`portal*` → `breaker*` rename across code, Docker, launchd, env, OWUI presets and
metrics, and (c) leaving the dead weight behind.

---

## 1. Executive Scope & Target State

### 1.1 What Breaker v1.0 IS

A local-first, fully-local AI platform behind one Open WebUI interface, extended through
its Pipeline server — the same architecture Portal 5 runs today, minus the historical
accumulation:

| Capability | Backing subsystem (post-rename paths) |
|---|---|
| Open WebUI front end | `deploy/breaker/docker-compose.yml` `open-webui` (image `breaker-open-webui:v0.13.0-hardened`, built from `deploy/breaker/Dockerfile.openwebui`) |
| Inference Pipeline (stateless router) | `breaker/platform/inference/router_pipe.py` (`:9099`, container `breaker-pipeline`) |
| Dual-engine routing: oMLX (MLX, `:8085`) + Ollama (GGUF, `:11434`) | `breaker/platform/inference/` + `config/backends.yaml` (sacred operator file, unchanged role) + `config/breaker.yaml` (renamed from `config/portal.yaml`) |
| Universal Zero-Signature Corporate/OT Threat Hunter | `breaker/modules/security/` (333 files, ~120.6k lines incl. `core/hunt/`), `scripts/hunt_bed/` (19 files), lab corpora in `scripts/lab/splunk_setup/` |
| Compliance Engine (NERC CIP register, reading-in-conversation) | `breaker/modules/compliance/` (104 files, ~42k lines) + `scripts/compliance/` + `scripts/validation/compliance_*.py` |
| Media: image/video/music, TTS, voice clone, transcription | `breaker/modules/media/`, host MFLUX (`:8933`), video-MLX (`:8935`), ACE-Step music (`:8912`), whisper (`:8915`), TTS (`:8916`), MLX speech (`:8918`), MLX transcribe (`:8924`) |
| Documents / RAG / Memory / Sandbox / CAD | `breaker/modules/{documents,general}` + platform retrieval/memory/embedding; services: documents (`:8913`), RAG (`:8921`), memory (`:8920`), sandbox+DinD (`:8914`), CAD render (`:8926`) — note there is no `portal/modules/rag/` directory; RAG tooling lives in the RAG MCP service + `portal/platform/retrieval/` |
| Observability | Prometheus (`:9090`, `breaker-prometheus`) + Grafana (`:3000`, `breaker-grafana`) + `config/prometheus/prometheus.yml` + 8 dashboards in `config/grafana/dashboards/` + `deploy/grafana/` |
| Stage 5 Conversational OWUI UAT | `tests/qat/` (`uv run python -m tests.qat --stage uat`) — human-grade acceptance journeys with output-hygiene and verified-serving-model gates |
| Channel adapters | Telegram/Slack compose services → `breaker-telegram` / `breaker-slack`, package `breaker_channels/` |

Full MCP/host fleet stays exactly as reserved in `.env.example` (roster authority:
`config/portal.yaml` → `config/breaker.yaml` `mcp_fleet` + `host_jobs`; port map in
CLAUDE.md "All Ports Are Reserved"); only the names change, never the numbers.

### 1.2 Hard design principles carried over (Portal 5 + OrcaCyber lessons)

1. **100% blind, zero-signature hunting.** The hunter never sees key material:
   out-of-band keys live on `/Volumes/data01/hunt_keys/` (written by
   `scripts/hunt_bed/keys_*.py`, consumed by `scripts/hunt_bed/prove_universal_blind.py`
   `--keys-dir`, default already that path). Ingest is byte-faithful and label-free
   (`scripts/hunt_bed/ingest_native.py`). No label ever enters the corpus the hunter
   reads.
2. **Canonical TA sourcetypes.** Splunk ingest uses canonical sourcetypes via
   `scripts/hunt_bed/ingest_canonical.py`; the `hb_*` index family (see §4.7) is the
   only hunt data namespace and is carried over untouched.
3. **Out-of-band keys.** Key JSON on `/Volumes/data01/hunt_keys/`, hunt knowledge in a
   DuckDB store (`PORTAL_HUNT_KNOWLEDGE_STORE` → `BREAKER_HUNT_KNOWLEDGE_STORE`), never
   in the repo.
4. **Orca-style Compliance data truth.** Compliance answers are graded against source
   data, not format: `scripts/validation/compliance_data_truth.py`,
   `scripts/validation/compliance_currency.py`, `scripts/compliance/truth/`. The
   `IN_SERVICE=False` pre-service downgrade (FAIL→WARN) stays until the V6 ACME
   acceptance gate passes (see §5.4).
5. **Human-grade conversational UAT with verified serving-model gates.**
   `tests/qat/` Stage 5 (`--stage uat`) plus `tests/wfe/settings_audit.py`
   (`uv run python -m tests.wfe.settings_audit [--behavioral]`) — baked-context,
   persona-pin and template-contract verification before any human journey counts.
6. **Everything CLAUDE.md calls sacred stays sacred**: `config/backends.yaml` is the
   only operator scaling file; the Pipeline stays stateless; MCP servers stay
   independent; Open WebUI source is never modified; arm64-native everywhere.

### 1.3 Audit corrections — brief assumptions vs. the actual repo

The dispatch brief named four things that do not match the tree. These are findings from
the audit, and each changes a line of the plan:

| Brief said | Repo reality (verified) | Plan consequence |
|---|---|---|
| `tests/uat_adaptive/` to trim | **No such directory.** The retired suites are `tests/uat/` + `tests/acceptance/` (already gone; `tests/qat/README.md` records their retirement). What remains dated: `tests/UAT_*.md`, `tests/uat_corpus/` (2 files), `tests/PORTAL5_*_EXECUTE_*.md` | Trim list uses the real paths (§3.3) |
| `tests/benchmarks/` is dead legacy | **Partially load-bearing.** `portal/modules/security/core/_data.py` (lines 30–99) and `portal/modules/security/core/matrix.py` (lines 479–551) import `bench_lab_exec` and `tests.benchmarks.bench.notify` at runtime; `pyproject.toml` `[tool.pytest.ini_options]` puts `tests/benchmarks` on `pythonpath` | Cannot drop wholesale. Split: keep `bench_lab_exec.py` + `bench/notify.py` (+ their imports), drop the one-off probes (§3.3) |
| `lab_vulhub_fleet_sweep.py` to wire as the continuous hunter proof harness | **No such file anywhere in the repo** (only the brief mentions it). The Vulhub capture lane that exists is `scripts/hunt_bed/lab_purple_capture.py` (controlled live Vulhub purple-team capture, Splunk ingest via `ingest_native.py`, keys to `/Volumes/data01/hunt_keys/`) | §5.5 wires `scripts/hunt_bed/lab_purple_capture.py` as the continuous-hunter proof harness; if the operator meant a different planned script, that is a brief correction, not a repo gap |
| "obsolete v6.1.0 docs" | **No file or doc names `v6.1.0`.** Closest real artifacts: compliance V6 closeout family — `scripts/verify_compliance_v2_closeout.py`, `scripts/verify_compliance_v6_closeout.py`, `tests/qat/scenarios.py` `IN_SERVICE=False` "pending the V6 ACME" annotations | Trim list targets the actual dated closeout/decision docs (§3.3) |

---

## 2. Source-tree audit (what exists, with counts)

All counts from HEAD `729e219d5`, taken 2026-11-24.

```
portal/                      737 .py files, 240,407 lines
  portal/platform/           181 .py files,  48,203 lines
  portal/modules/security/   333 .py files, 120,626 lines
  portal/modules/compliance/ 104 .py files,  42,017 lines
  portal/modules/orchestration/ 30 files,   15,161 lines
  portal/modules/cad/          9 files,    2,892 lines
  portal/modules/media/       10 files,    2,429 lines
  portal/modules/research/     7 files,    2,079 lines
  portal/modules/binary_research/ 18 files, 1,806 lines
  portal/modules/documents/    3 files,    1,185 lines
  portal/modules/coding/      3 files,    1,173 lines
  portal/modules/eval/         8 files,    1,013 lines
  portal/modules/data/         5 files,      426 lines
  portal/modules/vulnintel/    5 files,      452 lines
  portal/modules/netforensics/ 5 files,      243 lines
  portal/modules/icsot/        5 files,      285 lines
  portal/modules/detection/    5 files,      309 lines
  portal/modules/general/      3 files,       47 lines
portal_wiki/    canonical 606 files · archive 1,056 files · proposed 40 files · 5 top-level files
portal_mcp/     filesystem + scrapling adapters
portal_channels/ telegram + slack adapters
scripts/        167 top-level .py + lib/ lab/ hunt_bed/ compliance/ validation/ proofs/
                prove_then_scale/ seat_screen/ omlx/ _archive/
tests/          673 .py files total
tests/unit/     331 .py files   tests/qat/  25 files   tests/wfe/ 224 files
tests/security/ 96 files        tests/fixtures/ 191     tests/data/ 73
tests/benchmarks/ 78 files, ~17,975 lines (partially load-bearing, §1.3)
config/         portal.yaml 3,443 lines · backends.yaml 1,153 · bench_workspaces.yaml 757
                personas/ 110 production YAMLs + bench/ 2 · grafana/ prometheus/ compliance/ security/
deploy/         portal-5/ (compose yml 1,025 lines + lab yml + Dockerfile.openwebui)
                launchd/ 13 plists · grafana/ · root/ · _archive/
docs/           236 files (155 root entries + hunt/22 test_trim/12 engine_research/5 …)
coding_task/    98 files (lane briefs, FINDING_*, REPORT_*, CONTRACTS/, scratch/)
launch.sh       666 lines
```

Renaming surface: **842 files** in the repo currently contain `portal5` or `portal-5`
(Python, shell, YAML, JSON, plist, TOML, Markdown).

---

## 3. Keep vs. Trim/Drop inventory

### 3.1 KEEP — core product (copy into `breaker/`, then rename per §4)

| Path | Why | Size (audited) |
|---|---|---|
| `portal/platform/` → `breaker/platform/` | Pipeline router, CLI, registry, memory/retrieval/embedding/wiki host services | 181 files / 48,203 lines |
| `portal/modules/{security,compliance,media,coding,documents,cad,research,binary_research,vulnintel,icsot,detection,data,netforensics,orchestration,general,eval}` | Product modules. Note: there is no `portal/modules/rag/` directory — RAG tooling lives in the RAG MCP service + `portal/platform/retrieval/`; `eval/` (8 files, bench personas) copies only if eval lanes carry over | see §2 table |
| `portal_mcp/`, `portal_channels/`, `portal_wiki/` (→ `breaker_mcp/`, `breaker_channels/`, `breaker_wiki/`) | Filesystem/scrapling MCP adapters, Telegram/Slack adapters, wiki engine | small; wiki canonical 606 units |
| `config/portal.yaml` → `config/breaker.yaml` | Workspace + MCP fleet source of truth (3,443 lines) | sacred-adjacent: rename keys only, never values/ports |
| `config/backends.yaml` | Operator cluster-scaling file — copied **byte-identical** | 1,153 lines |
| `config/personas/` | Persona roster (110 production YAMLs + `bench/` 2 — bench stays out of production roster) | 112 YAMLs |
| `config/{bench_workspaces.yaml, engine_contract.yaml, arm_job_env_allowlist.yaml, arm_jobs/, challenge_classes.yaml, chat_templates/, compliance/, documents/, grafana/, inference/, modelfiles/, ollama_modelfiles/, prometheus/, routing_descriptions.json, routing_examples.json, searxng/, security/, spine_surfaces.yaml, complexity_budget.yaml, tool_catalog.yaml, cloudflared/, lab_targets.yaml, model_card_expectations.yaml, ollama_direct_allowlist.yaml, orchestration_arm.yaml, owui_tool_servers.yaml, attack_image_contract.json}` | Runtime config the product reads | — |
| `deploy/portal-5/` → `deploy/breaker/` | Compose stack (24 services, 12 named volumes, 1,025 lines) + lab compose (8 lab services — incalmo-c2, blue-triage, wazuh-{manager,indexer,dashboard}, mbptl-{main,internal,app} — 9 lab volumes, network `portal5-lab`) + `Dockerfile.openwebui` | — |
| `deploy/launchd/` (13 plists), `deploy/grafana/`, `deploy/root/` | Host job templates, cost dashboard JSON, root helper + sudoers | rename §4.4 |
| `scripts/lab/splunk_setup/` (17 files) | Splunk lab provisioner (app/, cli.py, conf.py, plan.py, host.py, reindex.py, rest.py, inventory.json) | — |
| `scripts/hunt_bed/` (19 files) | Zero-signature proof harness: keys_*.py, ingest_{canonical,native}.py, prove_universal_blind.py, lab_purple_capture.py, score_*.py, graph_hunt.py, judged_hunt.py, observe.py, owui_proof.py | — |
| `tests/unit/` (331 .py), `tests/qat/` (25 files) | Merge gate + conversational UAT suite | — |
| `tests/wfe/` (224 files) | WFE harness incl. `settings_audit.py` (verification ladder depends on it) | — |
| `tests/security/` (96), `tests/fixtures/` (191), `tests/data/` (73), `tests/routing/`, `tests/lib/`, `tests/common.py`, `tests/conftest.py`, `tests/memory_guard.py`, `tests/expected_models.py` | Unit/QAT/WFE dependencies | — |
| `launch.sh`, `scripts/lib/`, `scripts/validation/`, `scripts/ci_local.sh`, `scripts/validate_system.py`, `scripts/smoke_stream.sh`, `scripts/complexity_report.py` | Operator entrypoint + gate chain | — |
| `Dockerfile.{pipeline,mcp,mcp.x86,dind,attack,binresearch,cad,pwsh}` | Image builds (renames inside, §4.2) | — |
| `imports/openwebui/` | OWUI import bundle: functions/ (portal_router_pipe, portal_attachment_paths), tools/ (8 portal_*.json), workspaces/ (25 JSONs: 23 `workspace_auto_*` presets + `workspace_security_reviewer.json` + `workspaces_all.json` bundle), mcp-servers.json, rag_template.txt, config.env | — |
| Root: `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `KNOWN_LIMITATIONS.md`, `README.md`, `LICENSE`, `.env.example`, `.mcp.json`, `prompts/`, `playbooks/`, `fixtures/realuse_v1/`, `data/sandbox/` | Build + governance + shared-workspace contracts | — |
| Ops docs (subset of `docs/`): `HOWTO.md`, `ADMIN_GUIDE.md`, `ALERTS.md`, `CLUSTER_SCALE.md`, `MCP_DEV_TOOLING.md`, `MODEL_SEAT_PROCESS.md`, `TASK_WORKSPACE_FITNESS_EVAL_V1.md`, `BACKUP_RESTORE.md`, `KNOWN_ISSUES.md`, `LAB_SETUP.md`, `BULLY_REVIEW_PROGRAM.md`, `DESIGN_WIKI_GENERATION_LOOP_V1.md`, `docs/hunt/` (22 files — the OrcaCyber + hunt design record) | Governing/operator docs | — |
| Live Splunk/hunt data: `hb_*` indexes, `/Volumes/data01/hunt_keys/`, `/Volumes/data01/omlx-models`, `~/AI_Output/` (`/workspace`), Ollama store, `~/.omlx` | **NOT repo files — untouched by the migration** (§4.7) | — |

### 3.2 KEEP with modifications (rename or regenerate)

| Path | Modification |
|---|---|
| `.mcp.json` | Regenerated (derived). Contains `"${HOME}/projects/portal-5"` git-server path → `${HOME}/projects/breaker` |
| `config/backends.yaml` `workspace_routing:` block | Regenerated by sync-config — never hand-copied |
| `imports/openwebui/workspaces/*.json`, `config/modules.generated.yaml` | Regenerated by sync-config |
| `config/MODEL_CATALOG.md` (2,400+ lines), `config/UNUSED_MODELS_*.md` | Copy + mechanical rename of tag/​group prose; `model_inventory.snapshot` recaptured fresh |
| `config/bench_workspaces.yaml` (757 lines) | Copy + rename; eval lanes only merge when `modules.eval.enabled` — keep `enabled: false` default |
| `CLAUDE.md` | Rewrite header identity Portal 5 → Breaker v1.0; all rules carry over verbatim (they are the design principles §1.2) |
| `scripts/OPERATOR_TOOLS.md` | Copy + rename |

### 3.3 TRIM / DROP — leave behind in `portal-5` (exact paths)

**Historical evidence & lane scaffolding**

| Leave behind | Size | Why |
|---|---|---|
| `portal_wiki/archive/` | 1,056 files | Frozen acceptance/bench evidence units (SEC_BENCH delta records, unit-acceptance-* snapshots). The wiki engine reads `canonical/`, not `archive/` |
| `portal_wiki/proposed/` | 40 files | Stale July-2026 proposed SEC_BENCH deltas; the proposal flow can regenerate |
| `coding_task/` except `WORKER_CONTRACT.md`, `CONTRACTS/` | 98 files total | Lane FINDING_*/REPORT_*/RUN_*.sh history belongs to Portal 5's process record; the standing worker contract + contracts are orchestrator infra and carry if the operator wants the same harness (note: `WORKER_CONTRACT.md` cites a `coding_task/BRIEF_TEMPLATE.md` that does not exist in the repo — recreate or drop the reference if carried) |
| `docs/test_trim/` (12), `docs/reselection/` (2), `docs/reconciliation/` (1), `docs/history/` (1), `docs/archive/` (1), `docs/design/` (1), `docs/generated/` (2), `docs/wiki/` (2) | 22 files | Dated reconciliation/trim snapshots; regenerated on demand |
| `docs/` root dated decision/eval snapshots: `DECISION_*_20261019.md` (3), `DESIGN_ENGINES_AND_PROMPTS_20261019.md`, `DESIGN_ROOTS_REFINEMENT_20261020.md`, `ENGINE_*_2026111*.md` (5), `FLEET_REVIEW_20261113.md`, `CAM_LDS_EXTRACTION_20261108.md`, `CORPUS_*_2026110*.md` (2), `COUNCIL_BENCH_20261019.md`, `GEMMA26B_QAT_CONSOLIDATION_20261106.md`, `HOST_MEMORY_SAFETY_V1_CLOSEOUT.md`, `EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1_CLOSEOUT.md`, `HUNT_{JUDGE_RESULTS_20261112,KNOWLEDGE_S2_HANDOFF,P1_RESULTS_20261109,P3_RESEARCH_20261111}.md`, `LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md`, `SPINE_P0_ARCHIVE_RUN.md`, `BULLY_STATE_REVIEW_20261008.md`, `FINDING_ANCHOR_PROVENANCE_PHANTOM_PATH.md`, `ACCEPTANCE_RESULTS.md` | ~25 files | Point-in-time eval records; superseded by the closeout register `docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md` (which is KEEP — it is the authoritative disposition register) |
| `tests/` root dated reports: `UAT_CATALOG_TRIAGE_2026-06-26.md`, `UAT_KNOWN_ISSUES_2026-06-27.md`, `UAT_RESULTS.md`, `UAT_RUN_LOG.md`, `ACCEPTANCE_EVIDENCE.md`, `EXEC_SEC_FULL_COVERAGE_V1.md`, `PORTAL5_BENCH_EXECUTE_V4.md`, `PORTAL5_BENCH_SEC_EXECUTE_V3.md`, `PORTAL5_CANDIDATE_EVAL_V1.md`, `PORTAL5_PERSONA_MATRIX_EXECUTE_V1.md`, `uat_dashboard.py`, `tests/uat_corpus/` (2 files), `tests/acceptance_corpus/` (8), `tests/compliance_probe/` (3), `tests/frontend/` (2), `tests/frontends/` (1), `tests/_netguard/` (2), `tests/toolpreselect/` (5 — verify zero imports first), `tests/scripts/` (3) | ~35 files | Superseded by `tests/qat/`; the retired `tests/uat/` + `tests/acceptance/` are already gone. **Gate:** before dropping any `tests/` subtree, grep `pytest`/`pythonpath` references — `tests/benchmarks` proved load-bearing (§1.3) |
| `tests/benchmarks/` one-off probes & history — keep ONLY `bench_lab_exec.py`, `bench/notify.py`, `fixtures/`, `engine_h2h.yaml` (renamed refs), `capability_lib.py` (imported by probes still kept) | 78 files, ~18k lines → keep ~10 | `bench_lab_exec` + `tests.benchmarks.bench.notify` are runtime imports of `portal/modules/security/core/{_data,matrix}.py`. Drop `bench_*` one-offs, `results/`, `cad_gauntlet*`, `coding_shootout_analyze.py` only after a reference grep |
| `scripts/_archive/` | frozen | Already the repo's own retirement ground (mlx-retired-3a0c58e, analyze_bench_v5, engine_h2h_20260924, bench_v5_ladders) |
| `scripts/` one-off eval lanes (drop after grep): `bully_*` run/census scripts (17), `compliance_y2{1,3}_*`, `defensive_bully_*` (2), `dflash_ab.py`, `saluki_rule5_reverify.py`, `spine_p0_*` (3), `pending_verdicts_*` (3), `execute_pending_verdicts.py`, `collapse_snapshot.py`, `probe_single_part_live.py`, `retry_bully_sampled_window_entries.py`, `rebench_plan.py`, `remove_unused_models_20261115.sh`, `bench_supervisor.py` (verify no validator references), `arm_shadow_batch.py` | ~30 files | Point-in-time campaign harnesses. **Load-bearing and KEEP:** everything referenced by `launch.sh`, `scripts/validate_system.py`, `scripts/validation/registry.py` consumers, `scripts/ci_local.sh`, pre-commit/pre-push (`check_no_raw_run_output.sh`, `complexity_report.py`, `model_cleanup_audit.py`, `routing_regression.py`, `alias_census.py`, `project_compliance_sections.py`, `reconcile_security_arm.py`, `pending_verdicts_evidence.py` …), `scripts/OPERATOR_TOOLS.md`, and the WFE/QAT suites. The executor greps references per file before each drop |
| `config/` planning deadwood: `BENCH_REWIRE_PLAN_V1.md`, `FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md`, `PROPOSED_REASONING_OVERHAUL_V3.md`, `TASK_{OMLX_REASONING_POOL_REPAIR,REASONING_GROUP_OVERHAUL,ROUTER_POSTURE_GATE,WEB_SEARCH_RESILIENCE}_V1.md`, `PENDING_MODEL_VERDICTS.md`, `UNUSED_MODELS_2026{0721,0810,0811}.md`, `model_inventory.snapshot` (recapture) | ~11 files | Planning/proposal residue; the closeout register supersedes the UNUSED/verdict series |
| `deploy/_archive/omlx-canceled-P5-FUT-013/` | 1 dir | Canceled feature archive |
| `reports/` dated subtrees (`bully_b1/`, `mawa/`, `review_eval/`, `runtime/`, `compliance/`, `PENDING_VERDICTS_ANALYSIS_*.md`) | ~keep the dir, drop dated runs | Eval output history; recaptured on demand |

(`fixtures/realuse_v1/` is deliberately **not** on this list: the workspace-fitness eval
is HELD per `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md` — not trimmable until register v4
issues.)

**Retired in-config blocks — trim during the cut (they are copy-carrying dead weight):**

| Block | Location | Content |
|---|---|---|
| Retired workspace aliases (16) | `config/portal.yaml` lines 686–751 `aliases:` | `auto-image/video/music/math`, `general-fast/deep`, `auto-nemotron`, `auto-data`, `auto-extract-uncensored`, `auto-uncensored-throwaway[::gemma4-heretic|::ornith15]`, `auto-creative`, `auto-bigfix`, `auto-cad`, `compliance-reading` — all `remove_after: 2026-12-31`. Breaker is brand-new: aliases cannot have live API callers, so they enter as `workspaces:` keys only |
| Retired model entries (9+) | `config/portal.yaml` lines ~3404–3443 `models:` with `retired: true` | lily-cybersecurity, dolphin3-r1-mistral, whiterabbitneo, minimax-m2.1 (skip-138gb), deepseek-r1:32b, supergemma4-26b, dolphin-llama3:70b, llama3.3:70b … — disposition register stays (`docs/MODEL_FLEET_CLOSEOUT_20260906.*`) |

### 3.4 What deliberately does NOT move

`hb_*` Splunk indexes, `/Volumes/data01/hunt_keys/`, `/Volumes/data01/omlx-models` (+ hf-cache symlinks), `~/AI_Output/` and its `portal-data` subdir, the Ollama store (both `manifests/` trees + registry engine builds), `~/.omlx`, live Splunk data, Grafana/Prometheus *data* volumes, and the seated-model fleet (any removal is an A/B decision per `docs/MODEL_SEAT_PROCESS.md` — never a migration side effect).

---

## 4. Complete `portal` → `breaker` rename map

### 4.1 Python package, imports & tooling

| Old | New | Files touched |
|---|---|---|
| `portal/` | `breaker/` | 737 .py files move; every `import portal…` / `from portal…` rewritten repo-wide |
| `portal_wiki/` | `breaker_wiki/` | package + `pyproject.toml [tool.hatch] packages`, `scripts/native-mcp-service.sh` line 232 (`exec "$PY" -m portal_wiki.wiki_mcp`) |
| `portal_mcp/` | `breaker_mcp/` | package + `pyproject.toml` (packages list, ruff per-file-ignores `"portal_mcp/**/*.py"`) |
| `portal_channels/` | `breaker_channels/` | package + compose build context refs |
| `[project.scripts]` `portal-pipeline = "portal.platform.inference.__main__:main"`, `portal = "portal.platform.inference.cli:app"` | `breaker-pipeline`, `breaker` | `pyproject.toml` lines 265–267 |
| `pyproject.toml [tool.hatch.build.targets.wheel] packages = ["portal_channels", "portal_mcp", "portal", "portal_wiki"]` | same four, `breaker_*` | line 270 |
| `uv run portal …` / `python -m portal.platform.…` CLI invocations (42 call sites across `launch.sh`, `scripts/`, `docs/`) | `uv run breaker …` / `python -m breaker.platform.…` | `launch.sh` (11 `cli` invocations: lines 201/371/373/407/457/461/550–593 …) + scripts + docs |
| `python -m portal.platform.inference.cli` | `python -m breaker.platform.inference.cli` | `launch.sh`, `scripts/native-mcp-service.sh`, host plist templates |
| `pyproject.toml [tool.pytest.ini_options] pythonpath`, `tests/conftest.py`, `tests/wfe/`, `scripts/hunt_bed/prove_universal_blind.py` (`from portal.modules.security.core.hunt…`) | `breaker.…` | all test/harness imports |
| `Dockerfile.pipeline` COPY lines 25–30 (`portal/__init__.py`, `portal/platform/`, `portal/modules/eval/persona_matrix/prompts/`) + `groupadd -r portal && useradd -r -g portal portal` (lines 38–39) | `breaker/…`, `breaker` user | also `Dockerfile.mcp`, `Dockerfile.attack` (`/opt/portal5-attack.contract.json`, `verify-portal5-attack`), `Dockerfile.binresearch`, `Dockerfile.pwsh`, `Dockerfile.mcp.x86` |
| `uv run mypy portal/` gate | `uv run mypy breaker/` | `CLAUDE.md`, `scripts/ci_local.sh`, pre-commit config |
| Ruff per-file ignore paths (`pyproject.toml` lines 306–356: `scripts/_archive/**`, `portal_mcp/**`, …) | rewrite any `portal*` path | config only |

### 4.2 Docker & Compose

| Old | New |
|---|---|
| `deploy/portal-5/` (compose yml 1,025 lines, lab yml, `Dockerfile.openwebui`) | `deploy/breaker/` |
| Service keys: `portal-pipeline`, `portal-telegram`, `portal-slack` | `breaker-pipeline`, `breaker-telegram`, `breaker-slack` |
| Container names (24): `portal5-{ollama,ollama-init,pipeline,open-webui,openwebui-init,mcp-documents,mcp-tts,mcp-whisper,dind,mcp-sandbox,mcp-binresearch,mcp-proxmox,mcp-security,browser-mcp,telegram,slack,searxng,mcp-research,mcp-memory,mcp-rag,mcp-cad-render,prometheus,grafana,grafana-image-renderer}` | `breaker-<same suffix>` |
| Network `portal-5_default` (implicit from compose dir name); lab network `portal5-lab` (lab yml lines 229–231, subnet 172.30.0.0/24) | `breaker_default`; lab network `breaker-lab` (keep the subnet) |
| Images: `portal5-open-webui:v0.13.0-hardened`, `portal5-dind:latest`, `portal5-attack:latest`, `portal5-binresearch:latest`, `portal5-pwsh:latest` | `breaker-open-webui:v0.13.0-hardened`, `breaker-dind/attack/binresearch/pwsh:latest` (rebuild via `./launch.sh rebuild`, `build-lab-attack`, `build-binresearch`) |
| Named volumes: `portal5-hf-cache`, `portal5-lance`, `portal5-kb-sources` | `breaker-hf-cache`, `breaker-lance`, `breaker-kb-sources` — **data migration required** (`docker run --rm -v portal5-lance:/from -v breaker-lance:/to alpine cp -a /from/. /to/` per volume, or accept fresh + re-ingest; operator decision at Phase 7) |
| In-compose hostnames/URLs: `http://portal5-pipeline:9099` (mcp-cad-render), prometheus target `portal-pipeline:9099` (`config/prometheus/prometheus.yml` job `portal-pipeline`), `scripts/native-mcp-service.sh` rewrite-hosts list `"host.docker.internal portal-pipeline"` | `breaker-pipeline` everywhere |
| `launch.sh` `COMPOSE_DIR="$PORTAL_ROOT/deploy/portal-5"`, `PORTAL_ROOT` → `BREAKER_ROOT`, backup path `portal5_backup_*` (`scripts/lib/backup.sh`), lab filters `name=portal5-lab` (`scripts/lib/lab.sh`) | `deploy/breaker`, `BREAKER_ROOT`, `breaker_backup_*`, `name=breaker-lab` |
| `deploy/root/portal5-root`, `sudoers-portal5-root` | `breaker-root`, `sudoers-breaker-root` |
| Compose project name (shared today as `portal-5`) | `breaker` — **this is the fix for the historical foot-gun where a worktree `docker compose` recreates live containers**: fresh project name isolates Breaker from any Portal-5 checkout |

### 4.3 Environment variables — clean break, no shim

Breaker is a brand-new repo and a brand-new `.env`; a deprecation shim would carry the
old name into fresh code for no callers. **Rename all `PORTAL_*` → `BREAKER_*` in one
mechanical pass** (83 distinct names audited via repo-wide grep over
py/yml/yaml/sh/plist/json/env-example; `.env.example` 867 lines carries 12 `PORTAL_`
entries, compose passes ~15 through, host scripts read the rest). Groups:

- **Trace/debug:** `PORTAL_{TRACE,TRACE_BODIES,TRACE_MAX,TRACE_MAX_BYTES,TRACE_DIR,TRACE_TOOL_RESULT_CARRY,TRACE_MEDIA_TIMEOUT_S,TRACE_JARVIS_WAIT_S}` — note `PORTAL_TRACE_DIR=/tmp/portal_traces` default becomes `/tmp/breaker_traces`
- **Pipeline/service URLs:** `PORTAL_{PIPELINE_URL,ROUTER_URL,REVIEW_PIPELINE_URL,REVIEW_OLLAMA_URL,REVIEW_OMLX_URL,PUBLIC_URL,DATA_ROOT,WS_CACHE,CONFIG,ENV_FILE}`
- **ARM (orchestrated workers):** `PORTAL_ARM_{TELEGRAM_DB,APPROVAL_TTL_SECONDS,DEEP_DIGEST,FAST_DIGEST,PIPELINE_URL}`
- **Hunt (zero-signature stack):** `PORTAL_HUNT_{KNOWLEDGE_STORE,KNOWLEDGE_FAMILIES,JUDGE_BACKEND,JUDGE_MODEL,JUDGE_URL,JUDGE_KEY_ENV,EMBEDDING_MODEL,EMBEDDING_URL,EMBEDDING_KEY_ENV,MERGE_WEIGHTS,STAGE4_VERDICTS}`
- **Eval/bench:** `PORTAL_{ENABLE_EVAL,BENCH_WORKSPACES,QUALITY_V1,SIMPLIFY_V1,YAML_V1,SEATS,EMERGENT*}`
- **Security/lab:** `PORTAL_{LAB_CIDR,SECURITY_*,SWEEP_REPORT,TARGETS}`
- **Build/bootstrap:** `PORTAL_{BUILD_SHA,BUILD_DIRTY,ROOT,PATH,CURL,DOCKER,GIT,LIVE_CHECKOUT,HOST_SETUP,ALLOW_STACK_FROM_WORKTREE,SYNC_SKIP_PIPELINE_CHECK,UP_HEALTH_TRIES,NATIVE_MCP_HEALTH_TRIES,HEALTH_*,TIMEOUT_S,DEFAULT_PREDICT_LIMIT,FILE,RECIPE_OK__,TARGET_POSTCONDITION,ESCALATION_TARGET,NETGUARD,NETGUARD_LOG,DIND_CONTAINER,PIPELINE_CONTAINER,COMPOSE_DIR,SOURCE_PREFIX,ARM_}`

Operator-side places to update by hand at cutover: `.env` (copy from new
`.env.example`), shell profiles that export `PORTAL_*`, CI/cron outside the repo, and
the launchd plists (regenerated — §4.4).

### 4.4 macOS LaunchAgents — `com.portal5.*` → `com.breaker.*`

Two layers, both audited:

**Repo-tracked templates (13) — `deploy/launchd/`:** `com.portal5.{arm-queue,
engine-update, host-ml-watch, image-update, log-rotate, model-update, omlx-watchdog,
omlx, powermetrics, security-sweep, security-update, update-check, weekly-rebuild}.plist`
→ rename label + program paths (they point at `$PORTAL_ROOT` scripts) to
`com.breaker.*`.

**Live-installed agents on this host (38 in `~/Library/LaunchAgents/`, audited
2026-11-24):**

- **MCP/ML services (22):** `mlx-speech, mlx-transcribe, vl-retrieval, eg2-embedding,
  pipeline-mcp, mitre-mcp, detections-mcp, vulnintel-mcp, icsot-mcp, compliance-mcp,
  compliance-mcp-eval, detection-mcp, data-mcp, netforensics-mcp, review-mcp, wiki-mcp,
  git-mcp, unifi-mcp, music, music-minimax, mflux, video-mlx`
- **Platform/cron jobs (16):** `omlx, omlx-watchdog, arm-queue, engine-update,
  image-update, model-update, log-rotate, security-sweep, security-update,
  update-check, weekly-rebuild, host-ml-watch, brain-idle-off, orchestrate-burn,
  orchestrate-digest, orchestrate-usage`
  (the `powermetrics` job has a repo template — `deploy/launchd/com.portal5.powermetrics.plist`
  + `scripts/portal5-powermetrics.py` — but is **not currently installed**; treat the
  template, not the live set, as its source of truth)

Rename mechanism: the service labels are **config-driven** — `config/portal.yaml`
`mcp_fleet[].launchd_label:` (e.g. line 613 `com.portal5.compliance-mcp`) and
`host_jobs[].label:` (lines 661–680). `portal/platform/inference/cli/module_services.py`
generates and bootstraps `~/Library/LaunchAgents/<label>.plist` from those labels
(`_plist()` line 174, `launchctl bootstrap` line 169). So the cutover is:
1. rename labels in `config/breaker.yaml`; 2. `breaker module services-sync` (or
   equivalent CLI path) writes `com.breaker.*` plists; 3. `launchctl bootout` each
   `com.portal5.*` gui/$UID agent; 4. delete stale plists only after the breaker twin is
   confirmed healthy. `scripts/native-mcp-service.sh` (case list line 11–17, rewrite
   hosts line ~48) renames its service-case unchanged — service *names* (`mlx-speech`
   etc.) are internal, only the label prefix changes.

### 4.5 Open WebUI workspaces, presets & display names

| Old | New | Where |
|---|---|---|
| `"🔒 Portal Security Analyst"` (workspace name + description) | `"🔒 Breaker Security Analyst"` | `imports/openwebui/workspaces/workspace_auto_security.json` lines 3/5, `imports/openwebui/portal_import_bundle.json` lines 336/338, `config/portal.yaml` workspace `auto-security` (display text), `config/personas/securityuncensored.yaml` |
| All 23 `imports/openwebui/workspaces/workspace_auto_*.json` + `workspace_security_reviewer.json` + `workspaces_all.json` — every `"Portal …"` display string | `"Breaker …"` | regenerated by sync-config from `config/breaker.yaml` workspace names/descriptions — fix the YAML, regenerate, verify JSON |
| Persona display names (`"⚡ Portal Agentic Coder (Heavy)"`, `"🔄 Portal IDE / Agentic Coder"`, `"🔓 Portal Code Uncensored"`, …) | `"… Breaker …"` | `config/personas/*.yaml` `name:` fields (grep `Portal` in `config/personas/` — audited hits in agenticheavy, agenticlite, codingagentic, codinguncensored, codinguncensoredagentic, blueteamdefender comments, …) |
| `imports/openwebui/functions/portal_router_pipe.json` (+ embedded `portal_base_url`, `portal_api_key` valves, `pipes()` names `"Portal Auto Router"`, `"Portal Code Expert"`, …) | `breaker_router_pipe.json`, `breaker_base_url`, `breaker_api_key`, `"Breaker …"` | also `portal_attachment_paths.json` → `breaker_attachment_paths.json` |
| `imports/openwebui/tools/portal_{code,documents,mflux,music,security,tts,whisper,mlx_transcribe}.json` | `breaker_*.json` | 8 tool JSONs |
| `portal-trace-docs` (trace-docs OWUI knowledge/workspace id) | `breaker-trace-docs` | `imports/openwebui/portal_import_bundle.json` + `config/portal.yaml` trace-docs refs |

### 4.6 Grafana & Prometheus

| Old | New |
|---|---|
| Dashboards (8): `config/grafana/dashboards/portal5_{acceptance,benchmarks,mbptl,model_management,orchestrate_usage,overview,secbench,uat}.json` | `breaker_*.json` (8, plus `dashboards.yml` provisioning path refs) |
| Cost dashboard: `deploy/grafana/portal5_cost.json` | `deploy/grafana/breaker_cost.json` |
| Prometheus scrape job `portal-pipeline` → target `portal-pipeline:9099` | job `breaker-pipeline`, target `breaker-pipeline:9099` (`config/prometheus/prometheus.yml`; also `orchestrate-usage` job stays) |
| Grafana datasource uid/title refs to `Portal` | `config/grafana/datasources/datasources.yml` |
| **Metric names:** every `portal5_*` metric family → `breaker_*` (audited: 84 distinct `portal5_*` tokens across 61 `portal/` files — 32 under `portal/platform/` (`router/metrics.py`, `load_guard.py`, `lance_guard.py`, `memory/graph_memory.py`, `mcp_host/pipeline_mcp.py`, `wiki/claims.py`, `retrieval/store.py`, …) + 29 under `portal/modules/`; families include `portal5_{errors_total,load_guard_*,power_*,energy_*,embeddings_*,context_fit_total,capacity_fallback_total,hint_fallback_total,no_answer_total,auto_context_*,barrier_toolcall_fallback_total,client_disconnect_cancel_total,empty_answer_toolless_retried_total,answer_without_tool_retried_total,ctx_*,mtp_*,hunt_*,lab_*,lance,kb_sources,orchestrate_usage,persona_matrix,escalation_dispatch,memory_extract_failures,…}`) | rename at the emitters AND simultaneously in the 8 dashboard JSONs + cost dashboard, `scripts/lib/grafana_panels.py`, `scripts/update_grafana_*.py`, and any Splunk/panel references. Historical series in the `prometheus-data` volume stays under the old names — fresh volume for Breaker, keep Portal-5's volume mounted read-only if history matters (operator decision) |

### 4.7 Splunk / Hunt / Compliance — what stays untouched (data continuity)

- **`hb_*` index names: unchanged.** Audited families: `hb_flaws_aws`, `hb_ait_{fox,harrison,russellmitchell,russellmitchell_v2,santos,santos_v2,shaw,wardbeck,wilson}`, `hb_kyoushi_s1{,_v2}`, `hb_uwf_zeek24`, `hb_lmd_2023`, `hb_ics_pcap`, `hb_lab_*`. Index names are CLI args (`scripts/hunt_bed/ingest_native.py --index`), not brand strings — the proof harness keys on them (`scripts/hunt_bed/prove_universal_blind.py` `KEY_PATHS`) and the live Splunk holds the data. Renaming would orphan every saved search and the entire zero-signature key correspondence.
- **`/Volumes/data01/hunt_keys/`: unchanged.** Key JSONs are written by
  `scripts/hunt_bed/keys_*.py` (`keys_nextwave.py` operator default,
  `lab_purple_capture.py` `KEYS_DIR = Path("/Volumes/data01/hunt_keys")`) and consumed
  by the blind prover with the same default. No rename, no move.
- **Canonical TA sourcetypes (`ingest_canonical.py`): unchanged** — Splunk-side props
  depend on them.
- **Compliance corpus/register:** `config/compliance/` (closeout_checks.yaml,
  council.yaml, mapping/reading prompts, y21_resolutions.yaml) copies with internal
  rename only; the NERC CIP-007-6 corpus and review store are **live data outside the
  repo** — untouched. `scripts/nerc_autosync.py` state file
  `data/private/nerc_autosync_state.json` (gitignored) stays at its path — only the
  script's imports rename.
- **Hunt knowledge DuckDB (`BREAKER_HUNT_KNOWLEDGE_STORE`):** path is an env var —
  keep the operator's current value so the knowledge families carry over seamlessly.

---

## 5. Recommended structural refactors during the clean cut

Ordered by value; each is scoped so the mechanical rename (§4) never depends on it.

### 5.1 Package boundary cleanup (`breaker/platform/` vs `breaker/modules/`)

Keep the existing seam rule (CLAUDE.md R3: MCP modules never import
`platform.inference`) and make it *structural*: during the cut, run
`grep -rn "from breaker.platform" breaker/modules/ | grep -v mcp_host` and
`grep -rn "import breaker.modules" breaker/platform/` and file every violation as a
Phase-4 fix-or-report. The `modules.generated.yaml` service registry stays the single
wiring point. No new layer, no directory shuffle beyond the rename — the seam is
already right; the refactor is enforcement (a unit test asserting the import
direction, mirroring `tests/unit/test_channels.py`-style guards).

### 5.2 `scripts/` consolidation → `scripts/{ops,lab,hunt,compliance}/`

Target layout (move + import fix, no logic changes):

```
scripts/ops/     launch/upkeep: engine_autoupdate, model_upstream, engine_contract_check,
                 seat_preflight, rotate_logs, weekly_rebuild, backup (lib/backup.sh),
                 host_quiet, memory_safety_watch, omlx_* tooling, portal5-powermetrics
                 → breaker-powermetrics, native-mcp-service.sh, mcp-entrypoint.sh,
                 pipeline-entrypoint.sh, ci_local.sh, validate_system.py,
                 complexity_report.py, validate/ (the lettered checks stay as validation/)
scripts/lab/    (already exists) splunk_setup/ + lab_host, lab_ready, lab_setup,
                 lab_discover, lab_targets, lab_bots_install, caldera_emulate,
                 lab_provision_*.ps1, lab_splunkbase_install, load_attack_data_anchors,
                 verify_attack_image, image_security_update
scripts/hunt/   hunt_bed/ (19 files) + hunt_run.py, hunt_investigate.py,
                 security_sweep.py, run_hauhaucs_full_sweep.sh
scripts/compliance/  (already exists) + nerc_autosync.py, materialize_* corpus scripts,
                 compliance_acceptance.py, refresh_compliance_catalogs,
                 compliance_* report/probe scripts that survive §3.3 trim
```

Rules for the move: one `git mv` per file, update the callers found by
`grep -rn "<old path>"` (launch.sh, validation registry, OPERATOR_TOOLS.md, docs,
pre-commit hooks) in the same commit, and keep `scripts/lib/`, `scripts/validation/`,
`scripts/ci_local.sh`, `scripts/validate_system.py`, `scripts/smoke_stream.sh`,
`scripts/complexity_report.py` at the top level (hook chains reference them by path).
Re-run `python3 scripts/complexity_report.py --gate` — unwired_scripts is a gated
total, so the consolidation must leave it flat or lower.

### 5.3 `mypy` 100% green from Day 1 (scripts/ baseline debt)

Audited debt: `uv run mypy scripts/` today **aborts** (duplicate module
`scripts.compliance.truth.quote_fidelity` vs `truth.quote_fidelity`, and a bare
`_local` import in `scripts/compliance/truth/answer_key.py:32`); with
`--explicit-package-bases` it reports **2,850 errors in 232 files** (checked 292).
`portal/` source itself is mypy-clean (0 findings in `portal/**`), but the debt already
leaks into the `uv run mypy portal/` gate run via import-following — 582 findings, all
in `scripts/` + `tests/` modules portal imports (`scripts/validation/*` 196+
105+57+51+…, `tests/wfe/settings_audit.py`, `scripts/lab_targets.py`). Plan for the cut:

1. Add `__init__.py` where duplicate-module detection demands it (or run mypy with
   `--explicit-package-bases` permanently in `scripts/ci_local.sh`).
2. Fix the `_local` relative-import error in `scripts/compliance/truth/answer_key.py`
   first — it blocks everything after it.
3. Burn down in this order: (a) `no-untyped-def`/`type-arg` mechanical annotations in
   `scripts/compliance/truth/*` (the densest cluster, audited: `substrate_vs_key.py`,
   `copy_probe.py`), (b) `scripts/validation/` — these are gate code, fix completely,
   (c) one-off campaign scripts that survived §3.3 — fix or move to `scripts/_archive/`
   equivalents. 2,850 findings across 232 files is roughly the size of the existing
   `portal/` strict pass at its worst; schedule it as its own lane with a running
   error-count budget (target: `uv run mypy breaker/ scripts/` → `Success: no issues`).
4. Gate it: `scripts/ci_local.sh` gains `uv run mypy scripts/ --explicit-package-bases`
   once green, so Breaker never re-accumulates the debt.

### 5.4 Compliance `IN_SERVICE = True` readiness checklist

Audited state: the flag is defined at `scripts/validation/compliance_acceptance.py:60`
(`IN_SERVICE = False`, single definition site) and consumed by
`scripts/validation/compliance_data_truth.py` (lines 52–55: FAIL downgrades to WARN),
`scripts/validation/compliance_currency.py` (lines 61–64), and
`tests/qat/scenarios.py` (lines 6/36: "auto-compliance runs smoke turns only … pending
the V6 ACME" — scenario id `compliance_smoke`, workspaces `auto-compliance` /
`auto-compliance::reading`). Readiness gate before flipping to `IN_SERVICE = True`:

1. `uv run bash scripts/run_compliance_acceptance.sh` — full acceptance green (not the
   smoke-turn subset `tests/qat` runs pre-service).
2. `uv run python scripts/nerc_autosync.py --emit-change-report` — register change
   report emitted; state at `data/private/nerc_autosync_state.json` fresh.
3. `uv run python scripts/validation/compliance_currency.py` — every register
   requirement current.
4. `uv run python scripts/validation/compliance_data_truth.py` — data-truth grade ≥ its
   registered threshold with the FAIL→WARN downgrade *removed* (flip the flag, re-run,
   compare).
5. `uv run python -m tests.qat --scenario compliance_smoke` (compliance lane, tagged
   `in_service_false`) plus `uv run python -m tests.qat --stage uat` compliance
   journeys green.
6. Only then flip `IN_SERVICE = True` at `scripts/validation/compliance_acceptance.py:60`,
   delete the downgrade branches in the two validators, and update the
   `tests/qat/scenarios.py` annotations. The flip is a Breaker-Phase-6 item, **after**
   the V6 ACME gate — it is an acceptance decision, not a rename.

### 5.5 Continuous hunter proof harness (the existing Vulhub lane)

The brief's `lab_vulhub_fleet_sweep.py` does not exist (§1.3); the repo's controlled
live-Vulhub capture harness is `scripts/hunt_bed/lab_purple_capture.py` (Vulhub
purple-team capture → byte-faithful zero-label Splunk ingest via `ingest_native.py` →
keys to `/Volumes/data01/hunt_keys/`), landed with commit `8820c2b78` and the R2/R3
verdict reports (`coding_task/REPORT_HUNT_VERDICT_R3_*.md`). Wiring it as Breaker's
continuous proof harness:

1. Keep `scripts/hunt_bed/` whole through the cut (imports rename only:
   `from portal.modules.security.core.hunt…` → `breaker.…`).
2. Post-cut, add a scheduled lane (existing `com.portal5.*` job pattern →
   `com.breaker.hunt-proof` or an `arm_jobs/` YAML) that runs:
   `scripts/hunt_bed/lab_purple_capture.py` (capture) → `ingest_native.py --index hb_lab_*`
   → `prove_universal_blind.py --all-proof --keys-dir /Volumes/data01/hunt_keys`
   → score report. The proof corpus indexes and `KEY_PATHS` in
   `prove_universal_blind.py` (lines ~34–40: `hb_flaws_aws`, `hb_ait_wardbeck`, …) stay
   fixed so scores stay comparable across the rename.
3. OrcaCyber rule lineage lives in `docs/hunt/ORCACYBER_*.md` (deep dives 2/3, hunt
   plan, code review) — KEEP, they are the hunter's design record.

### 5.6 `nerc_autosync.py` wiring

Already live (audited: `scripts/nerc_autosync.py`, state at
`data/private/nerc_autosync_state.json`, consumers `scripts/validation/compliance_currency.py`
and `scripts/compliance/family_links.py`). In Breaker: copy with renamed imports, keep
the state path (data continuity), and register its `--emit-change-report` in the
Phase-6 verification ladder (§6, step V8) so currency is proven at every release, not
assumed.

---

## 6. Step-by-step cutover & verification checklist

Ordered phases. **Do not start Phase 1 without operator go-ahead on `main`.** Each
phase ends with its gate green before the next begins. Work happens on lane branches in
worktrees per CLAUDE.md R10; the fresh `breaker` repo starts on `main` at Phase 1.

### Phase 0 — Freeze & baseline receipt (Portal 5 side)

- [ ] P0.1 Record HEAD (`git rev-parse HEAD` in the Portal-5 checkout), `docker images`
      digests, and `ls ~/Library/LaunchAgents/com.portal5.* | wc -l` (audited today: 38).
- [ ] P0.2 Run the full Portal-5 ladder once and archive the output:
      `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check . && uv run mypy portal/ && python3 scripts/complexity_report.py --gate && bash scripts/ci_local.sh`
      (today's baseline: portal tree mypy-clean, scripts/ 2,850-error debt per §5.3).
- [ ] P0.3 `cp` any multi-hour checkpoint/WFE state files (non-negotiable backup rule)
      and snapshot `data/private/`, `results/checkpoints/`.

### Phase 1 — Initialize the blank `breaker` repo

- [ ] P1.1 `git init` fresh repo `breaker` (or blank GitHub repo
      `github.com/<owner>/breaker`); create `main`, copy `LICENSE`,
      `.gitignore` (from Portal 5, review entries for `portal*` paths), `CLAUDE.md`
      (rewritten identity header per §3.2), `.pre-commit-config.yaml` (updated hook
      paths).
- [ ] P1.2 Copy the KEEP set (§3.1) at audited HEAD only — `git -C portal-5 archive
      729e219d5 <path>` or checkout-then-rsync per subtree. **No `coding_task/`
      history, no `portal_wiki/archive|proposed`, nothing from §3.3.**
- [ ] P1.3 First commit on the blank repo: "chore: initial import of living product
      from portal-5@<HEAD>". Gate: `git diff --check` clean.

### Phase 2 — Mechanical rename (one commit family, ordered)

- [ ] P2.1 Packages: `git mv portal breaker`, `git mv portal_wiki breaker_wiki`,
      `git mv portal_mcp breaker_mcp`, `git mv portal_channels breaker_channels`;
      rewrite every import (`grep -rln "from portal\|import portal" | wc -l` first for
      the receipt, then `python -c` bulk replace with review).
- [ ] P2.2 `pyproject.toml`: packages list, `[project.scripts]`, mypy/ruff path ignores;
      `uv sync --all-extras --frozen` green; `uv run pytest tests/unit/ -q` green.
- [ ] P2.3 Config: `git mv config/portal.yaml config/breaker.yaml`; rename internal
      keys/values per §4 (fleet `name: portal-*` → `breaker-*`, `launchd_label:`,
      `host_jobs` labels, workspace display strings, persona `name:` fields, metric
      prefixes in emitters). Apply §3.3 config trims (aliases block, retired models).
- [ ] P2.4 Docker: `git mv deploy/portal-5 deploy/breaker`; rename services, container
      names, volumes (keep data-volume migration for Phase 7), images, in-compose URLs;
      `launch.sh` (`PORTAL_ROOT`→`BREAKER_ROOT`, `-m breaker.…`, help strings);
      `scripts/native-mcp-service.sh`; all 8 `Dockerfile.*` COPY/USER paths.
- [ ] P2.5 Env: `.env.example` `PORTAL_*` → `BREAKER_*` (12 entries) + compose
      pass-throughs + all script readers (`grep -rn "PORTAL_" --include="*.py"
      --include="*.sh"` burn-down to zero).
- [ ] P2.6 launchd templates: `deploy/launchd/com.portal5.*.plist` → `com.breaker.*`
      (13 files), plus `deploy/root/` helper names.
- [ ] P2.7 OWUI: `imports/openwebui/` function/tool JSON renames + display strings
      (§4.5); then regenerate workspaces from config:
      `uv run python -m breaker.platform.inference.cli sync-config` (repo-file writes
      only — **never** `./launch.sh sync-config` from a worktree).
- [ ] P2.8 Grafana/Prometheus: the 8 dashboard JSONs + cost dashboard, `datasources.yml`,
      `prometheus.yml` job/target, metric emitters (`breaker_*`), panel scripts.
- [ ] P2.9 Docs/config prose: README.md, CLAUDE.md, KNOWN_LIMITATIONS.md,
      OPERATOR_TOOLS.md, MODEL_CATALOG.md — every `Portal 5`/`portal5`/`portal-5`
      prose hit.
- [ ] P2.10 Leftover sweep (gate): `grep -rin "portal5\|portal-5\|com\.portal5\|
      PORTAL_" --exclude-dir=.git --exclude-dir=breaker_wiki/archive -l` must return
      **only** intentional historical references (e.g. the closeout register's
      provenance notes, this plan). Each remaining hit gets a `# historical:` marker
      or is renamed.

### Phase 3 — Trim pass (§3.3 executed against the fresh repo)

- [ ] P3.1 For each candidate drop: `grep -rn "<basename>" breaker/ config/ scripts/
      tests/ launch.sh pyproject.toml` — zero load-bearing hits before `git rm`.
      (`tests/benchmarks` proves the rule: keep `bench_lab_exec.py`, `bench/notify.py`,
      `fixtures/`, `engine_h2h.yaml`, `capability_lib.py`.)
- [ ] P3.2 Confirm `pythonpath` in `pyproject.toml` still resolves; `uv run pytest
      tests/unit/ -q` green after every removal batch.

### Phase 4 — Structural refactors

- [ ] P4.1 §5.1 import-direction guard test lands green.
- [ ] P4.2 §5.2 scripts consolidation (`scripts/{ops,lab,hunt,compliance}/`), callers
      updated same-commit; `python3 scripts/complexity_report.py --gate` flat-or-lower
      (unwrapped_scripts is a gated ceiling; `config/complexity_budget.yaml` is not
      edited).
- [ ] P4.3 §5.3 mypy scripts burn-down begins (may be its own lane; target `Success:
      no issues` before Phase 6, or the gap is explicitly reported in the Breaker
      v1.0 release notes).

### Phase 5 — Build & first boot

- [ ] P5.1 `uv sync --all-extras --frozen`; `uv run pytest tests/unit/ -q`,
      `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy breaker/`.
- [ ] P5.2 `./launch.sh rebuild && ./launch.sh up` on the designated host (operator
      runs; fresh compose project `breaker`, fresh volumes except migrated ones §4.2).
- [ ] P5.3 In-container config proof:
      `docker exec breaker-pipeline grep -n "breaker" /app/config/breaker.yaml` and
      `docker exec breaker-pipeline python -c "import breaker.platform.inference"`.
- [ ] P5.4 `./scripts/smoke_stream.sh` against the live stack (streaming change gate —
      the rename touches the Pipeline, so this is mandatory).

### Phase 6 — Verification ladder (Breaker)

| # | Command | Pass criterion |
|---|---|---|
| V1 | `uv run pytest tests/unit/ -q` | 0 failures |
| V2 | `uv run ruff check . && uv run ruff format --check .` | clean |
| V3 | `uv run mypy breaker/` (and `scripts/` per §5.3) | `Success: no issues` |
| V4 | `python3 scripts/complexity_report.py --gate` | no gated total over ceiling |
| V5 | `bash scripts/ci_local.sh` | green |
| V6 | `uv run python -m tests.wfe.settings_audit --behavioral` | every incumbent seat passes (baked context, persona pins, template honors `tools`/`think`) |
| V7 | `uv run python -m tests.qat --dry-run` then full `uv run python -m tests.qat` (stages 0→4) | all stages pass; live OWUI discovery from `config/breaker.yaml` |
| V8 | `uv run python scripts/nerc_autosync.py --emit-change-report` + `uv run python scripts/validation/compliance_currency.py` | register current; pre-service downgrade still WARN-only unless §5.4 checklist done |
| V9 | `uv run python -m tests.qat --stage uat` | Stage 5 conversational OWUI UAT green (human-grade journeys, output hygiene, verified serving model) |
| V10 | `uv run python scripts/hunt_bed/prove_universal_blind.py --all-proof --keys-dir /Volumes/data01/hunt_keys` | blind hunt smoke: proof indexes scored, zero keys read by the hunter, verdicts match the R3 baseline receipts |
| V11 | Leftover-reference sweep (P2.10 command) | only intentional historical hits remain |
| V12 | `launchctl list | grep -c com.breaker` / `grep com.portal5` | breaker agents loaded; portal5 agents booted out (Phase 7) |

### Phase 7 — Host cutover (operator, on the live host)

- [ ] P7.1 `launchctl bootout gui/$(id -u)/com.portal5.<each of the 38>` after the
      `com.breaker.*` twin of each is confirmed healthy; remove stale plists last.
- [ ] P7.2 Migrate or re-create data volumes (`breaker-hf-cache`, `breaker-lance`,
      `breaker-kb-sources`) — operator decision per §4.2; LanceDB re-ingest path is
      `scripts/rebuild_compliance_projections.py` + OWUI re-embed
      (`scripts/owui_reembed.py`).
- [ ] P7.3 Old `portal5-*` images: leave (Portal-5 checkout can still run standalone
      for rollback) — do not `docker rmi` until one full Breaker week is green.
- [ ] P7.4 Portal-5 repo: freeze on `main`, tag `v8.0.0-final`, mark archived in
      README. **Splunk `hb_*` indexes, `/Volumes/data01/hunt_keys/`, `/Volumes/data01/
      omlx-models`, `~/AI_Output/`, Ollama store untouched throughout — that is the
      continuity guarantee for the hunter.**

---

## 7. Risk register (what can go wrong, in order of likelihood)

1. **Compose project name flip** orphans nothing (fresh volumes are *intended*), but a
   stale `PORTAL_*` export in the operator's shell can silently point Breaker tooling
   at Portal-5 state — Phase 2.5 must end with `env | grep -i portal` empty on the host.
2. **`tests/benchmarks` imports** (§1.3): dropping it wholesale breaks the security
   matrix at runtime, not at import time (guarded by try/except — the failure mode is
   silent synthetic defaults, the worst kind). The reference grep in Phase 3.1 is
   load-bearing.
3. **Metric rename stranding dashboards**: if emitters rename before the JSONs (or
   only one side lands), Grafana panels render empty without erroring. Land
   P2.8 atomically; verify in the Grafana UI, not just `ruff`.
4. **LaunchAgent cutover half-state**: a `com.portal5.*` agent left loaded with
   rewritten script paths that no longer exist will crash-loop; bootout is per-label and
   reversible (bootout ≠ plist deletion, per `module_services.py` line 153).
5. **mypy scripts debt (2,850 findings)** is the largest single work item; if it does
   not land before v1.0 ships, the honest fallback is `scripts/_archive/`-style
   exclusion with an operator-approved `reason:` — never a complexity/mypy budget edit.
6. **Two live stacks in parallel** (rollback safety) is possible only because the
   compose project names differ; never run `docker compose down -v` on either.

---

*End of plan. Audited 2026-11-24 at portal-5 HEAD `729e219d5`; counts are receipts, not
estimates — re-derive any count that a later commit moves before executing its phase
(CLAUDE.md R12: never hardcode counts as prose in derived docs; this plan recomputes
its tables at execution time).*

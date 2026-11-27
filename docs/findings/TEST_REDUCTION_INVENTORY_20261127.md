# Test Reduction v2 — Inventory (2026-11-27)

Lane: `lane/test-reduce2` · Brief: `coding_task/BRIEF_TEST_REDUCTION_V2_20261127.md`
Measurement: `uv run python coding_task/measure_test_loc.py` (nonblank LOC; also reports
nonblank-nocomment, which matches v1's 108,690 figure to within 208 lines).

## Baseline (HEAD 1d1fc6241, = origin/main; v1 commit 92deb2041 not included)

| Group | files | nonblank LOC | nonblank-nocomment |
|---|---|---|---|
| tests/unit | 359 | 66,446 | 65,588 |
| tests/wfe | 113 | 33,506 | 32,686 |
| portal/**/tests | 101 | 10,985 | 10,624 |
| **TOTAL** | **573** | **110,937** | **108,898** |

Product nonblank LOC (portal/ minus tests): 202,072 → test:product ratio **0.5490**.
Baseline unit-suite runtime: `uv run pytest tests/unit/ -q` → **4147 passed, 46 skipped, 172.56 s**.

Scope note: `tests/wfe` is 30,009 LOC of **live WFE harness** (campaign/runner/checkers/suites/e2e
rigs, all referenced by live eval tooling and `portal/modules/compliance/core/eval_instance.py`)
plus 3,497 LOC of harness unit tests in `tests/wfe/tests/`. The harness itself is not test code
and is not deletable without breaking live WFE runs; only its unit tests are in the delete set.
`tests/qat` (incl. `tests/qat/tests/`, 7,590 LOC) is outside the measured scope and untouched.

## Protected contracts (brief §3) — where they live, all KEPT

- streaming deadline/heartbeat/repetition: `test_stream_pipeline_errors.py` (1,416),
  `test_stream_repetition_guard.py`, `test_stream_inband_error.py`, `test_stream_fallback.py`,
  `test_streaming_client*.py`, `test_pipeline_hardening.py` streaming classes.
- load_guard admission/eviction/working sets: `test_load_guard.py` (1,595),
  `test_load_guard_container_settings.py`, `test_load_guard_omlx_settle.py`, `test_router_placement.py`.
- routing/backends registry + reasoning_effort parity: `test_routing.py`, `test_backend_registry_health.py`,
  `test_omlx_backend.py`, `test_reasoning_effort.py`, `test_security_seat_reasoning_effort.py`,
  `test_thinking_channels.py`, `test_ollama_native.py`; WFE-side parity merged into
  `test_reasoning_effort.py` (see Merges); `test_seat_primary_matches_production.py` and
  `tests/wfe/tests/test_wfe_tool_modes.py` KEPT as routing/tool-exposure parity guards.
- QAT runner settle/liveness/preflight: `tests/qat/**` untouched; `test_bench_security_qat.py`,
  `test_uat_security.py` (host-quiet preflight) KEPT.
- tool exposure: `test_owui_tool_merge_dedup.py`, `test_channels.py`, `test_mcp_fleet_single_source.py`,
  `test_request_no_tools.py`, `test_require_tool_before_answer.py`, `test_required_tool_choice_retry.py`.
- failover tracing: `test_failover_protection_and_empty_hop.py`, `test_failover_window_floor.py`,
  `test_pipeline_hardening.py` failover classes, `test_turn_trace.py`, `test_trace_sections.py`.

## Delete inventory

Criteria codes: **SHAPE** = tests mocks/fixtures/shapes, not product behaviour (subject is
test/eval/bench harness code); **PROSE** = asserts doc/dashboard text or artifact shape;
**DUP** = duplicate of a test closer to the real contract; **ONEOFF** = one-off regression now
covered by a broader contract test. LOC = nonblank.

### Area 1 — prose / artifact-shape pins (tests/unit)

| file | LOC | covers | verdict |
|---|---|---|---|
| test_jarvis_docs_truth.py | 13 | asserts two sentences in JARVIS_LOCAL_RUNBOOK.md / ORCHESTRATION_ARM_OPERATORS.md stay corrected | DELETE PROSE |
| test_orchestrate_usage_dashboard.py | 236 | frozen SHA256 + panel-id/title/expr-count freeze of a Grafana dashboard JSON | DELETE SHAPE/PROSE (artifact freeze, re-frozen 2026-11-25; churn source, no product behaviour) |
| test_feature_traceability_completeness.py | 121 | drift lock on docs/FEATURE_QAT_TRACEABILITY_MATRIX.md phantom refs | DELETE PROSE (tool/persona alignment itself is covered by test_channels.py TestAllMCPServerToolAlignment, test_mcp_fleet_single_source.py, test_pipeline_image_personas.py) |

### Area 2 — WFE harness unit tests (subject = tests/wfe harness, not product)

| file | LOC | covers | verdict |
|---|---|---|---|
| tests/wfe/tests/test_wfe_checkers.py | 1,300 | checker soundness/gameability (WFE grading instruments) | DELETE SHAPE |
| tests/wfe/tests/test_wfe_contracts.py | 1,009 | harness tool-argument/stream-assembly/sampling/settings-audit contracts | DELETE SHAPE; one reasoning_effort parity test MERGED (below) |
| tests/wfe/tests/test_wfe_decision.py | 225 | harness decision rule case table | DELETE SHAPE |
| tests/wfe/tests/test_wfe_cells.py | 79 | cell matrix/baseline resolution | DELETE SHAPE |
| tests/wfe/tests/test_wfe_gold_isolation.py | 24 | gold-answer isolation | DELETE SHAPE |
| tests/wfe/tests/test_wfe_judge.py | 46 | blind pairwise judge mechanics | DELETE SHAPE |
| tests/wfe/tests/test_wfe_judge_compare.py | 17 | judge_compare, all mock | DELETE SHAPE |
| tests/wfe/tests/test_wfe_next_screens_slice.py | 74 | next-screen plan validation | DELETE SHAPE |
| tests/wfe/tests/test_wfe_office_contains.py | 196 | office_contains checker parsing | DELETE SHAPE |
| tests/wfe/tests/test_wfe_plan_suites.py | 106 | decision floor vs suite plans | DELETE SHAPE |
| tests/wfe/tests/test_wfe_prompt_surface.py | 73 | prompt-surface harness | DELETE SHAPE |
| tests/wfe/tests/test_wfe_publish.py | 43 | _publish collision-free writes | DELETE SHAPE |
| tests/wfe/tests/test_wfe_runner_timing_guard.py | 15 | malformed timing field guard | DELETE SHAPE |
| tests/wfe/tests/test_wfe_timing.py | 262 | runner/report timing payload parsing | DELETE SHAPE |
| tests/unit/test_wfe_exec_audit.py | 73 | harness _build_pipeline exec_audit/thinking_budget payloads + tool_grounded checker | DELETE SHAPE |
| tests/unit/test_wfe_surface_audit.py | 39 | surface-audit detectors on fixtures | DELETE SHAPE |
| tests/unit/test_wfe_production_smoke_cleanup.py | 8 | one-off smoke memory-note cleanup | DELETE ONEOFF |
| tests/unit/test_wfe_production_smoke_kb.py | 9 | one-off smoke empty-KB grading (finding F) | DELETE ONEOFF |
| tests/unit/test_seat_screen_intake_s8.py | 23 | s8 intake screen kit fixture parse | DELETE SHAPE |
| tests/unit/test_realuse_fixture_paths.py | 14 | realuse fixture readability | DELETE SHAPE |

KEPT in this cluster: `tests/wfe/tests/test_wfe_tool_modes.py` (28, production allowlist ⊆ workspace
tools — tool-exposure parity), `tests/unit/test_seat_primary_matches_production.py` (43, WFE seat ↔
production routing parity), `tests/unit/test_wfe_garble_probe.py` (46, live guard: no unprobed alias
onto the garbling mxfp8 conversion; referenced by KNOWN_LIMITATIONS unit), `tests/unit/test_eval_scope.py`
(163, product `router.eval_gate`), `tests/unit/test_bw_colon_ctx.py` (98, push-gate BW check).

### Area 3 — QAT/UAT harness + bench-library tests (duplicates of tests/qat/tests coverage)

| file | LOC | covers | verdict |
|---|---|---|---|
| tests/unit/test_uat_stage5_expansion.py | 604 | s5 journey definitions + marker graders on synthetic artifacts | DELETE SHAPE (journey/grader fixtures; scenarios themselves untouched) |
| tests/unit/test_uat_browser_driver.py | 546 | BrowserUI mechanics; playwright-missing preflight | DELETE SHAPE/DUP (preflight contract kept by tests/qat/tests/test_report_and_runner.py::test_browser_skip_without_playwright; client contracts by test_p0_contract_redesign.py) |
| tests/unit/test_uat_behavioral.py | 212 | docx/compliance graders, cross-session telemetry | DELETE DUP (tests/qat/tests/test_uat_behavioral.py, 2,084 LOC, covers the same graders closer to the QAT contract) |
| tests/unit/test_capability_lib.py | 111 | tests/benchmarks/capability_lib scorers | DELETE SHAPE |
| tests/unit/test_recall_scorer.py | 100 | tests/recall_scorer.py (a test helper) | DELETE SHAPE |

KEPT: `test_uat_security.py` (105, live runner host-quiet preflight), `test_bench_security_qat.py`
(173, protected QAT grading/trace gate).

### Area 4 — bench/eval/scorer-plane script tests (subject = measurement infrastructure)

| file | LOC | subject | verdict |
|---|---|---|---|
| test_speed_gate.py | 824 | scripts/speed_gate.py (speed bench) | DELETE SHAPE |
| test_speed_bench_pipeline_row.py | 568 | scripts/speed_bench.py row receipts | DELETE SHAPE |
| test_dflash_ab.py | 607 | scripts/dflash_ab.py (A/B bench) | DELETE SHAPE |
| test_dflash_ab_harness.py | 491 | one-off audit run 20261123T023745Z regression net | DELETE ONEOFF |
| test_bench_seat_ab.py | 586 | scripts/bench_seat_ab.py | DELETE SHAPE |
| test_security_sweep.py | 552 | scripts/security_sweep.py | DELETE SHAPE |
| test_bench_skip.py | 21 | bench skip-list mechanism | DELETE SHAPE |
| test_bench_concurrency_guard.py | 47 | bench lane max_concurrent config pin | DELETE SHAPE |
| test_prodpath.py | 185 | scripts/prodpath.py (bench production-path client) | DELETE SHAPE |
| test_media_screen_listen.py | 192 | scripts/proofs/media_screen_listen.py (model screen) | DELETE SHAPE |
| test_media_variant_screen.py | 335 | scripts/proofs/media_variant_screen*.py | DELETE SHAPE |
| test_prove_universal_blind.py | 406 | scripts/hunt_bed/prove_universal_blind.py (scorer plane) | DELETE SHAPE |
| test_corpus_truth_key.py | 171 | scripts/corpus_truth_key.py (answer-key builder) | DELETE SHAPE |
| test_keys_botsv2.py | 74 | scripts/hunt_bed/keys_botsv2.py (scorer keys) | DELETE SHAPE |
| test_lab_purple_capture.py | 443 | scripts/hunt_bed lab capture | DELETE SHAPE |
| test_lab_purple_sweep_catalog.py | 96 | config/lab_purple_sweep.yaml catalog shape | DELETE SHAPE |
| test_lab_vulhub_fleet_sweep.py | 148 | scripts/hunt_bed vulhub sweep orchestrator | DELETE SHAPE |
| test_hunt_canonical_ingest.py | 379 | scripts/hunt_bed/ingest_canonical.py + keys_flaws (scorer plane, never imported under portal/) | DELETE SHAPE |
| test_hunt_next_wave_ingest.py | 551 | scripts/hunt_bed next-wave ingest/keys; portal proof-index leak guard duplicated by test_hunt_knowledge.py::test_proof_indexes_cannot_enter_the_persistent_store | DELETE SHAPE/DUP |
| test_judgment_probe_instrument.py | 33 | bench_judgment_probe_v6 instrument fixes | DELETE ONEOFF |
| test_fara_probe_scoring.py | 34 | tests/benchmarks/bench_fara_cua_probe.py | DELETE SHAPE |

KEPT (product or live-ops subjects, verified by import): `test_seat_fit.py` (router.seat_fit),
`test_council_review_bench.py` (router.council), `test_candidate_eval.py` (security.core.candidate_eval),
`test_calibration_slice.py` (security.core.review), `test_tps_metrics.py` (router.metrics),
`test_splunk_setup.py` (lab SIEM deployment), `test_engine_install_plan.py` (engine installers),
`test_inkling2_repack.py` (live repack tool, receipt 2026-11-24), all launch/host/launchd/disk ops tests,
all `test_hunt_*` importing `portal.modules.security.core.hunt` (product hunt engine, 11.7k LOC),
`test_mawa_join*` (security.core.mawa), `test_lab_guard_shell_injection.py` (lab dispatch safety).

### Area 5 — one-off regression merges

| file | LOC | disposition |
|---|---|---|
| test_compliance_reasoning_v2_regressions.py | 157 | Verified per finding: F02 covered by test_compliance_v3_matrices.py::test_A05; F05 (both) by test_compliance_tiers.py (incomparable-units docstring cites F05); F06 and/or-swap by test_compliance_v3_matrices.py::test_A18 → those 5 tests DROP. NOT covered elsewhere: F01 historical-retired interval, F01 future-effective transition, F01 invalid-ISO rejection, F06 mixed-version rejection, F09 revoke-on-reject, F09 missing-target error → MERGE these 6 into test_compliance_engine.py (F01 ×3) and test_compliance_change_pipeline.py (F06 mixed, F09 ×2), delete file. Net ≈ −57. |

### Examined and KEPT (no criterion met)

- `test_model_catalog_parity.py` (168): live backends.yaml ↔ config/MODEL_CATALOG.md drift guard;
  the catalog itself cites this test as the reason entries exist. Config consistency, not prose.
- `test_overview_accuracy.py` (12): product metrics multiprocess mode.
- `test_chunking_5tuple.py` (16): char-offset correctness not asserted by any other chunking test.
- `test_compliance_v3_contract.py` (10): only AtomResult contract test.
- `test_compliance_mapping_store_consolidation.py` (15): store-path pin; cross-store visibility not
  proven elsewhere. Small; kept rather than risk the consolidation property.
- `test_pending_verdicts_evidence.py` (30): only coverage of scripts/pending_verdicts_evidence.py.
- Retired-model name scan (139 REMOVED_CLOSED identities × 573 files): every hit is a synthetic
  fixture string in a mocked config, not a pin on production seating — no deletions from this axis.
- Compliance cluster (70 files, 7,418), hunt product cluster (38 files, ~11.7k), pipeline/stream/
  load_guard/routing core (~9k), security module tests (10,985), jarvis (2.3k), orchestration arm
  (1.9k): product-behaviour tests, differentiated (31 duplicate test-name pairs checked, all
  distinct subjects), no criterion met.

## Merges (contract-preserving)

1. `tests/wfe/tests/test_wfe_contracts.py::TestAdaptiveThink::test_ollama_default_unchanged_by_engine_support`
   (WFE runner `_v1_think_fields` → `reasoning_effort:"none"` parity) → appended to
   `tests/unit/test_reasoning_effort.py` (the protected parity contract's best home).
2. `test_compliance_reasoning_v2_regressions.py`: 5 covered tests dropped; F01 ×3 →
   `test_compliance_engine.py`, F06 mixed-version + F09 ×2 → `test_compliance_change_pipeline.py`.

## Result vs target

Deleted: 50 files + 2 merge operations. See the lane commits for per-area gate output; final numbers and
runtime are recorded at the end of this file after the last area lands.

**Gap analysis (honest negative):** the brief's ≥20% (≥21,700-line) target is not reachable under
its own deletion criteria without cutting product-behaviour tests. The entire non-product surface
(WFE/QAT/bench/scorer harness tests + prose/shape pins + verified one-offs) sums to ~12.4k LOC
(~11.2%). The remaining ~9.3k would have to come from the protected or product clusters listed
above (hunt engine, compliance engine, security module, pipeline core) — each deletion there loses
a differentiated behaviour test, and several are live-proven contracts the brief forbids dropping.
Per WORKER_CONTRACT §0/§2 this lane reports the shortfall instead of tuning the delete set to hit
the number; the orchestrator decides whether to authorise specific product-cluster cuts or revise
the target.
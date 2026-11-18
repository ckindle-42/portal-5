# Phase 1c test trim — role `trim-bench-2`

Scope: `tests/benchmarks/` (24,799 `.py` lines at HEAD) and `tests/security/` second pass (13,307 `.py` lines at HEAD).

Rule applied: keep only bench/security harness code imported or executed by live bench/eval runs, and pytest tests meeting (1) pins a named live bug, (2) validates config/contracts the running system loads, or (3) pure logic with no I/O and no mocks. Delete retired/completed campaign harnesses, mocked/faked tests, offline E2E flows, duplicates, and tests of tooling scripts off the product path.

## Numbers

| scope | before (HEAD) | after | removed |
|---|---:|---:|---:|
| `tests/benchmarks/` (`.py`) | 81 files / 24,799 lines | 52 files / 16,873 lines | 29 files / 7,926 lines (-32.0%) |
| `tests/benchmarks/` (non-`.py` assets/fixtures) | 30 files / 1,935 lines | 26 files / 1,933 lines | 4 files (3 PNGs + 1 JSON) |
| `tests/security/` (`.py`) | 111 files / 13,307 lines | 96 files / 11,222 lines | 15 whole + 14 split / 2,085 lines (-15.7%) |
| **Total `.py` in scope** | **192 files / 38,106 lines** | **148 files / 28,095 lines** | **44 whole + 14 split / 10,011 lines (-26.3%)** |

> Note: >40% of scope lines are kept (73.7%) because 52 files (16,873 lines) in `tests/benchmarks/` are live bench/eval harness runners and shared libraries (`bench/`, `bench_repair/`, `bench_lab_exec.py`, `bench_omlx_v3.py`, `bench_judgment_probe_v6.py`, `bench_capability.py`, the 13 `bench_*_probe.py` drivers, `bench_router*.py`, `bench_tps.py`, etc.), and the remaining 92 pytest files in `tests/security/` are pure-logic or live-bug-pinning modules.

## Deleted whole files (44 `.py` files, 9,125 lines + 4 non-`.py` files)

| path | lines | why it fails the keep rule |
|---|---:|---|
| `tests/benchmarks/bench_cad_gauntlet.py` | 511 | superseded v1 CAD gauntlet (`bench_cad_gauntlet_v2.py` is live); zero code imports |
| `tests/benchmarks/bench_omlx_stress_extras.py` | 358 | one-off Aug 2026 stress follow-ups outside Phase-0 gate ladder; zero code imports |
| `tests/benchmarks/compliance_judgment_contract_v2.py` | 237 | scorer used only by the deleted R1 compliance judgment experiment scripts |
| `tests/benchmarks/compliance_judgment_r1_experiment.py` | 547 | historical R1 experiment on frozen holdout; zero code imports |
| `tests/benchmarks/compliance_judgment_r1_experiment_v2.py` | 651 | historical R1 v2 experiment on frozen holdout; zero code imports |
| `tests/benchmarks/eg2_runtime_measure.py` | 133 | one-off `:8946` vs `:11434` latency check from EG2 cutover; zero code imports |
| `tests/benchmarks/eg2_runtime_parity.py` | 143 | one-off `:8946` vs `:11434` parity check from EG2 cutover; zero code imports |
| `tests/benchmarks/embedding_consumers/__init__.py` | 7 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/__main__.py` | 3 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/cli.py` | 45 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/framework.py` | 518 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/gen_media.py` | 188 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/__init__.py` | 28 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/_common.py` | 217 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/attack_mapping.py` | 114 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/bully.py` | 356 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/compliance.py` | 271 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/harmful_intent.py` | 140 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/hygiene.py` | 589 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/media.py` | 488 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/memory.py` | 355 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/rag.py` | 542 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/refusal_classifier.py` | 171 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/router.py` | 200 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/seccode.py` | 425 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/security_text.py` | 184 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/tool_preselect.py` | 105 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/embedding_consumers/probes/wiki_search.py` | 111 | closed EG2 cutover campaign (`TASK_EG2_CUTOVER_V1` completed 2026-10-08; `:8917` retired; zero code imports) |
| `tests/benchmarks/prismml_mlx_server.py` | 289 | leftover adapter from closed `engine_h2h` evaluation (`7b26850f3`); zero code imports |
| `tests/security/bully/_discovery_fixtures.py` | 186 | `FixtureSnapshot` fake LanceDB helper used only by deleted/split `discovery_bench` tests |
| `tests/security/bully/test_discovery_bench_adoption.py` | 75 | tests tooling script `scripts.defensive_bully_p04_adoption` + `FixtureSnapshot` fake LanceDB |
| `tests/security/bully/test_hunt_sweep_h6_ci_invariants.py` | 57 | runs `scripts.validation.all_checks()` CI runner; duplicates `test_hunt_sweep_h4.py` |
| `tests/security/bully/test_investigation_a7_ci_invariants.py` | 30 | runs `scripts.validation.all_checks()` CI runner off product path |
| `tests/security/bully/test_investigation_i7_ci_invariants.py` | 73 | runs `scripts.validation.all_checks()` CI runner + duplicates `i1`/`i2` |
| `tests/security/bully/test_p1_6_investigation.py` | 102 | mocks `blue_orchestrate._run_three_section` with `unittest.mock.patch` + fake result |
| `tests/security/bully/test_relate_m2_ci_invariants.py` | 94 | runs `scripts.validation.all_checks()` CI runner + `_DenyingConnector` fake |
| `tests/security/bully/test_sa2_3_circularity.py` | 57 | offline E2E `discovery_bench` flow over `FixtureSnapshot` fake LanceDB |
| `tests/security/bully/test_sa2_4_cross_class.py` | 38 | offline E2E `discovery_bench` flow over `FixtureSnapshot` fake LanceDB |
| `tests/security/bully/test_scorer_feed_k5_ci_invariants.py` | 56 | runs `scripts.validation.all_checks()` CI runner + duplicates `test_starvation_k3.py` |
| `tests/security/bully/test_truth_y7_ci_invariants.py` | 36 | runs `scripts.validation.all_checks()` CI runner off product path |
| `tests/security/bully/test_unknown_m2_ci_invariants.py` | 99 | runs `scripts.validation.all_checks()` CI runner + tautological local checks |
| `tests/security/review/test_loader_contamination.py` | 49 | tests tooling script `scripts.load_attack_data_anchors` off product path |
| `tests/security/review/test_reader_tools.py` | 152 | uses `FakePivotSource` (fake Splunk) + `ScriptedClient` (fake LLM) |
| `tests/security/review_eval/test_runner_evidence_twins.py` | 95 | tests tooling script `scripts.review_eval_proof` off product path |
| `tests/benchmarks/assets/vision_probe_bars.png` | binary | unused asset for deleted `bench_omlx_stress_extras.py` |
| `tests/benchmarks/assets/vision_probe_shape.png` | binary | unused asset for deleted `bench_omlx_stress_extras.py` |
| `tests/benchmarks/assets/vision_probe_text.png` | binary | unused asset for deleted `bench_omlx_stress_extras.py` |
| `tests/benchmarks/fixtures/bonsai_quality/quality.json` | 2 | leftover fixture from closed `engine_h2h` evaluation (`7b26850f3`) |

## Split files (14 files, 886 lines removed)

| path | before | after | removed | what was removed | keep rule met by survivors |
|---|---:|---:|---:|---|---|
| `tests/security/bully/test_analyst_x4_concern_event.py` | 73 | 41 | 32 | removed `test_default_dispatcher_path_fires_concern_raised_not_promotion_queued` (`unittest.mock.patch` + `_FakeDispatcher`) | Rule 3 (pure `raise_concern` payload + `EventType` enum) |
| `tests/security/bully/test_corpus_bed_c1.py` | 160 | 128 | 32 | removed `test_stream_corpus_*` (`FakeConnector` mocking Splunk fetch) | Rule 1 + Rule 3 (D.4 regression + pure `assess_bed`/`bed_acceptance`/`plan_cousins`) |
| `tests/security/bully/test_discovery_bench_identity_diagnostic.py` | 93 | 65 | 28 | removed `test_identity_control_reports_classified_failures_and_thresholds` (`FixtureSnapshot` fake LanceDB) | Rule 3 (pure `classify_identity_failure` logic) |
| `tests/security/bully/test_hunt_sweep_h1.py` | 213 | 140 | 73 | removed 7 fake-lambda roundtrip / `FakeEntry` preflight tests | Rule 1 + Rule 3 (live-defect `already_done` + pure `calibrate_span`/`EntryProgress`) |
| `tests/security/bully/test_reintegration_r3_behavioral_signatures.py` | 63 | 25 | 38 | removed `_BehaviorSpineOnlySnapshot` fake KNN test | Rule 3 (pure `signatures.build_signature` logic) |
| `tests/security/bully/test_sa2_2_taxonomy.py` | 52 | 32 | 20 | removed `test_end_to_end_joint_scoring_on_fixture_corpus` (`FixtureSnapshot` offline E2E) | Rule 3 (pure `discovery_band` taxonomy logic) |
| `tests/security/bully/test_spl_detections_cloud.py` | 123 | 121 | 2 | removed `scripts.corpus_ingest` import and `INGESTED_SOURCETYPES` assertion | Rule 3 (pure `spl_detections`/`handoff` validation) |
| `tests/security/bully/test_universal_m5_ci_invariants.py` | 78 | 50 | 28 | removed `test_all_ten_invariants_registered_and_pass_clean` (`scripts.validation` runner) | Rule 1 + Rule 3 (RC1/RC4/RC5 pure-logic defect reproductions) |
| `tests/security/bully/test_unknown_u3_action_classifier.py` | 75 | 21 | 54 | removed `_StubClassifier` fake classifier seam tests | Rule 3 (pure `DeterministicActionClassifier` logic) |
| `tests/security/review/test_funnel_pipeline.py` | 250 | 58 | 192 | removed offline `pipeline.run` E2E flows with `HashEmbedder` fake embedder | Rule 3 (pure `funnel` decide/rank/split/baseline logic) |
| `tests/security/review/test_intake_knowledge.py` | 137 | 126 | 11 | removed `AnchorIndex` `HashEmbedder` test and `Fake` class | Rule 1 + Rule 3 (D-T2 `event_id` bug + pure intake/classifier logic) |
| `tests/security/review/test_judge.py` | 372 | 196 | 176 | removed `Scripted`/`Tools` mocked LLM and tool-loop tests (`run_judge`/`run_panel`) | Rule 3 (pure `parse_json_object`, `grounding`, `render_case`, `combine`, `panel_verdict`) |
| `tests/security/review/test_reader_guards.py` | 70 | 11 | 59 | removed `UncalledClient` / `streamer=stream` fake-transport tests | Rule 3 (pure `assert_prompt_label_free` guard) |
| `tests/security/review/test_store_verdicts.py` | 285 | 144 | 141 | removed offline `pipeline.review_window` maturation E2E cycles with `HashEmbedder` | Rule 1 + Rule 3 (pure in-memory `verdicts`/`ReviewStore` + `27302d8df` technique inheritance) |

## Kept files (148 `.py` files, 28,095 lines)

| path | lines | keep rule |
|---|---:|---|
| `tests/benchmarks/bench_lab_exec.py` | 1401 | Live bench/security harness imported by `portal/modules/security/core/*`, `detection_mcp`, `scripts/bench_supervisor.py`, `scripts/triage_actions.py` |
| `tests/benchmarks/bench_omlx_v3.py` | 1123 | Active oMLX Phase-0 upgrade gate (`docs/PUNCHLIST.md`) |
| `tests/benchmarks/bench_judgment_probe_v6.py` | 1079 | Live eval harness run by `scripts/compliance_y23_run.sh`, `scripts/compliance_y23_aggregate.py`, `tests/wfe/campaign.py` |
| `tests/benchmarks/bench_capability.py` | 1021 | Live capability bench run by `scripts/intent_eval.py` and imported by `bench_repair/` + `capability_lib` |
| `tests/benchmarks/bench_router_conditions.py` | 900 | Live router VRAM/eviction benchmark documented in `tests/benchmarks/README.md` and `docs/ADMIN_GUIDE.md` |
| `tests/benchmarks/bench_mbptl.py` | 823 | Live security bench harness imported by `tests/benchmarks/bench_lab_exec.py` |
| `tests/benchmarks/bench_candidates_v10.py` | 665 | Kept because `tests/unit/test_candidates_probe_max_tokens.py` (out of lane scope) imports it |
| `tests/benchmarks/bench_router.py` | 585 | Live router `GOLDEN_SET` benchmark documented in `tests/benchmarks/README.md` and `docs/ADMIN_GUIDE.md`; imported by `bench_router_conditions.py` |
| `tests/benchmarks/bench/runners.py` | 471 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/benchmarks/bench_cad_gauntlet_v2.py` | 459 | Live CAD gauntlet run by `scripts/run_cad_gauntlet_arm.sh` |
| `tests/benchmarks/bench/measure.py` | 439 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/benchmarks/bench_daily_soak.py` | 429 | Live daily fleet soak harness (maintained for current fleet in `1b5d6b1af`) |
| `tests/benchmarks/bench_research_probe.py` | 423 | Live intent-eval probe named by `scripts/intent_eval.py` |
| `tests/benchmarks/bench/cli.py` | 358 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/benchmarks/bench_security_exec_probe.py` | 343 | Live rebench probe named by `scripts/rebench_plan.py` |
| `tests/benchmarks/coding_shootout_analyze.py` | 339 | Live shootout analyzer imported by `tests/scripts/cc_challenge_matrix.py` |
| `tests/benchmarks/bench_reasoning_probe.py` | 336 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_tool_use_probe.py` | 331 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/benchmarks/bench/config.py` | 329 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_p1_5_cousin_engine.py` | 316 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench_vision_probe.py` | 307 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_omlx_soak.py` | 303 | Live oMLX soak harness (maintained for current fleet in `1b5d6b1af`) |
| `tests/benchmarks/bench_repair/cli.py` | 302 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/security/bully/test_hunt_sweep_h3.py` | 302 | Rule 1 (pins H5 rerun re-plant bug) |
| `tests/benchmarks/bench_cad_probe.py` | 274 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/security/bully/test_p3_1_mutation.py` | 268 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench_data_probe.py` | 265 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_refusal_preservation_probe.py` | 258 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/security/review_eval/test_claims.py` | 246 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_universal_e1_field_roles.py` | 237 | Rule 1 + Rule 3 (pins raw-KV profiling fix `6fe3b1d4a`; pure `infer_field_roles`) |
| `tests/benchmarks/bench_spl_probe.py` | 226 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/security/bully/test_conformance_w2.py` | 221 | Rule 1 (pins fix commit `01c4b55b6` scoreboard `candidate_state`/`known_benign`) |
| `tests/security/bully/test_investigation_i1.py` | 220 | Rule 1 + Rule 3 (pins live-run 26k-row trim fix `e77f73a83`; pure pivot chain) |
| `tests/benchmarks/bench_repair/runner.py` | 219 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/benchmarks/bench_compliance_probe.py` | 218 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_long_context_probe.py` | 216 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/security/bully/test_unknown_u1_artifact_graph.py` | 215 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_cousin_c1_relation.py` | 212 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_discovery_d1.py` | 210 | Rule 1 + Rule 3 (pins fix commit `8fbe6c862` answer-key containment; pure discovery) |
| `tests/benchmarks/bench_fara_cua_probe.py` | 206 | Live rebench probe named by `scripts/rebench_plan.py` |
| `tests/benchmarks/capability_lib.py` | 205 | Shared harness library imported by `portal/modules/security/core/*` and `tests/unit/test_capability_lib.py` |
| `tests/benchmarks/bench/discovery.py` | 203 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_adaptive_scope_a1.py` | 201 | Rule 1 + Rule 3 (pins I.6 flat `MAX_EVENTS` defect; pure `adaptive_scope` logic) |
| `tests/security/bully/test_unknown_v2_unit_outcome.py` | 196 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review/test_judge.py` | 196 | Rule 3 (pure `parse_json_object`, `grounding`, `render_case`, `combine`, `panel_verdict`) |
| `tests/security/bully/test_universal_m4_honest_metrics.py` | 190 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_full_assembly_f1.py` | 189 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_reintegration_r3b_correlation.py` | 186 | Rule 1 + Rule 3 (pins fix commit `358c05cda` identity overmerge; pure correlation) |
| `tests/security/bully/test_unknown_v1_unit_relation.py` | 181 | Rule 1 + Rule 3 (pins provenance exclusion fix `9539a6eab`; pure `unit_relation`) |
| `tests/security/bully/test_reintegration_r3c_series.py` | 180 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench/adhoc_probe.py` | 179 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_p1_3_evidence.py` | 178 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_real_telemetry_t1.py` | 175 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review_eval/test_attribution_decisions.py` | 170 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_truth_y4_quarantine_and_guard.py` | 166 | Rule 1 + Rule 3 (pins D4 scripted write-back poisoning; pure guard) |
| `tests/security/bully/test_p1_1_contracts.py` | 164 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench_mtp_probe.py` | 163 | Live intent/rebench probe named by `scripts/intent_eval.py` & `scripts/rebench_plan.py` |
| `tests/security/bully/test_corpus_bed_t2_guard_holes.py` | 162 | Rule 1 + Rule 3 (pins C.6 guard holes; pure `corpus_bed` validation) |
| `tests/security/bully/test_unknown_t4_leave_one_family_out.py` | 160 | Rule 1 + Rule 3 (pins recall denominator fix `9f41ea5c1`; pure LOFO metrics) |
| `tests/benchmarks/bench/lifecycle.py` | 155 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_corpus_bed_i4_cousin_time_range.py` | 150 | Rule 1 (pins fix commit `c4a39216d` + T.3 out-of-range cousin bug) |
| `tests/security/bully/test_cousin_c3_measurement_guards.py` | 148 | Rule 1 + Rule 3 (pins M.3 compounding/variance defect; pure measurement) |
| `tests/security/bully/test_behavior_inference_i1b.py` | 147 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review/test_store_verdicts.py` | 144 | Rule 1 + Rule 3 (pure in-memory `verdicts`/`ReviewStore` + `27302d8df` technique inheritance) |
| `tests/benchmarks/bench/report.py` | 141 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/review/_fakes.py` | 141 | Shared deterministic dict-record builder imported by `tests/unit/test_calibration_slice.py` and `tests/unit/test_review_event_time.py` (out of lane scope) |
| `tests/security/bully/test_hunt_sweep_h1.py` | 140 | Rule 1 + Rule 3 (live-defect `already_done` + pure `calibrate_span`/`EntryProgress`) |
| `tests/benchmarks/bench_repair/report.py` | 137 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/security/bully/test_score_sample_k1.py` | 137 | Rule 1 + Rule 3 (pins F.4 stratified-sample defect; pure `score_sample`) |
| `tests/security/bully/test_hunt_sweep_h2_anchor_time.py` | 135 | Rule 1 (pins live-verified `_anchor_for` index-earliest fallback) |
| `tests/security/bully/test_corpus_bed_a4_distance_planting.py` | 133 | Rule 1 + Rule 3 (pins I.6 distance-planting defect; pure `plan_cousins` logic) |
| `tests/benchmarks/cad_gauntlet_v2_oracles.py` | 132 | Live CAD gauntlet v2 oracle verifier (platform probe) |
| `tests/benchmarks/bench_mlx_hf.py` | 129 | Cited as live source in `KNOWN_LIMITATIONS.md` and 7 canonical wiki units (`test_spine_gates`/`test_detector_precision`) |
| `tests/security/bully/test_corpus_bed_c1.py` | 128 | Rule 1 + Rule 3 (D.4 regression + pure `assess_bed`/`bed_acceptance`/`plan_cousins`) |
| `tests/security/bully/test_unknown_m1_falsification_ladder.py` | 126 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review/test_intake_knowledge.py` | 126 | Rule 1 + Rule 3 (D-T2 `event_id` bug + pure intake/classifier logic) |
| `tests/security/bully/test_embedding_spaces_thresholds.py` | 125 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_reintegration_r5_universe.py` | 122 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_reintegration_r5c_behavior_classifier.py` | 122 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_spl_detections_cloud.py` | 121 | Rule 3 (pure `spl_detections`/`handoff` validation) |
| `tests/security/bully/test_hunt_sweep_h4.py` | 117 | Rule 1 + Rule 3 (pins K.4 zero-record stage claim defect; pure `ClaimEvidence`) |
| `tests/security/bully/test_scorer_feed_k2.py` | 116 | Rule 1 (pins fix commit `2f8f3ef2c` last-batch vs stratified sample) |
| `tests/security/bully/test_relate_g2_provenance_tiers.py` | 108 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench/notify.py` | 105 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/benchmarks/cad_grader.py` | 105 | CAD grader imported by `bench_cad_gauntlet_v2.py` |
| `tests/security/bully/test_behavior_values.py` | 104 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_i6_live_fidelity_fixes.py` | 100 | Rule 1 (pins fix commit `cee545204`/`b886de31d` Splunk `_time` + parser bug) |
| `tests/security/bully/test_truth_y2_observed_coverage.py` | 98 | Rule 1 + Rule 3 (pins D3 alignment coverage defect; pure `series_cousin`) |
| `tests/benchmarks/bench_tps.py` | 97 | Primary fleet TPS benchmark runner |
| `tests/security/bully/test_starvation_k3.py` | 97 | Rule 1 + Rule 3 (pins F.4 starvation profile; pure `starvation_check`) |
| `tests/security/bully/test_live_connect_i2_bounded_spl.py` | 95 | Rule 1 + Rule 3 (pins I.6 `host=` SPL defect; pure `_search_from_intent`) |
| `tests/security/bully/test_unknown_n2_baseline.py` | 94 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_relate_a1_anchors.py` | 93 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_corpus_bed_c6_blocked_conformance.py` | 92 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_unknown_l1_writeback_suppression.py` | 92 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_investigation_a2_adaptive_pivot.py` | 91 | Rule 1 + Rule 3 (pins I.6 `pivots:0` defect; pure `investigate` loop) |
| `tests/security/bully/test_truth_y3_priority_selection.py` | 90 | Rule 1 + Rule 3 (pins D2 priority selection defect; pure selection) |
| `tests/benchmarks/bench/prompts.py` | 88 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_universal_e3_blend.py` | 87 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_telemetry_behavior_i5_concentration.py` | 86 | Rule 1 + Rule 3 (pins T.3 suricata concentration defect; pure `coverage_report`) |
| `tests/security/review_eval/test_captures.py` | 86 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_corpus_bed_c4_fit_wide.py` | 84 | Rule 1 + Rule 3 (pins D.4 narrow-fit degeneracy; pure `NormalBaseline`/`discover`) |
| `tests/security/bully/test_corpus_bed_c3_capture.py` | 83 | Rule 1 (pins `capture_records` `portal5_lab`-only bug) |
| `tests/security/bully/test_unknown_t2_held_out_split.py` | 83 | Rule 1 + Rule 3 (pins anchor split contamination fix `9061b578e`; pure split) |
| `tests/security/bully/test_reintegration_r2_loop_grader.py` | 81 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_universal_u3_cross_vocabulary_ladder.py` | 81 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_unknown_t3_precision_recall.py` | 81 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_discovery_first_d2.py` | 80 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_analyst_x5_generator_classes.py` | 79 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_relate_g3_contamination_canary.py` | 79 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review_eval/test_traces.py` | 78 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/benchmarks/bench/results_io.py` | 77 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/security/bully/test_truth_y5_output_distribution.py` | 77 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_unknown_t1_grading_plane_legend.py` | 73 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_raw_kv_multipair.py` | 72 | Rule 1 + Rule 3 (pins `run-33f8f167db31` multi-pair KV bug `d6a957fd7`) |
| `tests/security/bully/test_universal_e4_baseline.py` | 72 | Rule 1 + Rule 3 (pins RC3 remarkability gap defect `1ff1e21ae`; pure baseline) |
| `tests/security/bully/test_conformance_w3.py` | 71 | Rule 1 (pins fix commit `c4336524a` scoreboard contract vs proxy) |
| `tests/security/bully/test_corpus_bed_a5_bed_guard.py` | 71 | Rule 1 + Rule 3 (pins I.6 zero-scored-units haystack defect; pure bed guard) |
| `tests/security/bully/test_reintegration_r1_pyramid.py` | 71 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_discovery_first_d3.py` | 70 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_unknown_n1_benign_types.py` | 69 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_investigation_a3_reach_chain.py` | 67 | Rule 1 + Rule 3 (pins I.6 single-entity reach defect; pure `reach_report`) |
| `tests/security/bully/test_relate_b1_ungated_intake.py` | 66 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_discovery_bench_identity_diagnostic.py` | 65 | Rule 3 (pure `classify_identity_failure` logic) |
| `tests/security/bully/test_soc_mld_instance_split.py` | 64 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_sa2_5_forge_demotion.py` | 62 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review_eval/test_folds.py` | 62 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_relate_g1_confidence_calibration.py` | 61 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/review/test_funnel_pipeline.py` | 58 | Rule 3 (pure `funnel` decide/rank/split/baseline logic) |
| `tests/security/bully/test_unknown_n3_likelihood_ratio.py` | 57 | Rule 1 + Rule 3 (pins N.3 attack-only IDF fix `66052ced1`; pure scoring) |
| `tests/benchmarks/bench_repair/__init__.py` | 54 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/benchmarks/bench_repair/config.py` | 53 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/benchmarks/bench_repair/checkpoint.py` | 51 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/security/bully/test_unknown_u2_unit_signature.py` | 51 | Rule 3 (pure logic, no I/O, no mocks) |
| `tests/security/bully/test_universal_m5_ci_invariants.py` | 50 | Rule 1 + Rule 3 (RC1/RC4/RC5 pure-logic defect reproductions) |
| `tests/benchmarks/bench_repair/corpus.py` | 43 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/security/bully/test_p1_0_config.py` | 42 | Rule 2 (validates live `config/portal.yaml` hunt/heart role-alias resolution) |
| `tests/security/bully/test_analyst_x4_concern_event.py` | 41 | Rule 3 (pure `raise_concern` payload + `EventType` enum) |
| `tests/benchmarks/bench_repair.py` | 39 | Live coding repair bench named by `scripts/intent_eval.py` & `config/bench_workspaces.yaml` |
| `tests/benchmarks/bench_security.py` | 33 | Live security bench shim imported by `portal/modules/security/core/*` & `scripts/rebench_plan.py` |
| `tests/security/bully/test_sa2_2_taxonomy.py` | 32 | Rule 3 (pure `discovery_band` taxonomy logic) |
| `tests/security/bully/test_reintegration_r3_behavioral_signatures.py` | 25 | Rule 3 (pure `signatures.build_signature` logic) |
| `tests/security/bully/test_unknown_u3_action_classifier.py` | 21 | Rule 3 (pure `DeterministicActionClassifier` logic) |
| `tests/benchmarks/bench/__init__.py` | 19 | Live TPS benchmark package (`tests/benchmarks/bench_tps.py`) |
| `tests/benchmarks/bench_repair/scoring.py` | 17 | Live coding repair benchmark package (`tests/benchmarks/bench_repair.py`, `scripts/intent_eval.py`) |
| `tests/security/review/test_reader_guards.py` | 11 | Rule 3 (pure `assert_prompt_label_free` guard) |
| `tests/security/review/__init__.py` | 0 | Package marker for `tests/security/review*` (checked by `HO. review_program`) |
| `tests/security/review_eval/__init__.py` | 0 | Package marker for `tests/security/review*` (checked by `HO. review_program`) |

## Consequences handled

- `portal_wiki/canonical/unit-design-embedding-consumers-harness.md`: replaced the 21 deleted `tests/benchmarks/embedding_consumers/...` source entries with `reports/embedding_consumers/EG2_CUTOVER.md` so `AJ` (`check_wiki_core`) remains green.
- `portal_wiki/canonical/unit-known-limitations-bully-discovery-truth-leak.md`: removed the deleted `tests/security/bully/_discovery_fixtures.py` source entry so `AJ` remains green.
- `portal_wiki/canonical/unit-code-scripts.md`: removed the deleted `tests/benchmarks/prismml_mlx_server.py` source entry (and its stale bullet alongside the already-deleted `test_prismml_mlx_server.py`) so `AJ` remains green.

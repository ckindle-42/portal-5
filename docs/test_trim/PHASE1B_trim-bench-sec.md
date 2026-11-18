# Phase-1b test trim — lane `trim-bench-sec`

Scope: `tests/benchmarks/`, `tests/security/`, and the `tests/` top-level leftovers
(`tests/_archive`, `tests/_archive_execdocs`, `tests/comfyui`, `*.bak`).

Rule applied (brief §The rule): keep only (1) tests that pin a named live bug, (2) tests that
validate config/contracts the running system loads, (3) pure logic with no I/O and no mocks.
Everything else in scope is deleted. Classification is mechanical: a file is a keeper only when
it imports no mock/patch surface (`unittest.mock`, `monkeypatch`), no transport (`httpx`,
`subprocess`, `urllib`, `socket`, `asyncio`), no `sqlite3`, and touches no file at all — not
`tmp_path`, not repo source, not run artifacts. Keeper status was then overridden *upwards* only
where the test or its introducing commit names a live bug.

## Numbers

| property | before (HEAD) | after |
| --- | --- | --- |
| `.py` files in `tests/benchmarks` + `tests/security` | 249 | 192 |
| `.py` lines in the same two trees | 48 504 | 38 105 |
| pytest test files in those trees | 157 | 107 |
| pytest test lines in those trees | 22 049 | 12 979 |
| files deleted by this commit | — | 74 (57 `.py`, 17 docs/`.bak`) |
| lines deleted by this commit | — | 16 490 (10 399 `.py`, 6 091 docs) |

The commit also carries the phase-1 document deletions (17 files, 6 091 lines): nothing had been
committed on this lane before this run.

## Deleted — pytest test files

| file | lines | why it fails the keep rule |
| --- | --- | --- |
| `tests/security/bully/test_p2_1_bin_tables.py` | 409 | writes a sqlite store (file I/O, not pure logic); writes files under `tmp_path` |
| `tests/security/review/test_defense.py` | 392 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/bully/test_p6_1_store.py` | 380 | writes a sqlite store (file I/O, not pure logic); writes files under `tmp_path` |
| `tests/security/bully/test_p5_2_handoff.py` | 370 | writes files under `tmp_path` |
| `tests/security/review/test_runtime.py` | 366 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); drives an httpx client; writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_p5_1_store.py` | 347 | writes a sqlite store (file I/O, not pure logic); writes files under `tmp_path` |
| `tests/security/bully/test_hunt_sweep_h2.py` | 327 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_p1_2_store.py` | 323 | writes a sqlite store (file I/O, not pure logic); writes files under `tmp_path` |
| `tests/security/review/test_io_adapters.py` | 321 | drives an httpx client; writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path`; urllib transport |
| `tests/security/review_eval/test_truth_runner.py` | 292 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_truth.py` | 282 | writes files under `tmp_path` |
| `tests/security/bully/test_universal_e5_inject_plane.py` | 267 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path` |
| `tests/security/bully/test_anchor_spine_content.py` | 266 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_p1_4_organ.py` | 264 | drives an httpx client; writes files under `tmp_path` |
| `tests/security/review_eval/test_mixed_harness.py` | 251 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_selftest_report_wall.py` | 244 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_boundaries.py` | 239 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_sa3_4_discovery_seed.py` | 200 | drives an httpx client; writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_conformance_w1.py` | 193 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_truth_audit.py` | 192 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review/test_service_knowledge.py` | 175 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/bully/test_p7_4_retrieval_validity.py` | 167 | writes files under `tmp_path` |
| `tests/security/bully/test_sa3_5_discovery_bakeoff.py` | 164 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); drives an httpx client; writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_corpus_bed_c5_cousin_inject.py` | 149 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/review/test_prune_ledger.py` | 146 | spawns a subprocess; writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_p6_8_cousin_calibration.py` | 141 | writes files under `tmp_path` |
| `tests/security/bully/test_inject_plane_i3_capture_investigation.py` | 139 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/review_eval/test_stamp_metrics.py` | 139 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review/test_wall_calibration_content.py` | 134 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review/test_state_renderer.py` | 128 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_hec_ship_timestamps.py` | 119 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path` |
| `tests/security/review/test_adapters.py` | 109 | drives an httpx client |
| `tests/security/bully/test_reintegration_r5a_live_chains.py` | 107 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path` |
| `tests/security/review/test_surfaces.py` | 107 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path`; asyncio transport |
| `tests/security/bully/test_truth_y1_acceptance.py` | 106 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_proof.py` | 103 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_sa7_l1_live_connect.py` | 101 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path` |
| `tests/security/bully/test_sa2_1_real_pairs.py` | 97 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/review/test_runs.py` | 97 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_conformance_w5.py` | 95 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review/test_invariants.py` | 93 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_conformance_w4.py` | 82 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_analyst_x2_store.py` | 79 | writes files under `tmp_path` |
| `tests/security/bully/test_truth_y6_json_raw_parsing.py` | 62 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_corpus_ingest_index.py` | 61 | mocks/patches I/O (`unittest.mock`, `monkeypatch`); writes files under `tmp_path` |
| `tests/security/bully/test_full_assembly_f2.py` | 56 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/bully/test_full_assembly_f3.py` | 54 | reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_arms.py` | 53 | mocks/patches I/O (`unittest.mock`, `monkeypatch`) |
| `tests/security/review_eval/test_bots_truth_key.py` | 52 | writes files under `tmp_path`; reads repo source or run artifacts outside `tmp_path` |
| `tests/security/review_eval/test_runner_one_path.py` | 30 | reads repo source or run artifacts outside `tmp_path` |

## Deleted — unreferenced scripts and the phase-1 test deletion

These are not pytest tests. Each is named by nothing in the repository: no `portal/` import,
no script, no config, no wiki unit, no other test (checked with a whole-repo substring scan over
every tracked file except the file's own `__pycache__` entries).

| file | lines | why |
| --- | --- | --- |
| `tests/benchmarks/bench_cad_probe.DEEPWEN_FOLLOWUP_001.py` | 333 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/bench_window_seat_sweep.py` | 210 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/compare_cad_gauntlet.py` | 124 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/compliance_stream_p0_live_capture.py` | 221 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/compliance_stream_p3c_assess_part_live.py` | 309 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/notify_soak_complete.py` | 65 | unreferenced one-off/campaign script living under `tests/` |
| `tests/benchmarks/test_empty_retry.py` | 67 | re-implements the guard it claims to test against a stub it builds itself; imports nothing from `portal/` |

## Deleted — stale documents

| file | lines | why |
| --- | --- | --- |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V2.md` | 1117 | superseded by V5 |
| `tests/_archive_execdocs/TASK_BENCH_EXECUTE_V7_UPDATE.md` | 825 | task doc for a bench generation that no longer exists |
| `tests/_archive_execdocs/ACCEPTANCE_TEST_GUIDE.md` | 620 | guide for archived acceptance generations; V9 is live |
| `tests/_archive/PORTAL5_UAT_EXECUTE_V1.md` | 552 | archived copy of the execute prompt; the live doc is `PORTAL5_UAT_EXECUTE_V5.md` |
| `tests/_archive_execdocs/PORTAL5_ACCEPTANCE_EXECUTE_V6.md` | 548 | superseded by `tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md` |
| `tests/_archive_execdocs/PORTAL5_BENCH_EXECUTE_V1.md` | 420 | superseded by `tests/PORTAL5_BENCH_EXECUTE_V4.md` |
| `tests/_archive_execdocs/PORTAL5_PROMPT_V6.md` | 397 | superseded prompt generation (V9 live) |
| `tests/UAT_RESULTS_20260728_pre_rerun2.md.bak` | 313 | same supersession, zero references |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V4.md` | 278 | superseded by V5 |
| `tests/UAT_RESULTS_20260727_pre_rerun_failed.md.bak` | 271 | same supersession, zero references |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V3.md` | 218 | superseded by V5 |
| `tests/_archive_execdocs/PORTAL5_BENCH_EXECUTE_V2.md` | 202 | superseded by V4 |
| `tests/_archive_execdocs/ROUTING_FALLBACK_ANALYSIS.md` | 159 | point-in-time analysis inside an archived directory; the fallback is pinned by live unit tests |
| `tests/_archive_execdocs/PORTAL5_ACCEPTANCE_EXECUTE_V7.md` | 96 | superseded by V9 |
| `tests/UAT_RESULTS_20260726_partial.md.bak` | 35 | July-2026 UAT snapshot superseded by `tests/UAT_RESULTS.md` + `UAT_RUN_LOG.md`; zero references |
| `tests/benchmarks/COVERAGE_AUDIT_2026-06-26.md` | 34 | point-in-time snapshot against HEAD `be20f14`; its counts are now derived live by `portal config show` |
| `tests/_archive_execdocs/README.md` | 6 | README of the archive directory itself |

## Kept — pytest tests that pin a named live bug (rule 1)

Each of these also carries mock or file I/O, which alone would delete it; rule 1 overrides.

| file | lines | the bug it pins |
| --- | --- | --- |
| `tests/security/bully/test_conformance_w2.py` | 221 | fix commit 01c4b55b6 — 'scoreboard fed real candidate_state and known_benign' |
| `tests/security/bully/test_conformance_w3.py` | 71 | fix commit c4336524a — 'run publishes the scoreboard contract, discovery_bubbled_rate deleted' |
| `tests/security/bully/test_corpus_bed_c3_capture.py` | 83 | docstring names the bug: capture_records read portal5_lab only, so BOTS was invisible |
| `tests/security/bully/test_corpus_bed_i4_cousin_time_range.py` | 150 | fix commit c4a39216d + T.3 defect: cousins were shipped ~8 years outside every BOTS index |
| `tests/security/bully/test_hunt_sweep_h2_anchor_time.py` | 135 | live-verified defect: `_anchor_for` fell back to index-earliest for all 27 answer-key entries |
| `tests/security/bully/test_hunt_sweep_h3.py` | 302 | H5 follow-up bug: a rerun re-shipped 8 already-planted cousins because the plant record was erased |
| `tests/security/bully/test_i6_live_fidelity_fixes.py` | 99 | fix commit cee545204 + live-verified: every real record's client-side `_time` was silently 'now' |
| `tests/security/bully/test_scorer_feed_k2.py` | 116 | fix commit 2f8f3ef2c — analytical path received the last batch, not a stratified sample |

## Kept — pure logic, no I/O, no mocks (rule 3)

Every file below: no `unittest.mock`/`monkeypatch`, no transport import, no `sqlite3`, and no
file access of any kind (no `open(`, no `read_text`, no `Path(`, no `tmp_path`) — values in,
assertions on returned values.

| file | lines |
| --- | --- |
| `tests/security/bully/test_adaptive_scope_a1.py` | 201 |
| `tests/security/bully/test_analyst_x4_concern_event.py` | 73 |
| `tests/security/bully/test_analyst_x5_generator_classes.py` | 79 |
| `tests/security/bully/test_behavior_inference_i1b.py` | 147 |
| `tests/security/bully/test_behavior_values.py` | 104 |
| `tests/security/bully/test_corpus_bed_a4_distance_planting.py` | 133 |
| `tests/security/bully/test_corpus_bed_a5_bed_guard.py` | 71 |
| `tests/security/bully/test_corpus_bed_c1.py` | 160 |
| `tests/security/bully/test_corpus_bed_c4_fit_wide.py` | 84 |
| `tests/security/bully/test_corpus_bed_c6_blocked_conformance.py` | 92 |
| `tests/security/bully/test_corpus_bed_t2_guard_holes.py` | 162 |
| `tests/security/bully/test_cousin_c1_relation.py` | 212 |
| `tests/security/bully/test_cousin_c3_measurement_guards.py` | 148 |
| `tests/security/bully/test_discovery_bench_adoption.py` | 75 |
| `tests/security/bully/test_discovery_bench_identity_diagnostic.py` | 93 |
| `tests/security/bully/test_discovery_d1.py` | 210 |
| `tests/security/bully/test_discovery_first_d2.py` | 80 |
| `tests/security/bully/test_discovery_first_d3.py` | 70 |
| `tests/security/bully/test_embedding_spaces_thresholds.py` | 125 |
| `tests/security/bully/test_full_assembly_f1.py` | 189 |
| `tests/security/bully/test_hunt_sweep_h1.py` | 213 |
| `tests/security/bully/test_hunt_sweep_h4.py` | 117 |
| `tests/security/bully/test_hunt_sweep_h6_ci_invariants.py` | 57 |
| `tests/security/bully/test_investigation_a2_adaptive_pivot.py` | 91 |
| `tests/security/bully/test_investigation_a3_reach_chain.py` | 67 |
| `tests/security/bully/test_investigation_a7_ci_invariants.py` | 30 |
| `tests/security/bully/test_investigation_i1.py` | 220 |
| `tests/security/bully/test_investigation_i7_ci_invariants.py` | 73 |
| `tests/security/bully/test_live_connect_i2_bounded_spl.py` | 95 |
| `tests/security/bully/test_p1_0_config.py` | 42 |
| `tests/security/bully/test_p1_1_contracts.py` | 164 |
| `tests/security/bully/test_p1_3_evidence.py` | 178 |
| `tests/security/bully/test_p1_5_cousin_engine.py` | 316 |
| `tests/security/bully/test_p1_6_investigation.py` | 102 |
| `tests/security/bully/test_p3_1_mutation.py` | 268 |
| `tests/security/bully/test_raw_kv_multipair.py` | 72 |
| `tests/security/bully/test_real_telemetry_t1.py` | 175 |
| `tests/security/bully/test_reintegration_r1_pyramid.py` | 71 |
| `tests/security/bully/test_reintegration_r2_loop_grader.py` | 81 |
| `tests/security/bully/test_reintegration_r3_behavioral_signatures.py` | 63 |
| `tests/security/bully/test_reintegration_r3b_correlation.py` | 186 |
| `tests/security/bully/test_reintegration_r3c_series.py` | 180 |
| `tests/security/bully/test_reintegration_r5_universe.py` | 122 |
| `tests/security/bully/test_reintegration_r5c_behavior_classifier.py` | 122 |
| `tests/security/bully/test_relate_a1_anchors.py` | 93 |
| `tests/security/bully/test_relate_b1_ungated_intake.py` | 66 |
| `tests/security/bully/test_relate_g1_confidence_calibration.py` | 61 |
| `tests/security/bully/test_relate_g2_provenance_tiers.py` | 108 |
| `tests/security/bully/test_relate_g3_contamination_canary.py` | 79 |
| `tests/security/bully/test_relate_m2_ci_invariants.py` | 94 |
| `tests/security/bully/test_sa2_2_taxonomy.py` | 52 |
| `tests/security/bully/test_sa2_3_circularity.py` | 57 |
| `tests/security/bully/test_sa2_4_cross_class.py` | 38 |
| `tests/security/bully/test_sa2_5_forge_demotion.py` | 62 |
| `tests/security/bully/test_score_sample_k1.py` | 137 |
| `tests/security/bully/test_scorer_feed_k5_ci_invariants.py` | 56 |
| `tests/security/bully/test_soc_mld_instance_split.py` | 64 |
| `tests/security/bully/test_spl_detections_cloud.py` | 123 |
| `tests/security/bully/test_starvation_k3.py` | 97 |
| `tests/security/bully/test_telemetry_behavior_i5_concentration.py` | 86 |
| `tests/security/bully/test_truth_y2_observed_coverage.py` | 98 |
| `tests/security/bully/test_truth_y3_priority_selection.py` | 90 |
| `tests/security/bully/test_truth_y4_quarantine_and_guard.py` | 166 |
| `tests/security/bully/test_truth_y5_output_distribution.py` | 77 |
| `tests/security/bully/test_truth_y7_ci_invariants.py` | 36 |
| `tests/security/bully/test_universal_e1_field_roles.py` | 237 |
| `tests/security/bully/test_universal_e3_blend.py` | 87 |
| `tests/security/bully/test_universal_e4_baseline.py` | 72 |
| `tests/security/bully/test_universal_m4_honest_metrics.py` | 190 |
| `tests/security/bully/test_universal_m5_ci_invariants.py` | 78 |
| `tests/security/bully/test_universal_u3_cross_vocabulary_ladder.py` | 81 |
| `tests/security/bully/test_unknown_l1_writeback_suppression.py` | 92 |
| `tests/security/bully/test_unknown_m1_falsification_ladder.py` | 126 |
| `tests/security/bully/test_unknown_m2_ci_invariants.py` | 99 |
| `tests/security/bully/test_unknown_n1_benign_types.py` | 69 |
| `tests/security/bully/test_unknown_n2_baseline.py` | 94 |
| `tests/security/bully/test_unknown_n3_likelihood_ratio.py` | 57 |
| `tests/security/bully/test_unknown_t1_grading_plane_legend.py` | 73 |
| `tests/security/bully/test_unknown_t2_held_out_split.py` | 83 |
| `tests/security/bully/test_unknown_t3_precision_recall.py` | 81 |
| `tests/security/bully/test_unknown_t4_leave_one_family_out.py` | 160 |
| `tests/security/bully/test_unknown_u1_artifact_graph.py` | 215 |
| `tests/security/bully/test_unknown_u2_unit_signature.py` | 51 |
| `tests/security/bully/test_unknown_u3_action_classifier.py` | 75 |
| `tests/security/bully/test_unknown_v1_unit_relation.py` | 181 |
| `tests/security/bully/test_unknown_v2_unit_outcome.py` | 196 |
| `tests/security/review/test_funnel_pipeline.py` | 250 |
| `tests/security/review/test_intake_knowledge.py` | 137 |
| `tests/security/review/test_judge.py` | 372 |
| `tests/security/review/test_loader_contamination.py` | 49 |
| `tests/security/review/test_reader_guards.py` | 70 |
| `tests/security/review/test_reader_tools.py` | 152 |
| `tests/security/review/test_store_verdicts.py` | 285 |
| `tests/security/review_eval/test_attribution_decisions.py` | 170 |
| `tests/security/review_eval/test_captures.py` | 86 |
| `tests/security/review_eval/test_claims.py` | 246 |
| `tests/security/review_eval/test_folds.py` | 62 |
| `tests/security/review_eval/test_runner_evidence_twins.py` | 95 |
| `tests/security/review_eval/test_traces.py` | 78 |

## Kept — everything else in scope (not pytest tests)

91 non-test `.py` files (26 388 lines at HEAD, ~25 100 after the six script deletions) stay.
They are the live exercisers and their harness: probes named as re-bench commands by
`scripts/rebench_plan.py` / `scripts/intent_eval.py`, the `bench/`, `bench_repair/` and
`embedding_consumers/` harness modules those probes and several `portal/` modules load, and the
two test helper modules still imported by kept tests (`tests/security/review/_fakes.py`,
`tests/security/bully/_discovery_fixtures.py`). This lane did not judge them against the keep
rule because the rule is written for tests; if the operator wants this quarter of the tree cut
too, it needs its own brief (see Open).

| file | lines | keep reason |
| --- | --- | --- |
| `tests/benchmarks/bench/__init__.py` | 19 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench/cli.py` | 358 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench/config.py` | 329 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/bench/discovery.py` | 203 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py`, `scripts/bully_analyst_loop_run.py` |
| `tests/benchmarks/bench/lifecycle.py` | 155 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/compliance/diagnose_dead_standards.py` |
| `tests/benchmarks/bench/measure.py` | 439 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/bench/notify.py` | 105 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py`, `scripts/bully_analyst_loop_run.py` |
| `tests/benchmarks/bench/prompts.py` | 88 | live exerciser — named by `scripts/_archive/engine_h2h_20260924/deep_lane/run_deep.py`, `scripts/check_owui_preset_drift.py` |
| `tests/benchmarks/bench/report.py` | 141 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/bench/runners.py` | 471 | live exerciser — named by `scripts/validation/orchestration_arm.py` |
| `tests/benchmarks/bench_cad_probe.py` | 274 | live exerciser — named by `scripts/compliance/write_closeout_report.py`, `scripts/intent_eval.py` |
| `tests/benchmarks/bench_capability.py` | 1021 | live exerciser — named by `scripts/intent_eval.py` |
| `tests/benchmarks/bench_compliance_probe.py` | 218 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_data_probe.py` | 265 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_fara_cua_probe.py` | 206 | live exerciser — named by `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_judgment_probe_v6.py` | 1079 | live exerciser — named by `scripts/compliance_y23_aggregate.py` |
| `tests/benchmarks/bench_lab_exec.py` | 1401 | live exerciser — named by `scripts/bench_supervisor.py`, `scripts/triage_actions.py` |
| `tests/benchmarks/bench_long_context_probe.py` | 216 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_mtp_probe.py` | 163 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_reasoning_probe.py` | 336 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_refusal_preservation_probe.py` | 258 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_repair.py` | 39 | live exerciser — named by `scripts/intent_eval.py` |
| `tests/benchmarks/bench_repair/__init__.py` | 54 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench_repair/checkpoint.py` | 51 | live exerciser — named by `scripts/bench_supervisor.py`, `scripts/bully_full_assembly_run.py` |
| `tests/benchmarks/bench_repair/cli.py` | 302 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench_repair/config.py` | 53 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/bench_repair/corpus.py` | 43 | live exerciser — named by `scripts/acquire_corpus_sources.py`, `scripts/anchor_requirements.py` |
| `tests/benchmarks/bench_repair/report.py` | 137 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/bench_repair/runner.py` | 219 | live exerciser — named by `scripts/arm_shadow_batch.py`, `scripts/compliance/pipeline_alignment_verify.py` |
| `tests/benchmarks/bench_repair/scoring.py` | 17 | live exerciser — named by `scripts/bully_full_assembly_run.py`, `scripts/compliance/truth/evidence_delivery.py` |
| `tests/benchmarks/bench_research_probe.py` | 423 | live exerciser — named by `scripts/intent_eval.py` |
| `tests/benchmarks/bench_security.py` | 33 | live exerciser — named by `scripts/lab_targets.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_security_exec_probe.py` | 343 | live exerciser — named by `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_spl_probe.py` | 226 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_tool_use_probe.py` | 331 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/bench_tps.py` | 97 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench_vision_probe.py` | 307 | live exerciser — named by `scripts/intent_eval.py`, `scripts/rebench_plan.py` |
| `tests/benchmarks/embedding_consumers/__init__.py` | 7 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/embedding_consumers/__main__.py` | 3 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/embedding_consumers/cli.py` | 45 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/embedding_consumers/framework.py` | 518 | live exerciser — named by `scripts/omlx_venv_install.py`, `scripts/pending_verdicts_report.py` |
| `tests/benchmarks/embedding_consumers/probes/__init__.py` | 28 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/embedding_consumers/probes/_common.py` | 217 | live exerciser — named by `scripts/cam_lds_extract.py`, `scripts/compliance/truth/operator_text_audit.py` |
| `tests/benchmarks/embedding_consumers/probes/attack_mapping.py` | 114 | live exerciser — named by `scripts/bully_analyst_loop_run.py`, `scripts/bully_loop_milestone_run.py` |
| `tests/benchmarks/embedding_consumers/probes/bully.py` | 356 | live exerciser — named by `scripts/build_specimen_corpus_v3.py`, `scripts/bully_analyst_loop_run.py` |
| `tests/benchmarks/embedding_consumers/probes/compliance.py` | 271 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/anchor_requirements.py` |
| `tests/benchmarks/embedding_consumers/probes/hygiene.py` | 589 | live exerciser — named by `scripts/validate_system.py`, `scripts/validation/__init__.py` |
| `tests/benchmarks/embedding_consumers/probes/media.py` | 488 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/embedding_consumers/probes/memory.py` | 355 | live exerciser — named by `scripts/_archive/analyze_bench_v5.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` |
| `tests/benchmarks/embedding_consumers/probes/rag.py` | 542 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py`, `scripts/bench_supervisor.py` |
| `tests/benchmarks/embedding_consumers/probes/router.py` | 200 | live exerciser — named by `scripts/alias_census.py`, `scripts/compliance/ask_conversational.py` |
| `tests/benchmarks/embedding_consumers/probes/wiki_search.py` | 111 | live exerciser — named by `scripts/validation/wiki.py` |
| `tests/security/review/__init__.py` | 0 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/security/review_eval/__init__.py` | 0 | live exerciser — named by `scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`, `scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py` |
| `tests/benchmarks/bench/adhoc_probe.py` | 179 | harness/library module — not a pytest test |
| `tests/benchmarks/bench/results_io.py` | 77 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_cad_gauntlet.py` | 511 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_cad_gauntlet_v2.py` | 459 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_candidates_v10.py` | 665 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_daily_soak.py` | 429 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_mbptl.py` | 823 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_mlx_hf.py` | 129 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_omlx_soak.py` | 303 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_omlx_stress_extras.py` | 358 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_omlx_v3.py` | 1123 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_router.py` | 585 | harness/library module — not a pytest test |
| `tests/benchmarks/bench_router_conditions.py` | 900 | harness/library module — not a pytest test |
| `tests/benchmarks/cad_gauntlet_v2_oracles.py` | 132 | harness/library module — not a pytest test |
| `tests/benchmarks/cad_grader.py` | 105 | harness/library module — not a pytest test |
| `tests/benchmarks/capability_lib.py` | 205 | harness/library module — not a pytest test |
| `tests/benchmarks/coding_shootout_analyze.py` | 339 | harness/library module — not a pytest test |
| `tests/benchmarks/compliance_judgment_contract_v2.py` | 237 | harness/library module — not a pytest test |
| `tests/benchmarks/compliance_judgment_r1_experiment.py` | 547 | harness/library module — not a pytest test |
| `tests/benchmarks/compliance_judgment_r1_experiment_v2.py` | 651 | harness/library module — not a pytest test |
| `tests/benchmarks/eg2_runtime_measure.py` | 133 | harness/library module — not a pytest test |
| `tests/benchmarks/eg2_runtime_parity.py` | 143 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/gen_media.py` | 188 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/probes/harmful_intent.py` | 140 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/probes/refusal_classifier.py` | 171 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/probes/seccode.py` | 425 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/probes/security_text.py` | 184 | harness/library module — not a pytest test |
| `tests/benchmarks/embedding_consumers/probes/tool_preselect.py` | 105 | harness/library module — not a pytest test |
| `tests/benchmarks/prismml_mlx_server.py` | 289 | harness/library module — not a pytest test |
| `tests/security/bully/_discovery_fixtures.py` | 186 | harness/library module — not a pytest test |
| `tests/security/review/_fakes.py` | 141 | harness/library module — not a pytest test |

## Consequences handled in this commit

- `portal/modules/security/core/bully/store.py`, `.../bully/mutation.py` and
  `portal/modules/security/core/review/constants.py` each named the deleted
  `test_boundaries.py` / `test_invariants.py` scan tests in a module docstring. One sentence per
  module was rewritten so no product docstring points at a path that no longer exists.
- `portal_wiki/canonical/unit-capability-review.md` cited
  `tests/security/review/test_runtime.py` as a source. Deleting the file made check
  `check_wiki_core` FAIL with `unit-capability-review: missing-source (...)` — the citation was
  removed from the unit's `sources:` list (its other eight sources and its claims are untouched).

## Not done — needs an operator decision

- `python3 scripts/complexity_report.py --gate` FAILS on one metric:
  `unwired_scripts: 28 > ceiling 25`. It was 24 at HEAD (headroom 1). Four `scripts/` files lost
  their last reference when the tests naming them went:
  `scripts/bully_review_prune_ledger.py`, `scripts/defensive_bully_discovery_bakeoff.py`,
  `scripts/defensive_bully_discovery_seed.py`, `scripts/review_eval_truth.py`. Either raise the
  ceiling with a `reason:` in `config/complexity_budget.yaml`, or delete those four scripts —
  both are outside this lane's scope, so neither was done here.

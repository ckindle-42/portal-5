# Bully prune ledger

keep roots: portal.modules.security.core.bully.data_plane, portal.modules.security.core.bully.live_connect, portal.modules.security.core.review, portal.modules.security.core.review_eval
tally: {'KEEP': 69, 'KEEP_DYNAMIC': 20, 'DELETE': 1} -- deletable lines: 173

| module | lines | decision | importers (any) |
|---|---|---|---|
| bully | 68 | KEEP | adversary, analyst_corpus, analyst_loop, anchors |
| adaptive_scope | 259 | KEEP_DYNAMIC | investigation_pivot, bully_full_assembly_run, bully_investigation_run_a6, bully_relate |
| adversary | 486 | KEEP | test_p2_3_adversary, test_p2_e2e_demonstration |
| advisories | 151 | KEEP | live_census, test_sa7_l10_phase0_gate, test_sa7_l6_advisories |
| analyst_corpus | 1192 | KEEP | analyst_corpus_real_ingest, analyst_corpus_snapshot_v2, corpus_acquire, test_sa4_1_source_evaluation |
| analyst_loop | 399 | KEEP | observed_mode, bully_analyst_loop_run, bully_full_assembly_run, bully_truth_acceptance_run |
| anchors | 436 | KEEP | compounding, measurement, provenance, relation |
| artifact_graph | 681 | KEEP | anchors, baseline, discovery, unit_ladder |
| asset_identity | 268 | KEEP | live_census, test_sa7_l5_asset_identity |
| baseline | 157 | KEEP | discovery, unit_ladder, unit_measurement, unit_outcome |
| behavior_classifier | 262 | KEEP_DYNAMIC | bully_loop_milestone_run, bully_truth_acceptance_run, test_reintegration_r5c_behavior_classifier, test_truth_y5_output_distribution |
| behavior_inference | 324 | KEEP_DYNAMIC | bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6, bully_relate |
| behavior_values | 298 | KEEP | evidence, source_adapters, content, build_specimen_corpus_v3 |
| blend | 273 | KEEP_DYNAMIC | inject_plane, bully_inject_capture, bully_universal_intake_run, bully_relate |
| bots_answer_key | 305 | KEEP | captures, truth, bully_corpus_hunt_run, bully_full_assembly_run |
| calibration | 126 | KEEP_DYNAMIC | bully_cousin_run_c7, bully_relate, test_cousin_c3_measurement_guards, test_relate_g1_confidence_calibration |
| canary | 95 | KEEP_DYNAMIC | bully_relate, test_relate_g3_contamination_canary, test_relate_m2_ci_invariants |
| case_history | 176 | KEEP | live_census, test_sa7_l4_case_history |
| class_onboarding | 410 | KEEP | analyst_corpus_real_ingest, defensive_bully_calibrate, test_sa1_class_onboarding, test_sa5_5_real_ingest |
| compounding | 85 | KEEP | analyst_loop, observed_mode, bully_analyst_loop_run, bully_relate_run |
| config | 207 | KEEP | adversary, analyst_corpus, cousin_forge, handoff |
| connectors | 302 | KEEP | advisories, asset_identity, case_history, coverage |
| contracts | 1041 | KEEP | adversary, costing, cousin_calibration_bench, cousin_engine |
| corpus_bed | 600 | KEEP | bots_answer_key, cousin_inject, inject_plane, truth |
| correlation | 366 | KEEP | intake, bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run |
| costing | 144 | KEEP | orchestrator, test_p4_1_costing, test_p4_3_targeting, test_sa4_6_snapshot_integration |
| cousin_calibration_bench | 1796 | KEEP | class_onboarding, cousin_forge, discovery_bench, embedding_bench |
| cousin_engine | 665 | KEEP | class_onboarding, cousin_calibration_bench, discovery_bench, embedding_spaces |
| cousin_forge | 281 | KEEP | build_specimen_corpus, test_p7_2_specimen_corpus |
| cousin_inject | 165 | KEEP_DYNAMIC | bully_corpus_hunt_run, bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6 |
| cousin_relation | 605 | KEEP | observed_mode, bully_cousin_ladder, bully_relate_run, bully_relate |
| coverage | 104 | KEEP | live_census, bully_relate_run, test_sa7_l10_phase0_gate, test_sa7_l3_coverage |
| cutover | 68 | KEEP | orchestrator, defensive_bully_closeout, defensive_bully_specimen_e2e, defensive_bully_train |
| data_plane | 842 | KEEP | advisories, asset_identity, case_history, coverage |
| degeneracy | 153 | KEEP | relation, bully_cousin_run_c7, bully_relate_run, bully_relate |
| discovery | 410 | KEEP | compounding, unit_outcome, funnel, legacy_arm |
| discovery_bench | 835 | KEEP | bully_b1_engine_variants, bully_v3_threshold_validation, defensive_bully_discovery_bakeoff, defensive_bully_discovery_v3 |
| drift_engine | 276 | KEEP | orchestrator, test_p3_2_drift |
| embedding_bench | 316 | KEEP | test_sa3_1_embedding_bench |
| embedding_spaces | 183 | KEEP | defensive_bully_p04_adoption, test_sa5_p02_space_thresholds, test_sa5_p04_adoption |
| events | 62 | KEEP | case_history, store, test_p1_2_store |
| evidence | 296 | KEEP | handoff, orchestrator, promotion, bully_review_defect_census |
| field_roles | 557 | KEEP | artifact_graph, bully_full_assembly_run, bully_loop_milestone_run, bully_universal_intake_run |
| full_pipeline | 500 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_full_assembly_f1, test_full_assembly_f2 |
| handoff | 801 | KEEP | class_onboarding, orchestrator, bully_loop_milestone_run, defensive_bully_specimen_e2e |
| harvest | 470 | KEEP | defensive_bully_train, test_p6_2_harvest |
| inject_plane | 818 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run, bully_inject_capture |
| investigation | 202 | KEEP | orchestrator, bully_loop_milestone_run, test_p1_6_investigation, test_p1_7_orchestrator |
| investigation_pivot | 491 | KEEP_DYNAMIC | inject_plane, bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6 |
| live_census | 104 | KEEP | bully_cousin_run_c7, bully_relate_run, sa7_live_census, sa7_phase0_gate |
| live_connect | 345 | KEEP | inject_plane, live_census, bully_corpus_hunt_run, bully_full_assembly_run |
| live_profiles | 71 | KEEP | live_census, test_sa7_l10_phase0_gate, test_sa7_l7_live_profiles |
| loop_grader | 394 | KEEP | orchestrator, bully_full_assembly_run, bully_loop_milestone_run, bully_review_defect_census |
| measurement | 224 | KEEP_DYNAMIC | bully_relate_run, bully_relate, test_cousin_c3_measurement_guards, test_relate_m1_measurement_plane |
| mutation | 383 | KEEP | cousin_calibration_bench, orchestrator, test_p3_1_mutation, test_p3_3_mutation_wiring |
| observed_mode | 271 | KEEP | test_analyst_x3_observed_wiring, test_cousin_c2_observed_wiring, test_relate_b3_observed_mode, test_relate_j1_relation_investigation |
| orchestrator | 1393 | KEEP | hunt_modes, test_p1_0_skeleton, test_p1_7_orchestrator, test_p2_5_queue |
| organ | 470 | KEEP | bully, analyst_corpus, embedding_bench, orchestrator |
| outbox | 29 | KEEP | store |
| phase0_gate | 83 | KEEP | sa7_phase0_gate, test_sa7_l10_phase0_gate |
| planner_proof | 56 | KEEP | live_census, test_sa7_l10_phase0_gate, test_sa7_l8_planner_proof |
| plateau | 209 | KEEP | orchestrator, test_p4_4_plateau |
| playbooks | 247 | KEEP | orchestrator, test_p6_3_playbooks |
| promotion | 721 | KEEP | harvest, orchestrator, relation_promotion, defensive_bully_specimen_e2e |
| provenance | 78 | KEEP_DYNAMIC | measurement, bully_relate, test_relate_g2_provenance_tiers, test_relate_m2_ci_invariants |
| pyramid | 295 | KEEP | behavior_classifier, loop_grader, series_cousin, signatures |
| relation | 246 | KEEP | bully_cousin_ladder, test_analyst_x1_loop, test_cousin_c2_observed_wiring, test_relate_a2_relation_engine |
| relation_investigation | 86 | KEEP | observed_mode, test_relate_j1_relation_investigation |
| relation_promotion | 95 | KEEP | test_relate_j2_bin_gates_on_relation |
| roster | 173 | DELETE | test_p6_5_roster |
| run_preflight | 409 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_hunt_sweep_h1, test_hunt_sweep_h2 |
| score_sample | 206 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_score_sample_k1, test_scorer_feed_k2 |
| scoreboard | 199 | KEEP | orchestrator, bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run |
| scoreboard_conformance | 355 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_corpus_hunt_run, bully_loop_milestone_run, bully_truth_acceptance_run |
| seed_scope | 135 | KEEP | observed_mode, bully_relate_run, test_analyst_x3_observed_wiring, test_cousin_c2_observed_wiring |
| series_cousin | 365 | KEEP | anchors, loop_grader, bully_full_assembly_run, bully_loop_milestone_run |
| signatures | 317 | KEEP | analyst_corpus, class_onboarding, compounding, cousin_calibration_bench |
| soc | 225 | KEEP | test_p2_4_soc |
| source_adapters | 492 | KEEP | analyst_corpus, class_onboarding, build_specimen_corpus, test_sa1_class_onboarding |
| specimen_ledger | 155 | KEEP | cousin_calibration_bench, cousin_forge, inject_plane, build_specimen_corpus |
| store | 2720 | KEEP | bully, adversary, case_history, handoff |
| targeting | 247 | KEEP | orchestrator, test_p4_3_targeting, test_sa4_6_snapshot_integration |
| telemetry_behavior | 517 | KEEP | artifact_graph, series_cousin, bully_corpus_hunt_run, bully_full_assembly_run |
| training | 738 | KEEP | defensive_bully_train, test_p6_4_training |
| truth_acceptance | 362 | KEEP_DYNAMIC | bully_corpus_hunt_run, bully_truth_acceptance_run, bully_relate, test_truth_y1_acceptance |
| unit_ladder | 266 | KEEP_DYNAMIC | bully_universal_intake_run, bully_unknown_cousin_run, bully_relate, test_universal_m5_ci_invariants |
| unit_measurement | 501 | KEEP_DYNAMIC | bully_universal_intake_run, bully_unknown_cousin_run, bully_relate, test_universal_m4_honest_metrics |
| unit_outcome | 425 | KEEP_DYNAMIC | unit_ladder, unit_measurement, bully_full_assembly_run, bully_universal_intake_run |
| unit_relation | 273 | KEEP | unit_ladder, unit_outcome, knowledge, bully_relate |
| universe | 480 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_loop_milestone_run, bully_truth_acceptance_run, test_analyst_x5_generator_classes |

## Tests that only exercise deletable modules (1)

- tests/security/bully/test_p6_5_roster.py

## Scripts that only exercise deletable modules (0)


## Docs to reconcile or archive

- docs/BULLY_ADAPTIVE_REACH_RUN_A6_V1.json
- docs/BULLY_ADAPTIVE_REACH_RUN_A6_V1.md
- docs/BULLY_ANALYST_LOOP_RUN_X6_V1.json
- docs/BULLY_ANALYST_LOOP_RUN_X6_V1.md
- docs/BULLY_BASELINE_CALIBRATION_V2.md
- docs/BULLY_BASELINE_CALIBRATION_V3.md
- docs/BULLY_BUILD_PROGRESS.md
- docs/BULLY_CALIBRATION_POLICY_V1.md
- docs/BULLY_CORPUS_BED_LANE_A_VERIFY_C2_V1.md
- docs/BULLY_CORPUS_BED_RUN_C6_V1.json
- docs/BULLY_CORPUS_BED_RUN_C6_V1.md
- docs/BULLY_COUSIN_RELATION_RUN_C7_V1.json
- docs/BULLY_COUSIN_RELATION_RUN_C7_V1.md
- docs/BULLY_DATA_PLANE_CENSUS_LIVE_V1.json
- docs/BULLY_DATA_PLANE_CENSUS_V1.md
- docs/BULLY_DISCOVERY_FIRST_RUN_D4_V1.json
- docs/BULLY_DISCOVERY_FIRST_RUN_D4_V1.md
- docs/BULLY_FULL_ASSEMBLY_RUN_F4_V1.json
- docs/BULLY_FULL_ASSEMBLY_RUN_F4_V1.md
- docs/BULLY_HUNT_SWEEP_RUN_H5_V1.json
- docs/BULLY_HUNT_SWEEP_RUN_H5_V1.md
- docs/BULLY_INVESTIGATION_RUN_I6_V1.json
- docs/BULLY_INVESTIGATION_RUN_I6_V1.md
- docs/BULLY_LEGACY_RETIREMENT_V1.md
- docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.json
- docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md
- docs/BULLY_P6_TRAIN_GAP_ANALYSIS.md
- docs/BULLY_PRODUCT_GROUND_R1.md
- docs/BULLY_REAL_TELEMETRY_RUN_T3_V1.json
- docs/BULLY_REAL_TELEMETRY_RUN_T3_V1.md
- docs/BULLY_REFINEMENT_POLICY_V1.md
- docs/BULLY_RELATE_INVESTIGATE_RUN_M3_V1.json
- docs/BULLY_RELATE_INVESTIGATE_RUN_M3_V1.md
- docs/BULLY_REVIEW_PROGRAM.md
- docs/BULLY_REVIEW_STATE.md
- docs/BULLY_SA7_P0_GATE_L10.md
- docs/BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1.json
- docs/BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1.md
- docs/BULLY_SCORER_FEED_RUN_K4_V1.json
- docs/BULLY_SCORER_FEED_RUN_K4_V1.md
- docs/BULLY_STATE_REVIEW_20261008.md
- docs/BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.json
- docs/BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.md
- docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json
- docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.md
- docs/BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json
- docs/BULLY_UNKNOWN_COUSIN_RUN_M3_V1.md
- docs/DESIGN_BULLY_ADAPTIVE_REACH_V1.md
- docs/DESIGN_BULLY_ANALYST_LOOP_V1.md
- docs/DESIGN_BULLY_CORPUS_BED_V1.md
- docs/DESIGN_BULLY_COUSIN_RELATION_V1.md
- docs/DESIGN_BULLY_DISCOVERY_FIRST_V1.md
- docs/DESIGN_BULLY_FULL_ASSEMBLY_V1.md
- docs/DESIGN_BULLY_HUNT_SWEEP_V1.md
- docs/DESIGN_BULLY_INVESTIGATION_V1.md
- docs/DESIGN_BULLY_LOOP_REINTEGRATION_V1.md
- docs/DESIGN_BULLY_REAL_TELEMETRY_V1.md
- docs/DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1.md
- docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md
- docs/DESIGN_BULLY_UNIVERSAL_INTAKE_V1.md
- docs/DESIGN_BULLY_UNKNOWN_COUSIN_V1.md
- docs/HANDOFF_BULLY_CROGL_STATE.md

## External importer KEEP decisions

32 initially unreachable modules have at least one retained test or script importer. They are direct KEEP promotions under the task rule; their static dependencies follow the ordinary closure. The importer paths and their ledger classifications are recorded in `prune_external_importer_evidence.json`.

| module | retained importer evidence |
|---|---|
| `adversary` | `tests/security/bully/test_p2_3_adversary.py`, `tests/security/bully/test_p2_e2e_demonstration.py` |
| `advisories` | `tests/security/bully/test_sa7_l10_phase0_gate.py`, `tests/security/bully/test_sa7_l6_advisories.py` |
| `analyst_corpus` | `tests/security/bully/test_sa4_6_snapshot_integration.py`, `tests/security/bully/test_sa5_2_cloudtrail_parsers.py` |
| `asset_identity` | `tests/security/bully/test_sa7_l5_asset_identity.py` |
| `case_history` | `tests/security/bully/test_sa7_l4_case_history.py` |
| `class_onboarding` | `scripts/defensive_bully_calibrate.py` |
| `costing` | `tests/security/bully/test_p4_1_costing.py`, `tests/security/bully/test_sa4_6_snapshot_integration.py` |
| `cousin_calibration_bench` | `scripts/build_specimen_corpus.py`, `scripts/bully_b1_engine_variants.py`, `scripts/bully_v3_threshold_validation.py`, `scripts/defensive_bully_calibrate.py`, `scripts/defensive_bully_discovery_seed.py`, `scripts/defensive_bully_discovery_v3.py`, `scripts/defensive_bully_p04_adoption.py`, `scripts/defensive_bully_specimen_e2e.py`, `tests/benchmarks/embedding_consumers/probes/bully.py`, `tests/security/bully/test_p7_2_specimen_corpus.py`, `tests/security/bully/test_p7_3_specimen_scale.py`, `tests/security/bully/test_p7_4_retrieval_validity.py`, `tests/security/bully/test_sa3_1_embedding_bench.py`, `tests/security/bully/test_sa3_4_discovery_seed.py`, `tests/security/bully/test_sa3_5_discovery_bakeoff.py` |
| `cousin_forge` | `scripts/build_specimen_corpus.py`, `tests/security/bully/test_p7_2_specimen_corpus.py` |
| `coverage` | `scripts/bully_relate_run.py`, `tests/security/bully/test_sa7_l10_phase0_gate.py`, `tests/security/bully/test_sa7_l3_coverage.py` |
| `cutover` | `scripts/defensive_bully_closeout.py`, `scripts/defensive_bully_specimen_e2e.py`, `scripts/defensive_bully_train.py`, `tests/security/bully/test_p7_cutover.py` |
| `discovery_bench` | `scripts/bully_b1_engine_variants.py`, `scripts/bully_v3_threshold_validation.py`, `scripts/defensive_bully_discovery_bakeoff.py`, `scripts/defensive_bully_discovery_v3.py`, `scripts/defensive_bully_p04_adoption.py`, `tests/benchmarks/embedding_consumers/probes/bully.py`, `tests/security/bully/test_sa2_1_real_pairs.py`, `tests/security/bully/test_sa3_5_discovery_bakeoff.py`, `tests/security/bully/test_sa5_p03_identity_diagnostic.py`, `tests/security/bully/test_sa5_p04_adoption.py` |
| `embedding_bench` | `tests/security/bully/test_sa3_1_embedding_bench.py` |
| `embedding_spaces` | `scripts/defensive_bully_p04_adoption.py`, `tests/security/bully/test_sa5_p02_space_thresholds.py`, `tests/security/bully/test_sa5_p04_adoption.py` |
| `harvest` | `scripts/defensive_bully_train.py`, `tests/security/bully/test_p6_2_harvest.py` |
| `live_census` | `scripts/bully_cousin_run_c7.py`, `scripts/bully_relate_run.py`, `tests/security/bully/test_sa7_l9_live_census.py` |
| `live_profiles` | `tests/security/bully/test_sa7_l10_phase0_gate.py`, `tests/security/bully/test_sa7_l7_live_profiles.py` |
| `mutation` | `tests/security/bully/test_p3_1_mutation.py`, `tests/security/bully/test_p3_3_mutation_wiring.py` |
| `observed_mode` | `tests/security/bully/test_analyst_x3_observed_wiring.py`, `tests/security/bully/test_cousin_c2_observed_wiring.py`, `tests/security/bully/test_relate_b3_observed_mode.py`, `tests/security/bully/test_relate_j1_relation_investigation.py` |
| `orchestrator` | `tests/security/bully/test_p1_7_orchestrator.py`, `tests/security/bully/test_p2_5_queue.py`, `tests/security/bully/test_p2_e2e_demonstration.py`, `tests/security/bully/test_p3_3_mutation_wiring.py`, `tests/security/bully/test_p3_4_drift_wiring.py`, `tests/security/bully/test_p4_2_scoreboard.py`, `tests/security/bully/test_p4_3_targeting_wiring.py`, `tests/security/bully/test_p4_4_plateau_wiring.py`, `tests/security/bully/test_p5_3_deploy.py`, `tests/security/bully/test_p7_cutover.py`, `tests/security/bully/test_reintegration_r4_cutover.py` |
| `phase0_gate` | `tests/security/bully/test_sa7_l10_phase0_gate.py` |
| `planner_proof` | `tests/security/bully/test_sa7_l10_phase0_gate.py`, `tests/security/bully/test_sa7_l8_planner_proof.py` |
| `playbooks` | `tests/security/bully/test_p6_3_playbooks.py` |
| `promotion` | `scripts/defensive_bully_specimen_e2e.py`, `tests/security/bully/test_p2_2_promotion.py`, `tests/security/bully/test_p2_5_queue.py`, `tests/security/bully/test_p2_e2e_demonstration.py`, `tests/security/bully/test_p5_3_deploy.py` |
| `relation` | `scripts/bully_cousin_ladder.py`, `tests/security/bully/test_analyst_x1_loop.py`, `tests/security/bully/test_cousin_c2_observed_wiring.py`, `tests/security/bully/test_relate_a2_relation_engine.py`, `tests/security/bully/test_relate_a3_anomaly_success.py`, `tests/security/bully/test_relate_g4_anti_degeneracy.py`, `tests/security/bully/test_relate_j1_relation_investigation.py`, `tests/security/bully/test_relate_j2_bin_gates_on_relation.py`, `tests/security/bully/test_relate_j3_outcome_to_anchor.py`, `tests/security/bully/test_relate_m1_measurement_plane.py` |
| `relation_investigation` | `tests/security/bully/test_relate_j1_relation_investigation.py` |
| `relation_promotion` | `tests/security/bully/test_relate_j2_bin_gates_on_relation.py` |
| `seed_scope` | `scripts/bully_relate_run.py`, `tests/security/bully/test_analyst_x3_observed_wiring.py`, `tests/security/bully/test_cousin_c2_observed_wiring.py`, `tests/security/bully/test_cousin_c4_seed_entity_scope.py`, `tests/security/bully/test_relate_b2_seed_scope.py`, `tests/security/bully/test_relate_j1_relation_investigation.py` |
| `soc` | `tests/security/bully/test_p2_4_soc.py` |
| `source_adapters` | `scripts/build_specimen_corpus.py`, `tests/security/bully/test_sa1_source_adapters.py`, `tests/security/bully/test_sa5_2_cloudtrail_parsers.py`, `tests/security/bully/test_sa7_data_plane.py` |
| `targeting` | `tests/security/bully/test_sa4_6_snapshot_integration.py` |
| `training` | `scripts/defensive_bully_train.py`, `tests/security/bully/test_p6_4_training.py` |

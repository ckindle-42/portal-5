# Bully prune ledger

keep roots: portal.modules.security.core.bully.data_plane, portal.modules.security.core.bully.live_connect, portal.modules.security.core.review, portal.modules.security.core.review_eval
tally: {'KEEP': 23, 'KEEP_DYNAMIC': 32, 'DELETE': 34} -- deletable lines: 12958

## Phase C notes

Deleted modules' tests and one-off run scripts go with those modules in the same batch. An importer promotes a candidate to KEEP only when it survives for an independent reason; a test or script whose purpose is exercising deleted code does not promote that code.

| module | lines | decision | importers (any) |
|---|---|---|---|
| bully | 68 | KEEP | adversary, analyst_corpus, analyst_loop, anchors |
| adaptive_scope | 259 | KEEP_DYNAMIC | investigation_pivot, bully_full_assembly_run, bully_investigation_run_a6, bully_relate |
| adversary | 486 | DELETE | test_p2_3_adversary, test_p2_e2e_demonstration |
| advisories | 151 | DELETE | live_census, test_sa7_l10_phase0_gate, test_sa7_l6_advisories |
| analyst_corpus | 1192 | DELETE | analyst_corpus_real_ingest, analyst_corpus_snapshot_v2, corpus_acquire, test_sa4_1_source_evaluation |
| analyst_loop | 399 | KEEP_DYNAMIC | observed_mode, bully_analyst_loop_run, bully_full_assembly_run, bully_truth_acceptance_run |
| anchors | 436 | KEEP | compounding, measurement, provenance, relation |
| artifact_graph | 681 | KEEP | anchors, baseline, discovery, unit_ladder |
| asset_identity | 268 | DELETE | live_census, test_sa7_l5_asset_identity |
| baseline | 157 | KEEP | discovery, unit_ladder, unit_measurement, unit_outcome |
| behavior_classifier | 262 | KEEP_DYNAMIC | bully_loop_milestone_run, bully_truth_acceptance_run, test_reintegration_r5c_behavior_classifier, test_truth_y5_output_distribution |
| behavior_inference | 324 | KEEP_DYNAMIC | bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6, bully_relate |
| behavior_values | 298 | KEEP | evidence, source_adapters, content, build_specimen_corpus_v3 |
| blend | 273 | KEEP_DYNAMIC | inject_plane, bully_inject_capture, bully_universal_intake_run, bully_relate |
| bots_answer_key | 305 | KEEP | captures, truth, bully_corpus_hunt_run, bully_full_assembly_run |
| calibration | 126 | KEEP_DYNAMIC | bully_cousin_run_c7, bully_relate, test_cousin_c3_measurement_guards, test_relate_g1_confidence_calibration |
| canary | 95 | KEEP_DYNAMIC | bully_relate, test_relate_g3_contamination_canary, test_relate_m2_ci_invariants |
| case_history | 176 | DELETE | live_census, test_sa7_l4_case_history |
| class_onboarding | 410 | DELETE | analyst_corpus_real_ingest, defensive_bully_calibrate, test_sa1_class_onboarding, test_sa5_5_real_ingest |
| compounding | 85 | KEEP_DYNAMIC | analyst_loop, observed_mode, bully_analyst_loop_run, bully_relate_run |
| config | 207 | KEEP | adversary, analyst_corpus, cousin_forge, handoff |
| connectors | 302 | KEEP | advisories, asset_identity, case_history, coverage |
| contracts | 1041 | KEEP | adversary, costing, cousin_calibration_bench, cousin_engine |
| corpus_bed | 600 | KEEP | bots_answer_key, cousin_inject, inject_plane, truth |
| correlation | 366 | KEEP | intake, bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run |
| costing | 144 | DELETE | orchestrator, test_p4_1_costing, test_p4_3_targeting, test_sa4_6_snapshot_integration |
| cousin_calibration_bench | 1796 | DELETE | class_onboarding, cousin_forge, discovery_bench, embedding_bench |
| cousin_engine | 665 | KEEP_DYNAMIC | class_onboarding, cousin_calibration_bench, discovery_bench, embedding_spaces |
| cousin_forge | 281 | DELETE | build_specimen_corpus, test_p7_2_specimen_corpus |
| cousin_inject | 165 | KEEP_DYNAMIC | bully_corpus_hunt_run, bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6 |
| cousin_relation | 605 | KEEP_DYNAMIC | observed_mode, bully_cousin_ladder, bully_relate_run, bully_relate |
| coverage | 104 | DELETE | live_census, bully_relate_run, test_sa7_l10_phase0_gate, test_sa7_l3_coverage |
| cutover | 68 | DELETE | orchestrator, defensive_bully_closeout, defensive_bully_specimen_e2e, defensive_bully_train |
| data_plane | 842 | KEEP | advisories, asset_identity, case_history, coverage |
| degeneracy | 153 | KEEP_DYNAMIC | relation, bully_cousin_run_c7, bully_relate_run, bully_relate |
| discovery | 410 | KEEP | compounding, unit_outcome, funnel, legacy_arm |
| discovery_bench | 835 | DELETE | bully_b1_engine_variants, bully_v3_threshold_validation, defensive_bully_discovery_bakeoff, defensive_bully_discovery_v3 |
| drift_engine | 276 | DELETE | orchestrator, test_p3_2_drift |
| embedding_bench | 316 | DELETE | test_sa3_1_embedding_bench |
| embedding_spaces | 183 | DELETE | defensive_bully_p04_adoption, test_sa5_p02_space_thresholds, test_sa5_p04_adoption |
| events | 62 | KEEP | case_history, store, test_p1_2_store |
| evidence | 296 | KEEP_DYNAMIC | handoff, orchestrator, promotion, bully_review_defect_census |
| field_roles | 557 | KEEP | artifact_graph, bully_full_assembly_run, bully_loop_milestone_run, bully_universal_intake_run |
| full_pipeline | 500 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_full_assembly_f1, test_full_assembly_f2 |
| handoff | 801 | KEEP_DYNAMIC | class_onboarding, orchestrator, bully_loop_milestone_run, defensive_bully_specimen_e2e |
| harvest | 470 | DELETE | defensive_bully_train, test_p6_2_harvest |
| inject_plane | 818 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run, bully_inject_capture |
| investigation | 202 | KEEP_DYNAMIC | orchestrator, bully_loop_milestone_run, test_p1_6_investigation, test_p1_7_orchestrator |
| investigation_pivot | 491 | KEEP_DYNAMIC | inject_plane, bully_full_assembly_run, bully_investigation_run_a6, bully_investigation_run_i6 |
| live_census | 104 | DELETE | bully_cousin_run_c7, bully_relate_run, sa7_live_census, sa7_phase0_gate |
| live_connect | 345 | KEEP | inject_plane, live_census, bully_corpus_hunt_run, bully_full_assembly_run |
| live_profiles | 71 | DELETE | live_census, test_sa7_l10_phase0_gate, test_sa7_l7_live_profiles |
| loop_grader | 394 | KEEP_DYNAMIC | orchestrator, bully_full_assembly_run, bully_loop_milestone_run, bully_review_defect_census |
| measurement | 224 | KEEP_DYNAMIC | bully_relate_run, bully_relate, test_cousin_c3_measurement_guards, test_relate_m1_measurement_plane |
| mutation | 383 | DELETE | cousin_calibration_bench, orchestrator, test_p3_1_mutation, test_p3_3_mutation_wiring |
| observed_mode | 271 | DELETE | test_analyst_x3_observed_wiring, test_cousin_c2_observed_wiring, test_relate_b3_observed_mode, test_relate_j1_relation_investigation |
| orchestrator | 1393 | DELETE | hunt_modes, test_p1_0_skeleton, test_p1_7_orchestrator, test_p2_5_queue |
| organ | 470 | KEEP | bully, analyst_corpus, embedding_bench, orchestrator |
| outbox | 29 | KEEP | store |
| phase0_gate | 83 | DELETE | sa7_phase0_gate, test_sa7_l10_phase0_gate |
| planner_proof | 56 | DELETE | live_census, test_sa7_l10_phase0_gate, test_sa7_l8_planner_proof |
| plateau | 209 | DELETE | orchestrator, test_p4_4_plateau |
| playbooks | 247 | DELETE | orchestrator, test_p6_3_playbooks |
| promotion | 721 | DELETE | harvest, orchestrator, relation_promotion, defensive_bully_specimen_e2e |
| provenance | 78 | KEEP_DYNAMIC | measurement, bully_relate, test_relate_g2_provenance_tiers, test_relate_m2_ci_invariants |
| pyramid | 295 | KEEP | behavior_classifier, loop_grader, series_cousin, signatures |
| relation | 246 | DELETE | bully_cousin_ladder, test_analyst_x1_loop, test_cousin_c2_observed_wiring, test_relate_a2_relation_engine |
| relation_investigation | 86 | DELETE | observed_mode, test_relate_j1_relation_investigation |
| relation_promotion | 95 | DELETE | test_relate_j2_bin_gates_on_relation |
| run_preflight | 409 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_hunt_sweep_h1, test_hunt_sweep_h2 |
| score_sample | 206 | KEEP_DYNAMIC | bully_full_assembly_run, bully_relate, test_score_sample_k1, test_scorer_feed_k2 |
| scoreboard | 199 | KEEP_DYNAMIC | orchestrator, bully_analyst_loop_run, bully_corpus_hunt_run, bully_full_assembly_run |
| scoreboard_conformance | 355 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_corpus_hunt_run, bully_loop_milestone_run, bully_truth_acceptance_run |
| seed_scope | 135 | DELETE | observed_mode, bully_relate_run, test_analyst_x3_observed_wiring, test_cousin_c2_observed_wiring |
| series_cousin | 365 | KEEP | anchors, loop_grader, bully_full_assembly_run, bully_loop_milestone_run |
| signatures | 317 | KEEP_DYNAMIC | analyst_corpus, class_onboarding, compounding, cousin_calibration_bench |
| soc | 225 | DELETE | test_p2_4_soc |
| source_adapters | 492 | DELETE | analyst_corpus, class_onboarding, build_specimen_corpus, test_sa1_class_onboarding |
| specimen_ledger | 155 | KEEP_DYNAMIC | cousin_calibration_bench, cousin_forge, inject_plane, build_specimen_corpus |
| store | 2720 | KEEP | bully, adversary, case_history, handoff |
| targeting | 247 | DELETE | orchestrator, test_p4_3_targeting, test_sa4_6_snapshot_integration |
| telemetry_behavior | 517 | KEEP | artifact_graph, series_cousin, bully_corpus_hunt_run, bully_full_assembly_run |
| training | 738 | DELETE | defensive_bully_train, test_p6_4_training |
| truth_acceptance | 362 | KEEP_DYNAMIC | bully_corpus_hunt_run, bully_truth_acceptance_run, bully_relate, test_truth_y1_acceptance |
| unit_ladder | 266 | KEEP_DYNAMIC | bully_universal_intake_run, bully_unknown_cousin_run, bully_relate, test_universal_m5_ci_invariants |
| unit_measurement | 501 | KEEP_DYNAMIC | bully_universal_intake_run, bully_unknown_cousin_run, bully_relate, test_universal_m4_honest_metrics |
| unit_outcome | 425 | KEEP_DYNAMIC | unit_ladder, unit_measurement, bully_full_assembly_run, bully_universal_intake_run |
| unit_relation | 273 | KEEP | unit_ladder, unit_outcome, knowledge, bully_relate |
| universe | 480 | KEEP_DYNAMIC | bully_analyst_loop_run, bully_loop_milestone_run, bully_truth_acceptance_run, test_analyst_x5_generator_classes |

## Tests that only exercise deletable modules (21)

- tests/security/bully/test_p1_0_skeleton.py
- tests/security/bully/test_p3_2_drift.py
- tests/security/bully/test_p4_3_targeting.py
- tests/security/bully/test_p4_4_plateau.py
- tests/security/bully/test_p6_8_cousin_calibration.py
- tests/security/bully/test_r1_dry_run_red_status.py
- tests/security/bully/test_r1_replay_driver.py
- tests/security/bully/test_sa1_class_onboarding.py
- tests/security/bully/test_sa2_2_taxonomy.py
- tests/security/bully/test_sa2_3_circularity.py
- tests/security/bully/test_sa2_4_cross_class.py
- tests/security/bully/test_sa2_5_forge_demotion.py
- tests/security/bully/test_sa4_1_source_evaluation.py
- tests/security/bully/test_sa4_2_broad_ingestion.py
- tests/security/bully/test_sa4_3_benign.py
- tests/security/bully/test_sa4_4_pivot_pairs.py
- tests/security/bully/test_sa4_5_hypotheses.py
- tests/security/bully/test_sa5_1_acquisition.py
- tests/security/bully/test_sa5_5_real_ingest.py
- tests/security/bully/test_sa5_6_snapshot_v2.py
- tests/security/bully/test_sa5_7_discovery_v3.py

## Scripts that only exercise deletable modules (5)

- scripts/analyst_corpus_real_ingest.py
- scripts/analyst_corpus_snapshot_v2.py
- scripts/corpus_acquire.py
- scripts/sa7_live_census.py
- scripts/sa7_phase0_gate.py

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

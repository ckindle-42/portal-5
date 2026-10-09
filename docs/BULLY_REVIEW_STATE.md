# Bully / Crogl review -- derived state

DO NOT EDIT. Rendered by `scripts/bully_review_state.py` from the defect census, stamped
evaluation reports and decision records; `--check` fails if this file is stale.

## Claims (each is a probe: `scripts/bully_review_defect_census.py`)

| id | status | evidence |
|---|---|---|
| D-AGENTS-STUB | module_absent | ModuleNotFoundError: investigation.agents |
| D-CIRCULAR-FIXTURES | present | R.3 signature tests feed AWS API verbs the production adapter never emits |
| D-DEAD-DIAL | absent | hunt.yaml has thresholds block=False; loop_grader reads hunt config=False |
| D-DEFENSE-CONSTANT | present | _defense_response(observable, healthy) -> 'COVERED' with no detection consulted |
| D-ENTITY-FIELDNAME | present | cross-source shared_entity edges for the same host values: 0 |
| D-LABEL-IN-SIGNATURE | present | signature family='kerberoast_chain' (the Red scenario name) |
| D-NAME-TABLE | present | behavior_values._FIELDS hand-listed field names: 64 |
| D-NOVEL-UNREACHABLE | present | _search_table distance-value comparisons: none |
| D-SIG-DICT-NOCONTENT | present | actions=['event-0:record', 'event-1:record'] |
| D-SIG-WEB-HTTPVERB | present | behavior_spine=('enumerate', 'c2_exfil', 'enumerate') |
| D-SIG-WIN-SPINE | present | behavior_spine=() actions=['event-0:4624', 'event-1:4769', 'event-2:4688'] |
| D-SINGLE-ITERATION | module_absent | ModuleNotFoundError: bully.orchestrator |
| D-UNITS-CAP | present | 700 artifacts -> 512 L1 units by default |
| D-VERDICT-DEADEND | module_absent | ModuleNotFoundError: bully.orchestrator |

Reachability of the engine package (static import closure):

| class | modules | lines |
|---|---|---|
| orphan | 0 | 0 |
| production | 11 | 4167 |
| production-lazy | 4 | 1256 |
| script-only | 44 | 19898 |
| tests-only | 0 | 0 |

## Decisions

| id | stage | status | report | problems |
|---|---|---|---|---|
| D-T1-BASELINE | raised | INCONCLUSIVE | reports/review_eval/6a29bc97d0fd3b97/truth_derivation.json | none |
| D-T2-TRUTH-STRATIFICATION | window | REJECTED | reports/review_eval/90890b3c9418457c/truth_stratification.md | none |
| D-T3-CHALLENGER | raised | INCONCLUSIVE | reports/review_eval/41eaed5720a9844f/t3_prerequisites.json | none |
| D-T3-PANEL | raised | REJECTED | reports/review_eval/41eaed5720a9844f/t3_prerequisites.json | none |
| D-T3-PIVOT | raised | INCONCLUSIVE | reports/review_eval/41eaed5720a9844f/t3_prerequisites.json | none |
| D-T3-READER | raised | INCONCLUSIVE | reports/review_eval/41eaed5720a9844f/t3_prerequisites.json | none |
| D-T4-DEFENSE | raised | INCONCLUSIVE | reports/review_eval/4de03bca93e183d8/t4_pair_gate.json | none |
| D-T4-MATURE | raised | INCONCLUSIVE | reports/review_eval/4de03bca93e183d8/t4_pair_gate.json | none |
| D-T4-SUPPRESS | raised | INCONCLUSIVE | reports/review_eval/4de03bca93e183d8/t4_pair_gate.json | none |
| D-T6-PROOF | window | INCONCLUSIVE | reports/review_eval/e2e/t6_proof.json | none |

## Measured (stamped, real corpora only)

### arm `?` stamp `4de03bca93e183d8`

commit `31ddefc13a03`, embedder `not_used;T4_precondition_only`, corpus `real:bots_truth_manifest:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`

| metric | value | n | reads as failure when |
|---|---|---|---|
| eligible_pairs | 0 | 3 | fails when fewer than 20 answer-key and same-index routine-use pairs can be independently labelled |
| botsv1_botsv2_unexcluded_index_seconds | 0 | 2 | fails when any indexed time remains outside every retained answer-key interval plus the 24-hour margin, requiring a routine-use search before a no-run result |
| same_index_benign_benchmark_cells | 0 | 12 | fails when portal5_lab benign benchmark cells are counted as same-index BOTSv background |

### arm `?` stamp `6382ecb3d97f4cee`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:recorded-captures:5445bf316cfc1c065f6d61c69858a3464ff10892831113e2797a68dea1c772b0`

| metric | value | n | reads as failure when |
|---|---|---|---|
| capture_admission_rate | 0.000887311 | 1127 | fails when the self-tested validator admits no recorded capture |

### arm `?` stamp `6a29bc97d0fd3b97`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv1,botsv2,botsv3:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`

| metric | value | n | reads as failure when |
|---|---|---|---|
| answer_key_entry_yield | 0.259259 | 27 | fails when declared entities cannot be independently located and reconciled |
| usable_index_slice_yield | 0 | 3 | fails when none of the three pre-registered indexes has a paired real slice |

### arm `?` stamp `90890b3c9418457c`

commit `83ddaa0bd53a`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:bots_truth_manifest:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`

| metric | value | n | reads as failure when |
|---|---|---|---|
| exact_parent_reconciliation_rate | 0 | 5 | fails when any completed current source replay differs from the T1 product event-id set |

### arm `T5-surface-e2e` stamp `d000a7c8502c9e9c`

commit `53ed4f0cce04`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv2/stream:dns/1501784416-1501784577`

| metric | value | n | reads as failure when |
|---|---|---|---|
| phase_d_e2e_case_success | 1 | 4 | value is below 1.0 when any required Phase D case is not evidenced as passing |

### arm `T6-real-corpus-proof` stamp `725bebcc8911ba4b`

commit `fcce4bf3dc9b`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:t6-proof:d2bbad0d80f3ce74a465f6626be714e0560496a5124fe4317eab7861cfec692f`

| metric | value | n | reads as failure when |
|---|---|---|---|
| claim_proven_fraction | 0.25 | 4 | fails when any standing claim is not PROVEN under the task rule |
| processed_corpus_fraction | 1.27305e-05 | 9 | fails when the processed real-event fraction is omitted or recomputes differently |
| drill_pass_fraction | 1 | 3 | fails when any required phase-C drill does not pass |

### arm `legacy_funnel` stamp `2921d3691e815b53`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv3:25e5d654c29bc747ced0c52e759b22d4a9e82d1c06d29d1d2008801ff3949ac0`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `legacy_funnel` stamp `5e3e806b2f815dc8`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv1:64b8b2f6043fa9373a8bc6356081ae8efebd6da065a4e90350da691b0d568abb`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `legacy_funnel` stamp `81ae0e963b3a499a`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv2:8c4fea104572cf48e00b1f73c001e1edfb6c8f9e3cb2475980cf7c7fc157aebc`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `review_d0` stamp `cf5bfa97e417c12a`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv1:64b8b2f6043fa9373a8bc6356081ae8efebd6da065a4e90350da691b0d568abb`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `review_d0` stamp `d03e05d3725798a9`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv3:25e5d654c29bc747ced0c52e759b22d4a9e82d1c06d29d1d2008801ff3949ac0`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `review_d0` stamp `ea8a1330837e2913`

commit `d6145c276260`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:botsv2:8c4fea104572cf48e00b1f73c001e1edfb6c8f9e3cb2475980cf7c7fc157aebc`

| metric | value | n | reads as failure when |
|---|---|---|---|
| slice_eligibility | 0 | 1 | fails when the pre-registered index has no usable attack and benign pair |

### arm `t3_prerequisites` stamp `41eaed5720a9844f`

commit `4a6eeb9ccd01`, embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`, corpus `real:reader-prerequisites:f56783be88f2f963a32f3f8a52701da15e8a705fe18f73257116328410f35500`

| metric | value | n | reads as failure when |
|---|---|---|---|
| core_reasoning_candidate_rate | 0.5 | 4 | fails when no configured single-reader candidate produces a reasoning channel |
| panel_reasoning_seat_rate | 0.333333 | 3 | fails when the configured panel has no reasoning-capable seat |
| paired_truth_slice_yield | 0 | 3 | fails when no registered index has an eligible paired truth slice |
| alpha_open_available | 0 | 1 | fails when T2 has no candidate-recall-versus-alpha curve from which to derive alpha_open |
| workload_B_available | 0 | 1 | fails when T1 did not establish workload budget B |
| reader_depth_R_available | 0 | 1 | fails when evaluation window duration and measured concern p95 latency are unavailable |

binding stage: `unmeasured` (all pre-registered paired slices were excluded before product execution)


## T6 proof claims (validated report)

Processed corpus: `0.001273%`. Stop rule: stopped at the certified truth-yield ceiling: T2 admitted one cousin capture, and the T1/T2 evidence manifests contain no additional independent cousin items; the last-20-percent bootstrap-SE plateau cannot be estimated at n=1, so no synthetic substitute or repeated truth item was added.

| claim | status | n and estimate (95% CI) | control / completeness |
|---|---|---|---|
| C1 any source | UNPROVEN | review n=9; 0.667 [0.333, 1.000] | legacy n=9; 0.667 [0.333, 1.000]; blind: botsv1:WinEventLog:Application, botsv2:winregistry, botsv3:stream:http |
| C2 same or similar | UNPROVEN | known review n=5; 0.000 [0.000, 0.000]; cousin review n=1; 0.000; CI unavailable; novel review n=0; no estimate; benign n=33 | known legacy n=5; 0.000 [0.000, 0.000]; cousin legacy n=1; 0.000; CI unavailable; novel legacy n=0; no estimate; false-raise/1k=60.60606060606061 |
| C3 corpus is ground | PROVEN | windows n=9; stages n=69 | fetched 3559/3559; projected full corpus seconds=not estimable; bottleneck funnel.flagged has zero throughput |
| C4 recorded truth | UNPROVEN | cousin review n=1; 0.000; CI unavailable; novel review n=0; no estimate; evidence_twin review n=0; no estimate | cousin legacy n=1; 0.000; CI unavailable; novel legacy n=0; no estimate; evidence_twin legacy n=0; no estimate; captures admitted=1/1127, rejected=1126, reasons={'CAPTURE_GROUND_TRUTH_INVALID': 1126, 'LEGACY_CAPTURE_UNSCOPED': 653, 'MISSING_EPISODE_ID': 718, 'NO_SIGNAL_RULE': 8, 'NO_TIMED_EVENTS_IN_INTERVAL': 726, 'SIGNAL_MISSING_IN_INTERVAL': 1073, 'SIGNAL_PRESENT_ONLY_OUTSIDE_INTERVAL': 1, 'SIGNAL_PRESENT_WITHOUT_EVENT_TIMESTAMP': 178} |

### Phase-C drills

| drill | status | evidence |
|---|---|---|
| recovery | PASS | interrupted_status=INTERRUPTED |
| embedder_change | PASS | changed_run_id=run-866e07c1c56e; doctor_fix_applied=True; elapsed_seconds=0.21147199999541044; false_raise_alpha_plus_3se_per_1000=295.2005245492835; false_raise_per_1000=32.25806451612903; false_raise_within_tolerance=True; false_raised_units=1; final_stale_calibrations=[]; from_identity=google/embeddinggemma-2;dim=768;task=sentence similarity;role=query; return_to_default_fix_applied=True; return_to_default_identity=google/embeddinggemma-2;dim=768;task=sentence similarity;role=query; sample_benign_unit_count=31; sample_event_count=18; sample_window=portal5_lab_20260616; stale_after_fix=[]; stale_before_fix=['known_similar|L2_ENTITY']; temporary_identity=google/embeddinggemma-2;dim=256;task=sentence similarity;role=query |
| reader_unreachable | PASS | all_judged_unsure_and_degraded=True; concern_count=1; deterministic_concerns_preserved=True; elapsed_seconds=0.10535304201766849; model_transport=local connection refused before any model response; no_invented_claims=True; run_id=run-dd04ec4cbab9; sample_window=portal5_lab_auditd_20260616 |

## Ownership (one owner per capability)

| capability | owner |
|---|---|
| candidate_funnel | review.funnel + review.calibration |
| content_cards | review.content |
| defense_coverage | review.defense (runs the detection library over a concern's window) |
| durable_runs | review.runs |
| intake_and_units | review.intake (engine: bully.field_roles, bully.artifact_graph, bully.correlation) |
| knowledge_retrieval | review.knowledge (anchors persisted by review.store) |
| measurement | review_eval (stamp, metrics, selftest, attribution, decisions, report) |
| relation_reading | review.judge + review.panel, gated by review.grounding |
| replay_corpus | already-indexed telemetry (BOTS indexes, portal5_lab) + previously recorded exercise captures, read through siem.capture_store and bully.live_connect / bully.data_plane (replay plane; read-only; never product). NOTHING IN THIS PROGRAM EXECUTES: exec_chain, blue.collect_and_ship_scenario_telemetry, scripts/caldera_emulate.py and bully.inject_plane are OUT OF SCOPE as runnable paths and are owned by no capability here. |
| verdict_and_learning | review.verdicts + review.store |
| window_source | review.window |

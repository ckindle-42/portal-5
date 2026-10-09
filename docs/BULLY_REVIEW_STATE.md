# Bully / Crogl review -- derived state

DO NOT EDIT. Rendered by `scripts/bully_review_state.py` from the defect census, stamped
evaluation reports and decision records; `--check` fails if this file is stale.

## Claims (each is a probe: `scripts/bully_review_defect_census.py`)

| id | status | evidence |
|---|---|---|
| D-AGENTS-STUB | present | hardcoded checklist=True; makes model/tool calls=False |
| D-CIRCULAR-FIXTURES | present | R.3 signature tests feed AWS API verbs the production adapter never emits |
| D-DEAD-DIAL | present | hunt.yaml has thresholds block=True; loop_grader reads hunt config=False |
| D-DEFENSE-CONSTANT | present | _defense_response(observable, healthy) -> 'COVERED' with no detection consulted |
| D-ENTITY-FIELDNAME | present | cross-source shared_entity edges for the same host values: 0 |
| D-LABEL-IN-SIGNATURE | present | signature family='kerberoast_chain' (the Red scenario name) |
| D-NAME-TABLE | present | behavior_values._FIELDS hand-listed field names: 64 |
| D-NOVEL-UNREACHABLE | present | _search_table distance-value comparisons: none |
| D-SIG-DICT-NOCONTENT | present | actions=['event-0:record', 'event-1:record'] |
| D-SIG-WEB-HTTPVERB | present | behavior_spine=('enumerate', 'c2_exfil', 'enumerate') |
| D-SIG-WIN-SPINE | present | behavior_spine=() actions=['event-0:4624', 'event-1:4769', 'event-2:4688'] |
| D-SINGLE-ITERATION | present | run_hunt reports iterations=1 / 'single-iteration P1 proof' |
| D-UNITS-CAP | present | 700 artifacts -> 512 L1 units by default |
| D-VERDICT-DEADEND | present | modules consuming investigation_verdict besides orchestrator: none |

Reachability of the engine package (static import closure):

| class | modules | lines |
|---|---|---|
| orphan | 0 | 0 |
| production | 11 | 4232 |
| production-lazy | 25 | 12187 |
| script-only | 47 | 17296 |
| tests-only | 7 | 1652 |

## Decisions

| id | stage | status | report | problems |
|---|---|---|---|---|
| D-T1-BASELINE | raised | INCONCLUSIVE | reports/review_eval/6a29bc97d0fd3b97/truth_derivation.json | none |

## Measured (stamped, real corpora only)

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

binding stage: `unmeasured` (all pre-registered paired slices were excluded before product execution)


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

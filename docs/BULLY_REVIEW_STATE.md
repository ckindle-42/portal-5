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
| production | 0 | 0 |
| production-lazy | 27 | 12634 |
| script-only | 56 | 21081 |
| tests-only | 7 | 1652 |

## Decisions

No decision records.

## Measured (stamped, real corpora only)

No real-data report exists yet.

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

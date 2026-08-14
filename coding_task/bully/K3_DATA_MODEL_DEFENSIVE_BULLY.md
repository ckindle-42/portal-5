# DATA MODEL — Defensive Bully

Persistent and important transient structures. Ownership rules: only
`hunt_state.py` touches `hunt_state.db`; only `hunt_organ.py` touches the
`hunt_memory` LanceDB table; only `harvest.py` writes corpus JSONL. Everything
carries provenance. Supersede never deletes.

Conventions: `*_id` fields are stable natural keys; timestamps are epoch
floats (UTC) except display strings; enums are string columns checked in code.

---

## 1. SUB tables (SQLite, `PORTAL5_HUNT_DIR/hunt_state.db`, WAL)

### 1.1 `hunts` — one row per hunt run

| field | type | notes |
|---|---|---|
| hunt_id | TEXT PK | `hunt-<ISO>-<hash8>` |
| started_at / ended_at | REAL | |
| config_version | TEXT | content hash of hunt.yaml + heart.yaml |
| status | TEXT | `running|completed|blocked|stopped` |
| stop_reason | TEXT | plateau / budget / operator / blocked detail |
| neighborhoods | TEXT(JSON) | neighborhoods visited, in order |
| totals | TEXT(JSON) | `{candidates, promoted, killed, blocked}` |

Lifecycle: created at hunt start; closed at stop. Immutable after close
except `status`/`ended_at` on resume. Retention: permanent.

### 1.2 `iterations` — one row per hunt iteration

| field | type | notes |
|---|---|---|
| iteration_id | TEXT PK | `<hunt_id>-i<seq>` |
| hunt_id | TEXT FK | |
| target_cell | TEXT | cell ref chosen by TGT |
| mutation_id | TEXT | FK to mutation spec (nullable) |
| episode_id | TEXT | join to Episode / Splunk / captures |
| verdict_summary | TEXT(JSON) | cousin grade + decomposition snapshot |
| outcome | TEXT | `candidate|no_candidate|blocked|killed` |
| UNIQUE(hunt_id, seq) | | idempotent re-drive |

### 1.3 `cousin_records` — the discovery unit

| field | type | notes |
|---|---|---|
| cousin_id | TEXT PK | `cz-<ISO>-<hash8>` |
| hunt_id / iteration_id / episode_id | TEXT | provenance |
| base_known_id | TEXT | the known record it mutants from |
| mutation_id | TEXT | |
| grade | TEXT | SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS_UNCLASSIFIED |
| composite | REAL | D value |
| decomposition | TEXT(JSON) | `{d1_semantic … d5_detection}` |
| nearest_knowns | TEXT(JSON) | `[(record_id, distance)]` |
| detection_response | TEXT(JSON) | per-detection outcome vector |
| field_signature | TEXT(JSON) | sourcetypes + field histogram |
| behavior_sequence | TEXT(JSON) | ordered step kinds |
| status | TEXT | `suspect|gated|council|pending_operator|promoted|killed` |
| thresholds_version | TEXT | config content hash at grading |
| superseded_by | TEXT | nullable |
| created_at | REAL | |

Mutation rules: `status` transitions only via BIN; content fields immutable
after grading (a re-grade creates a superseding row). Retention: permanent.

### 1.4 `candidates` / gate results (the bin)

| field | type | notes |
|---|---|---|
| candidate_id | TEXT PK | `cb-<…>`; 1:1 with a cousin_record in bin flow |
| gate_results | TEXT(JSON) | `{g0:{pass,evidence[]}, g1a:{…}, g1b:{…}, g2:{…}, g3:{…}}` each with tool version + evidence refs |
| council_record_id | TEXT | FK |
| queue_state | TEXT | `not_queued|pending|confirmed|rejected` |
| decided_by / decided_at / rationale | | operator fields |

### 1.5 `council_records` + `council_opinions`

`council_records`: council_record_id PK, candidate_id FK, roster JSON
(seat→model→family), participation, unresolved bool, review_valid bool,
materiality_version, created_at.
`council_opinions`: opinion row per seat — member_id, model, valid, error,
recommendation, confidence, strongest_objection, missing_evidence JSON,
conditions_to_change JSON, objection_classification `{material, kind,
citations}`, rebuttal JSON (nullable), rebuttal_standing (nullable bool).
Retention: permanent; full dissent preserved.

### 1.6 `known_state` — the negative-result DB (feed 2)

| field | type | notes |
|---|---|---|
| entry_id | TEXT PK | `ks-<…>` |
| subject | TEXT | cell ref (technique × sourcetype × detection neighborhood key) |
| kind | TEXT | `known_benign|known_covered|known_defense|dead_end|recent_kill` |
| penalty | REAL | multiplicative TGT factor (0.0–1.0) |
| confidence_half_life_days | REAL | aging; past it → stale flag, penalty decays toward 1 |
| evidence | TEXT(JSON) | episode/cousin refs (required — no evidence, no entry) |
| superseded_by | TEXT | contradiction handling: new entry supersedes with reason |
| created_at / hunt_id | | |

### 1.7 `detection_baselines` (BR-DRIFT)

| field | type | notes |
|---|---|---|
| detection_id | TEXT | technique/detection key |
| window | TEXT(JSON) | rolling stats: fire_rate mean/stdev, latency, row-shape signature, clause-satisfaction rates, sourcetype completeness |
| sample_count | INT | < MIN → INSUFFICIENT-BASELINE honest flag |
| updated_at / last_episode_id | | |
| PK(detection_id) | | one rolling row per detection |

### 1.8 `drift_flags`

flag_id PK, detection_id, episode_id, class (`TELEMETRY_FAILURE|
ENVIRONMENTAL_CHANGE|DETECTION_DEGRADATION|ATTACKER_EVOLUTION`), score REAL,
detail JSON, routed bool (true when routed to BR-COUSIN), created_at.

### 1.9 `decision_events` — append-only decision log

| field | type | notes |
|---|---|---|
| event_id | TEXT PK | `de-<ISO>-<seq>` |
| hunt_id / iteration_id | TEXT | nullable for operator events |
| actor | TEXT | `system:<component>` or `operator:<id>` |
| kind | TEXT | `target_select|grade|gate|council_block|promote|kill|plateau|roster|playbook|train|config` |
| subject_id | TEXT | cousin/candidate/seat/model/… |
| rationale | TEXT | mandatory |
| data | TEXT(JSON) | factor snapshots, gate detail, etc. |

No updates, no deletes. This is the provenance backbone.

### 1.10 `cost_ledger`

row per hunt (or iteration): hunt_id, tokens_in/out per role JSON, wall_clock
REAL, lab_actions INT, lab_minutes REAL, operator_minutes REAL, unit_costs
JSON (config snapshot), computed cost REAL. Read by TGT/PLT/SCORE.

### 1.11 `plateaus`

plateau_id PK, neighborhood TEXT, series JSON (marginal discovery window),
saturation REAL, decision TEXT, rationale TEXT, created_at, hunt_id.

### 1.12 `promotion_queue`

queue_id PK, item_kind (`cousin_detection|model|playbook|roster`), item_id,
state (`pending|confirmed|rejected`), enqueued_at/from hunt, resolved_by/at,
rationale. **Only operator actors resolve.**

### 1.13 `playbooks` (PLAY)

playbook_id PK, scenario_class TEXT, version INT, instruction_set JSON
(recall priorities, deciding discriminators, common kills, budget shape),
source_hunts JSON, status (`draft|active|retired`), activated_by/at,
superseded_by, created_at. Effectiveness metrics appended as decision events.

### 1.14 `dataset_versions` + `trained_models`

`dataset_versions`: dataset_version PK (content hash), role, window, counts
JSON, splits JSON, manifest_path, created_at.
`trained_models`: model_tag PK, base_model, dataset_version FK, seed,
hyperparams JSON, gguf_path, bench_report JSON (arms comparison + regression
deltas), verdict (`pending|served|rejected|rolled_back`), provenance JSON,
created_at, served_by/at.

### 1.15 `roster_weights`

seat_id, window, weight REAL (bounded 0.5–2.0), rationale JSON
(objection-validity, cousin-call correctness, participation), state
(`proposed|active`), activated_by/at, superseded_by.

---

## 2. ORG records (LanceDB `hunt_memory`)

One row per emission. Schema:

| field | type | notes |
|---|---|---|
| record_id | TEXT PK | `hr-<kind>-<hash>` content-derived |
| text | STRING | canonical narrative (graded facts, not raw blobs) |
| vector | FLOAT[1024] | :8917 embedding |
| kind | STRING | `cousin|kill|benign_pattern|defense|plateau|playbook_delta|detection_change|known_bad` |
| provenance_class | STRING | `hunt_emission|operator_assertion|external_intel` |
| hunt_id / episode_id | STRING | |
| technique_ids / tactic | STRING(JSON) | |
| field_signature | STRING(JSON) | mirrors cousin_records |
| behavior_sequence | STRING(JSON) | |
| detection_response | STRING(JSON) | |
| grade | STRING | where applicable |
| outcome | STRING | promoted/killed/recorded |
| ingested_at | DOUBLE | |

Retention: permanent; `kb_versions`-class time travel is available from
LanceDB but rebuilds go through guarded `rebuild` (operator-initiated).
Mutation: upsert by record_id; corrections supersede (new row +
`supersedes` metadata) — rows are not edited in place for content changes.

**Canonical record text** (what gets embedded): a deterministic rendering of
the record's substantive fields (tactic, technique candidates, field signature
summary, behavior sequence summary, detection outcome summary, grade/outcome,
key rationale) — no timestamps/ids in the embedded text (identity lives in
metadata).

---

## 3. Transient structures

| structure | shape | lifetime |
|---|---|---|
| `Episode` | existing `episode.py:45-74` | per iteration; persisted via existing surfaces + SUB anchor |
| `MutationSpec` | `{mutation_id, base_scenario, variant_params, target_host, budget_class, expected_artifact_contract, parent_known_id}` | one iteration |
| `HuntContext` | SUB snapshot (open cells, known-state view, plateau view, cost view) + config versions | hunt start |
| `RecallResult` | `{hits: [(record_id, distance)], utilization_token}` | per iteration; token recorded on the hunt (feed-1 instrument) |
| `Candidate` | cousin verdict + episode refs + draft detection + gate input bundle | bin flow |
| `CouncilRecord` | INTERFACES I-8 | persisted at gate completion |
| `DriftFlag` | INTERFACES I-9 | persisted same iteration |
| `HandoffPackage` | DESIGN §23 parts, as JSON + rendered files | persisted on promotion |
| `Playbook` (active) | injected context block | per investigation-arm call |

---

## 4. Identity, lifecycle, retention, supersession — summary rules

1. **Identity:** content-derived ids where re-drive must be idempotent
   (records, datasets, model tags); time-derived ids where uniqueness is the
   point (hunts, iterations, events).
2. **Lifecycle:** suspects → gates → council → queue → promoted/killed;
   drafts → active → retired (playbooks); proposed → active (roster);
   pending → served/rejected/rolled_back (models).
3. **Retention:** everything permanent by default. The compounding claim
   depends on history; there is no garbage collection in this build. (A
   future pruning policy is an operator decision, not a design omission.)
4. **Supersession:** corrections create new rows linked by `superseded_by`;
   readers default to current-only views; the superseded chain is always
   queryable (audit + ROSTER retrospection).
5. **Contradiction:** a new known-state entry that contradicts an old one
   supersedes it with the evidence refs that justify the flip (e.g. a cell
   long `known_benign` that just produced a cousin). The decision event
   records the contradiction explicitly — this is the anti-poisoning control:
   flips require evidence and are visible.
6. **Aging/decay:** known-state penalties carry a confidence half-life; stale
   entries decay toward neutral penalty and surface as re-test leads in TGT
   rather than silently governing forever.

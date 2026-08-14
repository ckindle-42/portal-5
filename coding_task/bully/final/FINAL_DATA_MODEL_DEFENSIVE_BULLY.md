# FINAL DATA MODEL — Defensive Bully

Persistent and important transient state. Ownership rules: only
`bully/store.py` touches `hunt_state.db`; only `bully/organ.py` touches the
`hunt_memory` projection; only `bully/harvest.py` writes corpus JSONL.
Everything carries provenance. Supersede never deletes.

Conventions: `*_id` fields are stable natural keys; timestamps epoch floats
(UTC); enums are string columns checked in code (closed sets); JSON fields
are schema-validated before insert with canonical serialization; content
hashes are SHA-256 (algorithm recorded); coordination fields (lease, outbox
attempts, active pointers) use compare-and-swap while truth records are
append-only; foreign keys on; no cascade delete on audit/provenance tables.

Global rules:
- **Append-only + supersede, never delete.** A correction is a new row
  linked by `superseded_by`; readers default to current-only views; the
  superseded chain is always queryable (audit + ROSTER retrospection).
- **Trust tiers:** `VALIDATED`, `OPERATOR_CONFIRMED`, `SUSPECT`,
  `IMPORTED_UNVERIFIED`, `SUPERSEDED`. Only VALIDATED or OPERATOR_CONFIRMED
  records may change promotion priors. Contradictions link both records and
  force review — never averaged away.
- **Retention classes:** AUDIT (indefinite) · EVIDENCE (bytes per configured
  policy; hashes/metadata retained) · DERIVED (rebuildable/expirable) ·
  TRAINING (immutable released artifacts).
- **Seven memory kinds honored** (`case_notebook.py:1-17` doctrine): agent
  scratch is transient; case evidence immutable; the prior-incident library
  is operator-confirm-only; **no agent long-term memory at inference** — ORG
  retrieval feeds the hunt loop's context, never an implicit model memory.
- **Poisoning posture:** production grading/gating is label-blind (BM);
  retrieved knowledge is trust-tagged and cannot introduce tools, scope, or
  policy; a low-authority record cannot alone justify a SAME grading;
  contradiction flips require evidence and are visible.

---

## 1. SUB tables (SQLite WAL, `PORTAL5_HUNT_DIR/hunt_state.db`)

### 1.1 `hunts`

| field | type | notes |
|---|---|---|
| hunt_id | TEXT PK | `hunt-<ISO>-<hash8>` |
| objective / neighborhood_scope | TEXT | authorized scope |
| authorization_ref | TEXT | operator authorization artifact id/hash/expiry |
| config_version | TEXT | content hash of hunt.yaml + heart.yaml snapshot |
| role_snapshot | TEXT(JSON) | resolved model aliases + digests |
| budgets / budgets_used | TEXT(JSON) | iteration/wall/lab-action/mutation |
| stage | TEXT | stage machine enum (DESIGN §7) |
| status | TEXT | `running|completed|blocked|stopped|cancelled|failed` |
| stop_reason | TEXT | plateau / budget / operator / blocked detail |
| lease_owner / lease_expiry | TEXT/REAL | one active lease per hunt (CAS) |
| parent_hunt_id | TEXT | nullable — materially new scope = new hunt, linked |
| started_at / ended_at | REAL | |

Lifecycle: created at authorization; stages advance only via legal
transition commands; immutable after close except resume fields. Retention:
AUDIT.

### 1.2 `iterations`

| field | type | notes |
|---|---|---|
| iteration_id | TEXT PK | `<hunt_id>-i<seq>`; UNIQUE(hunt_id, seq) |
| hunt_id | TEXT FK | |
| target_cell | TEXT | cell ref chosen by TGT |
| mutation_plan_id | TEXT | nullable FK |
| episode_id | TEXT | join to Episode / Splunk / captures |
| assessment_id | TEXT | cousin assessment snapshot ref |
| outcome | TEXT | `candidate|no_candidate|blocked|killed` |
| infrastructure_status | TEXT | valid-trial vs infrastructure-failure (yield math) |

### 1.3 `behavior_signatures`

| field | type | notes |
|---|---|---|
| signature_id | TEXT PK | UNIQUE(episode_ref, signature_algorithm_version, input_manifest_hash) |
| canonical_fingerprint | TEXT | exact-match SAME test |
| action_sequence | TEXT(JSON) | ordered typed verbs/objects |
| event_graph | TEXT(JSON) | entity/event relationships |
| parameter_families | TEXT(JSON) | normalized ranges |
| context_topology | TEXT(JSON) | identities/privilege/hosts/protocols/timing |
| artifacts | TEXT(JSON) | tools/hashes/paths/accounts + cleanup |
| attack_mappings | TEXT(JSON) | ids + tactic + mapping source/version |
| telemetry_shape | TEXT(JSON) | sourcetypes + field histogram + completeness |
| detector_outcomes | TEXT(JSON) | per-detection predicate outcomes/latency |
| evidence_manifest_id | TEXT FK | |
| completeness | REAL | missing dimensions lower this, never renormalize |
| created_at | REAL | |

Lifecycle: computed → superseded by new inputs/algorithm; never edited.
Retention: AUDIT (large derived payloads may follow DERIVED if reproducible).

### 1.4 `cousin_assessments`

| field | type | notes |
|---|---|---|
| assessment_id | TEXT PK | |
| subject_signature_id / reference_signature_id | TEXT FK | |
| candidate_set_id | TEXT FK | sources + health + union/exclusions |
| d_behavior / d_telemetry / d_semantic / d_attack / d_context | REAL | per-dimension decomposition |
| composite | REAL | D |
| relationship | TEXT | SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS_UNCLASSIFIED |
| nonsemantic_channels | INT | ≥2 required for SIMILAR/NEW (check) |
| vetoes | TEXT(JSON) | discriminator contradictions evaluated |
| defense_response | TEXT | COVERED/NEAR_MISS/MISSED/INDETERMINATE — separate axis |
| product_band | TEXT | derived: SIMILAR×MISSED, NEW×NEAR_MISS, ANOMALOUS×blind, SAME×MISSED… |
| nearest_knowns | TEXT(JSON) | `[(record_id, distance)]` |
| confidence / completeness | REAL | |
| algorithm_version / thresholds_version | TEXT | calibration artifact refs |
| explanation | TEXT(JSON) | feature-overlap citations + nearest refs |
| superseded_by | TEXT | nullable |

Mutation rules: content immutable after grading (a re-grade creates a
superseding row). Retention: AUDIT.

### 1.5 `candidates` + `gate_results` (the bin)

`candidates`: candidate_id PK (`cb-<…>`; 1:1 with an assessment in bin flow),
alert_version INT, current_state TEXT (state machine enum), gate_policy_version,
terminal_reason TEXT nullable, queue_state TEXT, decided_by/at, rationale.

`gate_results`: result_id PK, candidate_id FK, gate_id TEXT
(`G-1|G0|G1a|G1b|G2|G4|G3|G5`), attempt INT, outcome TEXT
(`pass|fail|blocked`), validator_version, inputs/evidence JSON, checks/reasons
JSON, created_at. UNIQUE(candidate_id, alert_version, gate_id, attempt).

### 1.6 `council_packets`, `council_opinions`, `objections`, `rebuttals`

`council_packets`: packet_id PK, candidate_id FK, evidence_manifest_id +
hash (frozen), roster snapshot JSON (seat→model alias→family), materiality
_version, created_at.

`council_opinions`: UNIQUE(packet_id, seat_id, attempt); member_id, model,
valid, error, recommendation, confidence, findings JSON, strongest_objection,
missing_evidence JSON, conditions_to_change JSON.

`objections`: objection_id PK, packet_id FK, seat_id, category (enumerated),
material BOOL (code-validated), claim, evidence/missing-proof citations,
status (`open|rebutted|re_review|withdrawn|sustained|waived|superseded`),
due/age, created_at.

`rebuttals`: rebuttal_id PK, objection_id FK, author (model/operator), claim,
evidence citations, requested review, re_review_result nullable, created_at.
Closure records: withdrawal (originating/equivalent seat) or waiver
(operator identity, role, reason, evidence version) — both AUDIT, visible in
handoffs.

### 1.7 `known_state` — the negative-result DB (feed 2)

| field | type | notes |
|---|---|---|
| entry_id | TEXT PK | `ks-<…>` |
| subject | TEXT | coverage-cell key (procedure family/version × detection id/version × environment class × telemetry schema/version) |
| kind | TEXT | `known_benign|known_covered|known_defense|dead_end|recent_kill|disproved|blocked|contradicted` |
| trust_tier | TEXT | only VALIDATED/OPERATOR_CONFIRMED adjusts priors |
| posterior_adjustment | TEXT(JSON) | uncovered-posterior evidence, never a second multiplier |
| applicability | TEXT(JSON) | environment/detection/telemetry bounds |
| confidence_half_life_days | REAL | aging; stale → decay toward neutral + re-test lead |
| evidence | TEXT(JSON) | episode/assessment refs (required — no evidence, no entry) |
| contradiction_links | TEXT(JSON) | forced-review links |
| superseded_by | TEXT | contradiction handling |
| created_at / hunt_id | | |

KNOWN_COVERED requires a deployment receipt + successful post-deploy replay
(check constraint + application rule).

### 1.8 `detection_baselines` + `drift_flags`

`detection_baselines`: baseline key = hash(procedure family, detection
id/version, environment fingerprint, telemetry schema version, policy
version); status (`warmup|active|superseded`); window membership; rolling
stats (fire rate mean/stdev, latency, row-shape signature, clause-satisfaction
rates, sourcetype completeness; median/MAD/EWMA state); sample_count (< MIN →
INSUFFICIENT-BASELINE); model_canary_ref; updated_at, last_episode_id.

`drift_flags`: flag_id PK, detection_id, episode_id, class
(`TELEMETRY_DEGRADATION|ENVIRONMENT_CHANGE|ATTACKER_EVOLUTION|
DETECTION_DEGRADATION|UNCLASSIFIED`), score REAL, signals/bands/breaches
JSON, consecutive_count INT, routed BOOL (true → BR-COUSIN), created_at.

### 1.9 `decision_events` — append-only, hash-chained

| field | type | notes |
|---|---|---|
| event_id | TEXT PK | `de-<ISO>-<seq>`; UNIQUE(aggregate_type, aggregate_id, aggregate_version) |
| hunt_id / iteration_id | TEXT | nullable for operator events |
| actor | TEXT | `system:<component>` or `operator:<id>` (+ role) |
| kind | TEXT | `target_select|grade|gate|council_block|objection|waiver|promote|kill|plateau|roster|playbook|train|config|recall|impact` |
| subject_id | TEXT | cousin/candidate/seat/model/… |
| rationale | TEXT | mandatory |
| data | TEXT(JSON) | factor snapshots, gate detail, versions |
| prev_event_hash / chain_hash | TEXT | tamper-evidence (not a backup substitute) |
| occurred_at / recorded_at | REAL | |

No updates, no deletes. The provenance backbone.

### 1.10 `index_outbox`

| field | type | notes |
|---|---|---|
| outbox_id | TEXT PK | UNIQUE(record_type, record_id, record_version, projection_version) |
| source_hash | TEXT | must equal the authoritative record hash before completion |
| operation | TEXT | upsert/tombstone |
| required_for_closure | BOOL | dead letter with required=true blocks hunt closure |
| status | TEXT | `pending|leased|completed|dead_letter` (CAS) |
| attempts / next_attempt / error | | bounded exponential retry |
| completed_at / projected_row_hash | TEXT | |

### 1.11 `recall_receipts` + `decision_impacts`

`recall_receipts`: recall_id PK (unique per hunt/stage/source watermark),
query/filters/trust policy JSON, source/projection/embedding/reranker
versions, source health, candidates/scores JSON, exclusions JSON, selected
context JSON, token budget, created_at. Immutable; persisted even when
empty/degraded.

`decision_impacts`: impact_id PK, recall_id FK, consuming decision ref,
before/after candidate ranking or action set JSON, cited recalled record ids,
change_kind (`SELECTED|DEPRIORITIZED|AVOIDED|CONTROL_ADDED|NO_EFFECT`),
explanation, created_at. Immutable. This is the auditable compounding chain.

### 1.12 `cost_ledger`

row per hunt/iteration per meter: lab_minutes, inference calls/tokens/latency,
analyst_minutes, replay_work, storage_bytes, training_allocation,
measurement_quality, pricing_profile_version, computed_units REAL.
Missing material measurement = NULL + quality flag — blocks ROI claims, never
zero.

### 1.13 `plateaus`

plateau_id PK, neighborhood, qualifying trial ids JSON (≥8 trials, ≥2
dimensions), promotions INT, unique_response_gain REAL, posterior upper bound
REAL, saturation REAL (secondary signal), policy_version, decision
(`CONTINUE|PLATEAU|INSUFFICIENT`), reset_trigger/version nullable,
override/expiry nullable, created_at, hunt_id.

### 1.14 `promotion_queue`

queue_id PK, item_kind (`cousin_detection|model|playbook|roster|waiver|
policy`), item_id, state (`pending|confirmed|rejected`), enqueued_at/from
hunt, resolved_by/at, rationale. **Only operator actors resolve** (check +
application rule); each action kind is a separate command.

### 1.15 `playbooks` (PLAY)

playbook_id PK, scenario_class, version INT, content_hash, instruction_set
JSON (recall priorities, deciding discriminators, common kills, budget shape,
stop rules, fallback), source_hunts JSON, status (`draft|replay_validated|
canary|awaiting_operator|active|retired|rolled_back`), active pointer CAS per
scenario_class, replay/canary results JSON, activated_by/at, superseded_by,
created_at. Effectiveness metrics appended as decision events.

### 1.16 `dataset_versions` + `training_examples` + `trained_models`

`training_examples`: example_id PK (content/evidence fingerprint), role
(hunter/analyst/disprover/cousin-smeller), input/output, provenance JSON
(hunt_id, episode_id, models, distances, outcome, trust_tier), group tags
(family/campaign/time), leakage/oracle flags, consent/licensing class, split
restriction, quarantine/exclusion reason, transformation version, superseded_by.

`dataset_versions`: dataset_version PK (content hash), role, window, counts
JSON, split manifest JSON (family/campaign/time groups; test frozen before
harvest window), dedup/leakage report JSON, replay-mix sources, approval ref,
manifest_path, created_at. Immutable after release.

`trained_models`: model_tag PK, base_model + digest, dataset_version FK,
seed, hyperparams JSON, toolchain versions JSON, gguf_path + hash,
five_arm_report JSON, intake/canary reports JSON, acceptance_policy_version,
verdict (`pending|served|rejected|rolled_back|declined_no_gain|
training_failed`), provenance JSON, active alias before/after, created_at,
served_by/at.

### 1.17 `roster_records`

record_id PK, seat_id, window, independence family, capability/evaluation
suite versions, citation validity, objection precision/recall, cousin-call
correctness, abstention quality, latency/cost, eligibility
(`candidate|eligible|probation|ineligible|retired`), advisory_weight REAL
(bounded [0.5, 2.0] — ordering only), rationale JSON, state
(`proposed|active`), activated_by/at, superseded_by. Updated only from
outcomes unavailable to the reviewer at decision time.

### 1.18 `evidence_manifests` + `evidence_items`

`evidence_manifests`: manifest_id PK, episode/attempt refs, required-type
list, present items, completeness score + reasons, created_at.
`evidence_items`: evidence_id PK, type, URI/path token, content hash, byte
size, media/encoding, capture/source times, source actor/system,
synthetic/redacted flags, access class, verification status/time,
retention/hold, parent evidence, parser/normalizer version.
Lifecycle: declared → verified/invalid/quarantined/expired-by-policy. Bytes
live in the existing capture store; never changed in place. Redaction =
tombstone + audit event without falsifying the original hash.

### 1.19 `soc_deliveries`

delivery_id PK + stable correlation marker; alert/version, destination/config
version, redacted payload hash, producer ack, consumer query/read object,
send/visible times, latency, SLO, load profile, content-integrity result,
failure. Lifecycle: intended → sent → visible/failed/unknown. G3 cites the
passing receipt.

### 1.20 `detection_proposals` (HND)

proposal_id PK + version; promoted alert ref; family/delta/evidence/replay
bundle; affected cells/detections; proposed rule/query + content hash;
positive/negative tests; noise estimate; telemetry assumptions;
rollout/rollback; owner/expiry; proof-leg results (fires-on-attack,
quiet-on-benign, no-regression); disposition/deployment/coverage-validation
refs. Lifecycle: draft → submitted → accepted/revise/rejected/expired →
deployed → replay-validated/failed → retired.

### 1.21 `validation_results`

result_id PK (unique for claim/test/input hashes/attempt), claim id/type,
method/suite/case versions, inputs, expected/observed, pass/fail/block/skip
(required skips never aggregate as pass), evidence ids, resource metrics,
failure meaning, synthetic flag, created_at.

---

## 2. ORG records (LanceDB `hunt_memory` projection)

One row per emission. Schema:

| field | type | notes |
|---|---|---|
| record_id | TEXT PK | `hr-<kind>-<hash>` content-derived |
| text | STRING | canonical narrative (graded facts, not raw blobs) |
| vector | FLOAT[1024] | :8917 embedding (dim per current service) |
| kind | STRING | `cousin|kill|benign_pattern|defense|plateau|playbook_delta|detection_change|known_bad|objection` |
| trust_tier | STRING | mirrors SUB tiers |
| provenance_class | STRING | `hunt_emission|operator_assertion|external_intel` |
| hunt_id / episode_id | STRING | |
| technique_ids / tactic | STRING(JSON) | |
| field_signature / behavior_sequence / detection_response | STRING(JSON) | mirrors signatures |
| relationship / product_band | STRING | where applicable |
| outcome | STRING | promoted/disproved/recorded |
| source_record_id / source_hash | STRING | dereference + validation against SUB |
| projection_version | STRING | schema + embedding model version |
| ingested_at | DOUBLE | |

Retention: DERIVED — disposable; rebuild by replay from SUB. Mutation:
upsert by record_id via the outbox; corrections supersede (new row +
supersedes metadata). Rows are never legal truth inputs until dereferenced
and hash-validated against SUB.

**Canonical record text** (what gets embedded): a deterministic rendering of
the record's substantive fields (tactic, technique candidates, field-signature
summary, behavior-sequence summary, detection-outcome summary, relationship/
band, key rationale) — no timestamps/ids in the embedded text (identity lives
in metadata).

---

## 3. Transient structures

| structure | shape | lifetime |
|---|---|---|
| `Episode` | existing `episode.py:45-74` | per iteration; persisted via existing surfaces + SUB anchor |
| `MutationPlan` | contracts.py DTO (I-1) | one iteration; persisted as a record |
| `HuntContext` | SUB snapshot (open cells, known-state view, plateau view, cost view) + config versions | hunt start |
| `RecallReceipt` / `DecisionImpact` | I-4 | persisted (AUDIT) |
| `Candidate` | assessment + episode refs + draft detection + gate bundle | bin flow; persisted |
| `CouncilRecord` | I-8 | persisted at gate completion |
| `DriftFlag` | I-9 | persisted same iteration |
| `HandoffPackage` | DESIGN §23 parts, JSON + rendered files | persisted on promotion |
| `Playbook` (active) | injected context block | per investigation-arm call |
| `EngagementCheckpoint` | stage + counters + resume token | per stage; superseded by next checkpoint |

---

## 4. Identity, lifecycle, retention, supersession — summary rules

1. **Identity:** content-derived ids where re-drive must be idempotent
   (records, signatures, assessments, datasets, model tags); time-derived ids
   where uniqueness is the point (hunts, iterations, events); UUIDv7 or
   Portal-native ids at boundaries.
2. **Join keys:** `hunt_id`, `iteration_id`, `episode_id`, `signature_id`,
   `assessment_id`, `candidate_id`, `detection_id`, `cell_key`,
   `dataset_version`, `model_tag`. Technique ids are coverage **tags**, not
   join keys.
3. **Lifecycle:** candidate states per the bin machine; hunt stages per the
   orchestrator machine; playbooks/models/roster per their lifecycles
   (DRAFT→…→ACTIVE→RETIRED / proposed→active). State never moves backward;
   corrections supersede.
4. **Retention:** AUDIT rows permanent by default — the compounding claim
   depends on history. EVIDENCE bytes per configured policy with hashes
   retained. DERIVED rebuildable. TRAINING artifacts immutable.
5. **Supersession:** corrections create new rows linked by `superseded_by`;
   current-only views by default; full chains queryable.
6. **Contradiction:** a new known-state entry that contradicts an old one
   supersedes it with justifying evidence refs; the decision event records
   the contradiction explicitly (the anti-poisoning control: flips require
   evidence and are visible; contradictions force review, never average).
7. **Aging/decay:** known-state priors carry a confidence half-life; stale
   entries decay toward neutral and surface as re-test leads in TGT rather
   than silently governing forever. ORG decay is a ranking down-weight, never
   removal.
8. **Required database constraints:** unique idempotency keys + aggregate
   versions; FKs from every proof/decision to exact input versions; checks
   preventing `synthetic=true` evidence from passing G0 or promoting; checks
   preventing PROMOTED without passing gates + a G5 record; checks preventing
   KNOWN_COVERED without deployment + post-deploy replay validation; one
   active lease per hunt, one active playbook per class, one active model
   alias per role; outbox source-hash equality before completion; closed
   enums; no cascade delete on audit tables.

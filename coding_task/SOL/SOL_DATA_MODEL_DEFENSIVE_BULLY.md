# Defensive Bully Data Model

## Global rules

SQLite WAL at `${PORTAL_DATA_DIR}/security/defensive_bully/bully.sqlite3` is authoritative. Schema migrations are monotonic and recorded in `schema_migration`. Raw evidence and large model artifacts are content-addressed external files; the database stores references and hashes. LanceDB is a disposable projection.

All durable domain rows include, directly or through their parent: UUIDv7 ID, integer `version`, `created_at`, `created_by`, `correlation_id`, schema/config/algorithm versions, and optional `supersedes_id`. Mutable coordination fields (lease, active pointer, outbox attempts) use compare-and-swap; truth records are append-only. Foreign keys are enabled. Enumerations reject unknown values. JSON fields are schema-validated before insert and have canonical serialization/hashes.

Retention classes are:

- **AUDIT:** indefinite unless a documented security/legal retention policy is stricter; decision events, authority, promotions, waivers, provenance.
- **EVIDENCE:** configured retention with legal hold; metadata/hash retained after permitted byte expiry.
- **DERIVED:** rebuildable/expirable; projection, caches, sufficient statistics.
- **TRAINING:** immutable released dataset/model artifacts under model-retention policy.

Deletion is never used to correct truth. A new row supersedes the prior row and records reason/actor. Redaction creates a tombstoned reference plus a redaction audit event without falsifying the original hash.

## Relational integrity summary

```text
hunt 1--* hunt_attempt 1--1 episode_ref 1--* evidence_item
  |          |                 |
  |          +--* behavior_signature --* cousin_assessment
  |          +--* temporal_sample --> temporal_baseline/assessment
  +--* target_decision / cost_record / plateau_assessment
  +--* promotion_alert --* gate_result --* council_packet
                              |             +--* opinion --* objection --* rebuttal
                              +--> soc_delivery
promotion --> detection_proposal / training_example / playbook_version
all knowledge records --> decision_event + index_outbox --> projection
```

## Hunt

**Owner:** SUB. **Identity:** `hunt_id`; versions append events, while the current projection row uses optimistic `state_version`. **Required fields:** objective, neighborhood/coverage scope, authorization ID/hash/expiry, effective configuration hash, role snapshot, budget limits/used, stage, outcome, lease owner/expiry, start/end, block/cancel reason. **Lifecycle:** draft through closed/blocked/cancelled/failed as defined in final design. **Provenance:** creator/approvers and config/policy versions. **Retention:** AUDIT. **Mutation:** only legal transition commands; counters atomically increment. **Supersession:** a materially new objective/scope is a new hunt linked by `parent_hunt_id`, not an edit.

## Hunt attempt and Episode reference

**Owner:** SUB for attempt; Episode adapter for reference. **Identity:** `attempt_id`; unique `(hunt_id, attempt_no)` and unique external execution idempotency key. **Required attempt fields:** target decision, mutation plan/version, execution intent/status, replay/control kind, clean-snapshot ID, timestamps, infrastructure/valid-trial status. `episode_ref` includes Portal Episode ID, red/telemetry/detection/response statuses, target/environment, time window, evidence-manifest ID, synthetic flag, external result reference. **Lifecycle:** intended → dispatched → completed/failed/unknown; unknown requires receipt reconciliation. **Retention:** AUDIT/EVIDENCE. **Mutation:** status CAS only; result immutable. **Supersession:** retries are new attempts; Episode corrections append a new reference version.

## Evidence manifest and item

**Owner:** evidence service; bytes owned by capture store. **Identity:** `manifest_id`; item `evidence_id`; unique `(hash_algorithm, content_hash, logical_type, source_ref)` where applicable. **Required fields:** type, URI/path token, content hash, byte size, media/encoding, capture/source times, source actor/system, episode/attempt, synthetic/redacted flags, access class, verification status/time, retention/hold, parent evidence, parser/normalizer version. A manifest has required-type list, present items, completeness score and reasons. **Lifecycle:** declared → verified/invalid/quarantined/expired-by-policy. **Provenance:** full source and chain. **Retention:** EVIDENCE; hashes/metadata AUDIT. **Mutation:** bytes never changed in place. **Supersession:** normalized/derived item cites parents; redaction/tombstone is an audit-linked new status.

## Behavior signature and cousin representation

**Owner:** BR-COUSIN. **Identity:** `signature_id`; unique `(episode_ref_id, signature_algorithm_version, input_manifest_hash)`. **Required fields:** canonical fingerprint; ordered typed actions; entity/event graph; normalized parameter families; identity/privilege; asset/topology/protocol/timing; artifacts; ATT&CK mappings/version/source; telemetry distributions/completeness; detector predicates/latency/visibility; per-feature evidence IDs; completeness and hard-feature flags. **Lifecycle:** computed → superseded by new inputs/algorithm; never edited. **Retention:** AUDIT, large derived payload may follow DERIVED policy if reproducible. **Mutation:** none. **Supersession:** explicit link.

`candidate_set` records query signature, each source health/version, source-ranked IDs, union/deduplication, exclusions, and requested top-K. `cousin_assessment` is keyed by subject/reference signatures and assessment algorithm version. It stores all five structural distances, aggregate `D`, relationship enum, two-or-more non-semantic relation proofs, a separate detector-response divergence vector and defense-response enum, evidence completeness/confidence, threshold/calibration version, reason codes, and assessor provenance. Relationship and response columns are never collapsed into one label.

## Coverage cell and known outcome

**Owner:** ORG/SCORE. **Identity:** `coverage_cell_id` is a canonical hash of procedure family/version, detection ID/version (or no-detector sentinel), environment class/version, and telemetry schema/version. **Required fields:** components, active/superseded status, first/last observed. Known outcome is one of `KNOWN_DEFENSE`, `KNOWN_BENIGN`, `KNOWN_COVERED`, `DISPROVED`, `BLOCKED`, `CONTRADICTED`, with evidence, applicability bounds, trust tier, confidence policy, valid-from/until, source decision, and contradiction links. **Lifecycle:** proposed/suspect → validated/operator-confirmed → expired/superseded/contradicted. **Retention:** AUDIT. **Mutation:** confidence is a derived new version; raw outcomes append. **Supersession:** detector/environment/telemetry change creates a new coverage cell; never transfers covered status automatically.

`KNOWN_DEFENSE` means a relevant defensive mechanism exists and has evidence; `KNOWN_COVERED` requires successful replay through a deployed detector/version; `KNOWN_BENIGN` is a context-bounded causal judgment, not a global technique label.

## Detection state

**Owner:** HND/detection integration. **Identity:** `(detection_id, detection_version, environment_class, telemetry_schema_version)`. **Required fields:** rule/content hash or opaque external version, status, owner, deployment receipt, predicate contract, telemetry dependencies, positive/negative replay results, coverage cells, effective/retired times. **Lifecycle:** observed/proposed/deployed/validated/degraded/retired. **Retention:** AUDIT. **Mutation:** new external rule produces new version. **Supersession:** retirement and successor link; coverage must be re-proven.

## Temporal baseline, sample, and assessment

**Owner:** BR-DRIFT. **Identity:** baseline key hashes procedure family, detection version, environment fingerprint/class, telemetry schema, and temporal-policy version. **Required baseline fields:** warm-up/active/superseded status; window membership; scalar median/MAD/EWMA state; event-distribution reference; minimum samples; critical/consecutive bounds. Samples include signature/episode/control IDs, sequence distance, event vector, predicate satisfaction, alert latency, telemetry completeness, control/environment health, and sample eligibility. Assessments store signal bands/breaches, consecutive count, cause enum, confidence/reason, and input sample/baseline versions. **Lifecycle:** warm-up → active → superseded; assessment append-only. **Retention:** samples EVIDENCE/AUDIT; sufficient statistics DERIVED. **Mutation:** one sample contributes once. **Supersession:** any key-component/policy change starts a new baseline.

## Decision event

**Owner:** store/events service. **Identity:** monotonically sortable `event_id`, unique domain `(aggregate_type, aggregate_id, aggregate_version)`. **Required fields:** event type/schema, aggregate/version, actor/action/authority, occurred/recorded time, correlation/causation IDs, canonical payload/hash, previous event hash and chain hash. **Lifecycle:** append only. **Retention:** AUDIT. **Mutation/supersession:** none; corrective event references erroneous event. Event hash chaining detects local tampering but does not replace access control/backups.

## Index outbox and projection record

**Owner:** ORG. **Identity:** unique `(record_type, record_id, record_version, projection_version)`. **Required fields:** event/source hash, operation, required-for-closure flag, status, attempts/next attempt/error, lease, completed time, projected row/hash. **Lifecycle:** pending → leased → completed or dead-letter; repair can return dead-letter to pending with audit event. **Retention:** AUDIT for receipt; projection DERIVED. **Mutation:** coordination fields CAS. **Supersession:** new source/projection version creates a new entry; removal is represented by a tombstone projection.

## Recall receipt and decision impact

**Owner:** ORG then consuming component. **Identity:** `recall_id`, unique per hunt/stage/source watermark; `impact_id` per consuming decision. **Required fields:** query/filters/trust policy, source/projection/embedding/reranker versions, source health, candidates/scores, exclusions, selected context/token budget. Impact records before/after candidate ranking or action set, cited recalled records, change kind (`SELECTED`, `DEPRIORITIZED`, `AVOIDED`, `CONTROL_ADDED`, `NO_EFFECT`), and deterministic/model explanation. **Lifecycle:** immutable. **Retention:** AUDIT. **Mutation:** none. **Supersession:** new watermark/decision creates a new receipt/impact.

## Promotion alert and gate result

**Owner:** BIN. **Identity:** `alert_id` with `alert_version`; linked to one assessment/evidence manifest. **Required fields:** relationship/response, impact claim, current state/outcome, gate-policy version, terminal reason, operator requirement. Gate result has gate ID, attempt, pass/fail/block, validator version, exact inputs/evidence, checks/reasons, time. **Lifecycle:** legal forward state graph only. **Retention:** AUDIT. **Mutation:** compare-and-swap current projection plus append event/result. **Supersession:** changed evidence/claim creates new alert version and invalidates downstream passes.

## Council opinion, objection, and rebuttal

**Owner:** HEART. **Identity:** `packet_id`; unique opinion `(packet_id, seat_id, attempt)`; `objection_id`; `rebuttal_id`. **Required opinion fields:** roster/model/prompt/inference versions, disposition, findings, evidence citations, missing evidence, strongest objection, conditions to change, parse/abstention. Objection stores category, materiality, claim, evidence/missing-proof citation, status, originating seat, due/age. Rebuttal stores author, claim, evidence citations, target objection, requested review. Closure stores withdrawal reviewer or operator waiver authority/reason. **Lifecycle:** objection open → rebutted/pending re-review → withdrawn, sustained, waived, or superseded. **Retention:** AUDIT. **Mutation:** append statuses. **Supersession:** new packet for changed evidence; old objections remain visible.

## SOC delivery

**Owner:** SOC adapter. **Identity:** delivery ID and stable correlation marker. **Required fields:** alert/version, destination/config, redacted payload hash, producer acknowledgment, consumer query/read object, send/visible times, latency, SLO, load profile, content-integrity result, failure. **Lifecycle:** intended → sent → visible/failed/unknown. **Retention:** AUDIT. **Mutation:** append attempt/receipt. **Supersession:** redelivery is a new attempt; G3 cites the passing receipt.

## Cost record, target score, and statistics

**Owner:** SCORE. **Identity:** cost record per hunt/attempt and source meter; target-score record per decision/cell. **Required cost fields:** lab minutes, inference calls/tokens/latency, analyst minutes, replay, storage, training allocation, source/measurement quality, pricing-profile version, total units. Target score stores hard eligibility, each raw factor, Beta posterior parameters and 95% lower/upper bound, value, estimated cost, priority, exclusions, tie-break. Statistics store valid successes/trials and observation watermark. **Lifecycle:** estimated → final/superseded; observations append, sufficient statistics derive. **Retention:** AUDIT; caches DERIVED. **Mutation:** missing is null plus quality, never zero. **Supersession:** correction creates new record and recomputes downstream state.

## Plateau

**Owner:** PLT. **Identity:** neighborhood plus plateau-policy/version and assessment watermark. **Required fields:** qualifying trial IDs/window, mutation dimensions, promotions, unique response-state gain, posterior upper bound, thresholds, decision (`CONTINUE`, `PLATEAU`, `INSUFFICIENT`), reset trigger/version, override/expiry. **Lifecycle:** insufficient → continue/plateau → reset/superseded. **Retention:** AUDIT. **Mutation:** none. **Supersession:** new valid trial or reset creates a new assessment.

## Detection proposal and promotion

**Owner:** HND. **Identity:** `proposal_id/version`. **Required fields:** promoted alert; family/delta/evidence/replay bundle; affected cells/detections; proposed rule/query and content hash; positive/negative tests; noise estimate; telemetry assumptions; rollout/rollback; owner/expiry; disposition/deployment/coverage validation references. **Lifecycle:** draft → submitted → accepted/revise/rejected/expired → deployed → replay-validated/failed → retired. **Retention:** AUDIT/EVIDENCE. **Mutation:** revisions append. **Supersession:** revised or successor detection links prior proposal.

## Playbook

**Owner:** PLAY. **Identity:** stable playbook ID plus immutable semantic version/content hash. **Required fields:** applicability, prerequisites, allowed actions, budgets, recall/controls/stop/fallback, source decisions, generator, replay/canary results, status, active-pointer receipt, rollback version. **Lifecycle:** draft → replay-validated → canary → awaiting operator → active → retired/rolled back. **Retention:** AUDIT. **Mutation:** content creates new version; active pointer CAS. **Supersession:** explicit successor; old version executable only for replay.

## Training example

**Owner:** HARV. **Identity:** content/evidence fingerprint plus example version. **Required fields:** source decisions/evidence hashes, input/target or preference pair, relationship/response labels, objection/rebuttal content, role/task, trust tier, family/campaign/time groups, split restrictions, leakage/oracle flags, secret/PII/licensing status, transformation version, quarantine/exclusion reason. **Lifecycle:** candidate → quarantined/eligible → included in dataset → superseded/revoked. **Retention:** TRAINING/AUDIT. **Mutation:** correction is a new version. **Supersession:** released datasets remain reproducible and record later revocation.

## Dataset version

**Owner:** TRAIN. **Identity:** dataset content hash and semantic version. **Required fields:** ordered example versions/hashes, schema/transformation, frozen cutoff, train/validation/test split manifest, group allocations, dedup/leakage report, class/role statistics, replay-mix sources, approval, storage artifact hash. **Lifecycle:** draft → validated → released → deprecated/revoked. **Retention:** TRAINING. **Mutation:** immutable after release. **Supersession:** any example/split change creates a new version.

## Trained model and model provenance

**Owner:** TRAIN/model lifecycle. **Identity:** `model_version_id`, artifact digest, and immutable Ollama tag. **Required fields:** role, base model identity/digest/license, dataset hash, code commit/toolchain/config/seeds, resource profile, checkpoints/adapter/merged/GGUF hashes, five-arm evaluation, acceptance-policy/result, import/canary/promotion/rollback receipts, active alias before/after. **Lifecycle:** planned → training → trained → evaluated → rejected/accepted → exported → imported → canary → active → retired/rolled back/failed. **Retention:** TRAINING/AUDIT; failed large checkpoints follow policy after metadata retention. **Mutation:** append lifecycle events; artifact immutable. **Supersession:** alias pointer selects a new version; rollback selects a retained prior version.

## Roster record

**Owner:** ROSTER. **Identity:** reviewer/model artifact plus role and evaluation-policy version. **Required fields:** independence family, capabilities, suite/version, citation validity, objection precision/recall, calibration/abstention, latency/cost, health, eligibility/probation/expiry, evidence watermark. **Lifecycle:** candidate → eligible/probation/ineligible/retired. **Retention:** AUDIT. **Mutation:** new evaluation creates a version. **Supersession:** current eligibility pointer; never changes historical packet roster.

## Validation result

**Owner:** relevant deterministic validator or validation runner. **Identity:** result ID unique for claim/test/input hashes/attempt. **Required fields:** claim ID/type, method/suite/case versions, inputs, expected/observed behavior, pass/fail/block/skip, evidence IDs, resource metrics, failure meaning, synthetic flag. **Lifecycle:** immutable attempt; aggregation derives release status. **Retention:** AUDIT/EVIDENCE. **Mutation:** none. **Supersession:** rerun is a new attempt; required skips never aggregate as pass.

## Promotion and supersession records

Any consequential activation uses a generic `promotion_record`: subject type/ID/version, from/to state or pointer, prerequisite validation IDs, authenticated approver/role, reason, time, policy version, rollback target, expiry where applicable. `supersession` stores old/new subject, reason/category, actor, time, and whether downstream derivations are invalidated. Both are AUDIT, append-only, and cannot be cascaded away.

## Required database constraints

- unique domain idempotency keys and aggregate event versions;
- foreign keys from every proof/decision to exact input versions;
- checks preventing `synthetic=true` evidence from a passing G0 or promotion;
- checks preventing `PROMOTED` without passing G0–G4 and a G5 promotion record (application and deferred integrity audit; SQLite trigger where practical);
- checks preventing known-covered without deployment and post-deploy replay validation;
- one active lease per hunt, active playbook per applicability key, and active model alias per role;
- outbox source hash must equal authoritative record hash before completion;
- trust-tier and status enums are closed;
- no cascade delete on audit/provenance tables.

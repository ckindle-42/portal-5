# FINAL INTERFACES — Defensive Bully

Contracts between major components. Format per interface: PRODUCER /
CONSUMER / PURPOSE / INPUT / OUTPUT / STATE EFFECT / FAILURE SEMANTICS /
PROVENANCE / IDEMPOTENCY-RETRY / OPERATOR BOUNDARY. Types reference
`FINAL_DATA_MODEL_DEFENSIVE_BULLY.md`. Existing-code anchors cited at HEAD
`47d3e884` (re-verify at build HEAD). Boundary DTOs are immutable,
schema-versioned, JSON-serializable (`bully/contracts.py`); every command
carries `command_id`, `idempotency_key`, `expected_version`, `actor`,
`correlation_id`.

Cross-cutting guarantees (apply unless overridden): code-decided outputs are
deterministic; synthetic evidence never passes a promotion gate; production
paths are label-blind (BM); missing capability fails honest-BLOCKED; every
persisted record carries provenance; consequential promotions halt for an
authorized operator.

---

## I-1. Red direction (bully → Red)

**Interface:** compiled `MutationPlan` → scenario overlay, consumed by the
existing Red scenario machinery (`exec_chain._prepare_scenario:3071` /
`BenchConfig.set_scenario`; `_run_chain_test:3564`, unchanged).

- PRODUCER: MUT (`bully/mutation.py`)
- CONSUMER: Red execution (`exec_chain`, unchanged)
- PURPOSE: tell Red *which* cousin to manufacture, never *how* to execute
- INPUT: a validated MutationPlan (reference scenario, typed operators,
  invariants, expected observables, controls, replay policy, allowed
  targets/tools, cleanup, approval ref, budget class, idempotency key)
- OUTPUT: a rendered scenario overlay (`red_prompt`, `red_order`, expectation
  metadata) handed to the unchanged executor
- STATE EFFECT: none on bully state (the resulting Episode is the effect);
  plan + validation + approval persisted
- FAILURE SEMANTICS: validation failure (unknown operator, invariant
  conflict, scope violation via `perception.assert_in_lab:46-53`, budget
  exceeded, missing control) → rejected; no Red call; decision event
  recorded; iteration honest-BLOCKED. Never partially compiled.
- PROVENANCE: plan carries `plan_id`, reference record id, operator lineage,
  proposer invocation, approval reference
- IDEMPOTENCY/RETRY: re-rendering the same plan version yields a
  byte-identical overlay (pure function); execution dedupes on the
  idempotency key
- OPERATOR BOUNDARY: mutation budget values are operator config; new/widened
  mutation classes require explicit operator confirmation

## I-2. Episode (Red → bully) — EXISTING, UNCHANGED

- PRODUCER: purple/bench flow (`blue.py::run_purple_tests:1941`,
  `_score_purple:1519`; `episode.py`)
- CONSUMER: LOOP (`bully/orchestrator.py`) via the Episode adapter
- PURPOSE: the truth-plane input contract — reason-coded axes + evidence refs
- INPUT: red result, telemetry status, detection correlations
- OUTPUT: `Episode` dataclass (`episode.py:45-74`) + verdict via
  `derive_verdict` (`:146-183`); persisted per existing surfaces
- STATE EFFECT: recorded into SUB as the iteration's anchor (immutable
  reference + evidence manifest)
- FAILURE SEMANTICS: telemetry failures arrive as reason codes → INDETERMINATE
  (existing); LOOP treats INDETERMINATE as blocked, never as miss/pass
- PROVENANCE: `episode_id` is the join key across SUB/ORG/Splunk
- IDEMPOTENCY/RETRY: re-consuming the same episode_id updates the same SUB
  rows
- OPERATOR BOUNDARY: none (deterministic). No operator can relabel
  synthetic/unverified evidence as real.

**Reconciliation note:** `agentic_blue_eval.py:82-91`'s local Episode is the
capture replay DTO (comment-level documentation only); the truth-plane
`episode.py::Episode` is the only Episode in the bully. The investigation-arm
adapter accepts a live Episode, not only the replay DTO.

## I-3. Hunt loop (operator/CLI → system; system internal driver)

- PRODUCER/CONSUMER: `commands/hunt_modes.py` ↔ `bully/orchestrator.py`
- PURPOSE: run/resume/status/cancel a hunt
- INPUT: `{neighborhood: str|"auto", budget_class, dry_run, resume_id?}` +
  config from `config/security/hunt.yaml` + `heart.yaml`; operator
  authorization for creation
- OUTPUT: hunt report `{hunt_id, iterations, candidates graded, promotions to
  queue, plateau/stop reason, cost summary}`; exit code per bench-CLI
  semantics (nonzero on honest-BLOCKED)
- STATE EFFECT: full SUB/ORG writes per iteration (DESIGN §7); stage machine
  `DRAFT → AUTHORIZED → RECALL_READY → TARGETED → MUTATION_READY → EXECUTING
  → ANALYZING → PROMOTING → COMPOUNDING → CLOSED` (+ BLOCKED/CANCELLED/
  FAILED); lease + idempotency keys
- FAILURE SEMANTICS: any gate/infra failure → recorded; run exits honestly;
  crash → lease expiry + resume from last committed event; cancel revokes
  leases, never deletes evidence
- PROVENANCE: `hunt_id` on every emitted record; per-hunt config snapshot
- IDEMPOTENCY/RETRY: `--resume <hunt_id>` continues from SUB state; natural
  keys prevent double-record; duplicate command key returns the original
  receipt
- OPERATOR BOUNDARY: operator starts/stops/authorizes hunts; the loop never
  self-schedules (daemon is a future extension); admission control checks lab
  locks and bench-supervisor activity before lab actions

## I-4. Knowledge organ (ORG)

Module-internal API of `bully/organ.py` (NOT an MCP tool):

```python
upsert(record: HuntRecord) -> None                      # via outbox worker
knn(query: str | BehaviorSignature, k: int, filters: dict) -> list[tuple[HuntRecord, float]]
recall(context: HuntContext, k: int) -> RecallReceipt   # mandatory pre-hunt
index_emissions(iteration: IterationEmissions) -> None  # universal, outbox-coupled
stats() -> OrganStats
```

- PRODUCER: all bully components (writes via outbox); LOOP/TGT/BR-COUSIN
  (reads)
- CONSUMER: same
- PURPOSE: semantic hunt memory; the distance substrate for candidate
  retrieval; auditable compounding
- INPUT: `HuntRecord` (canonical text + metadata incl. trust tier); filters
  support `{kind, technique_id, tactic, trust_tier, hunt_id, time range}`
- OUTPUT: records with **raw cosine distance** + source hashes; RecallReceipt
  `{query, projection version, candidates, exclusions, selected context,
  dependency health}`
- STATE EFFECT: `hunt_memory` projection rows (LanceDB); outbox rows in SUB
- FAILURE SEMANTICS: embed service unreachable → recall unsatisfiable → hunt
  blocks (never silent lexical grading); reranker failure degrades
  presentation only; stale/hash-mismatched projection rows rejected on
  dereference; required outbox dead letter blocks hunt closure with
  operator-visible remediation
- PROVENANCE: trust tier + provenance class mandatory; SAME grading may not
  rest solely on low-authority classes; retrieved content is tagged and can
  never introduce tools/scope/policy
- IDEMPOTENCY/RETRY: `upsert` keyed by content-derived `record_id`;
  projection rebuild is idempotent replay from SUB
- OPERATOR BOUNDARY: `operator_assertion`/`external_intel` writes are
  operator-initiated; organ inspection CLI is read-only; the operator cannot
  waive mandatory recall for promotion-capable hunts

## I-5. Persistent substrate (SUB)

Module-internal API of `bully/store.py` (sole owner of `hunt_state.db`):

```python
load_context() -> HuntContext
record_decision(event: DecisionEvent) -> None           # append-only, hash-chained
record_cousin(record: CousinRecord) -> None
update_known_state(subject, kind, evidence, *, supersedes=None) -> None
append_cost(hunt_id, cost: CostRecord) -> None
baseline_get/put(detection_id, Baseline) -> ...
promotion_enqueue(item) / promotion_resolve(id, actor, rationale) -> ...
plateau_get/put(neighborhood) -> ...
outbox_append(items, tx) / outbox_lease() / outbox_complete() / outbox_dead_letter()
recall_receipt_put(receipt) / decision_impact_put(impact)
lease_acquire(hunt_id) / lease_renew() / lease_release()
```

- PRODUCER/CONSUMER: all bully components via these functions only
- PURPOSE: durable, recovery-safe compounding state
- INPUT/OUTPUT: typed records (DATA_MODEL doc)
- STATE EFFECT: the database; supersede sets `superseded_by` (never delete);
  decision log append-only; coordination fields compare-and-swap
- FAILURE SEMANTICS: SQLite errors propagate; a write failure is fatal to the
  iteration (state loss is worse than a stopped hunt); integrity check via
  `hunt doctor`; schema migration backup/preflight; code refuses a newer
  unsupported schema
- PROVENANCE: every table carries created_at/hunt_id/source refs and
  config/algorithm versions; trust tiers enforced
- IDEMPOTENCY/RETRY: natural unique keys per table; re-drive does not
  double-record; one active lease per hunt
- OPERATOR BOUNDARY: `promotion_resolve` requires `actor="operator:*"` —
  machine-enforced confirm-only

## I-6. Cousin engine (BR-COUSIN)

```python
build_signature(episode: Episode, telemetry_view) -> BehaviorSignature
candidate_set(signature, organ, attack_graph, family_index) -> CandidateSetReceipt
grade(signature, candidates, coverage: CoverageView) -> CousinAssessment
explain(assessment) -> Explanation
```

- PRODUCER: `bully/cousin_engine.py`; CONSUMER: LOOP, BIN, SCORE, HARV
- PURPOSE: two-axis grading — structural relationship + defense response
- INPUT: candidate signature; candidate-set receipt (union of semantic k-NN,
  ATT&CK neighborhood, event-graph motifs, scenario family); coverage view
  from SUB; discriminators from `spl_detections.technique_signature_full`
- OUTPUT: `CousinAssessment {relationship ∈ SAME|SIMILAR|NEW|DIFFERENT|
  ANOMALOUS_UNCLASSIFIED, D, decomposition {behavior, telemetry, semantic,
  attack, context}, vetoes evaluated, response ∈ COVERED|NEAR_MISS|MISSED|
  INDETERMINATE, nearest_knowns[], confidence/completeness, algorithm +
  threshold versions, explanation fields}`
- STATE EFFECT: none (pure); LOOP persists the assessment + outbox emission
- FAILURE SEMANTICS: degraded organ/candidate source → recorded degraded;
  classification proceeds only if policy-required sources/dimensions are
  complete, else ANOMALOUS/INDETERMINATE honestly; missing dimensions lower
  confidence, never renormalized
- PROVENANCE: assessment carries algorithm/threshold/config versions +
  candidate receipt ids; every normalized feature cites evidence ids
- IDEMPOTENCY/RETRY: pure function of immutable inputs + versions; algorithm
  change produces a new assessment, never an overwrite
- OPERATOR BOUNDARY: thresholds/weights are operator config with a
  calibration artifact; threshold-policy changes are separately approved and
  versioned, never retroactive

## I-7. Alert bin (BIN)

```python
process(candidate: Candidate) -> BinOutcome      # G-1→G0→G1a→G1b→G2→HEART→G3
promote(candidate_id, operator_actor, note) -> Promotion
kill(candidate_id, gate, rationale) -> None
```

- PRODUCER/CONSUMER: LOOP → BIN; HEART invoked inside; operator resolves the
  queue
- PURPOSE: suspect-until-proven promotion pipeline
- INPUT: `Candidate` (cousin assessment + episode refs + draft detection +
  mutation provenance + evidence manifest)
- OUTPUT: `BinOutcome {state, gate_results{}, council_record_ref,
  queue_id?}` per the state machine (DESIGN §13)
- STATE EFFECT: candidate row transitions (compare-and-swap on expected
  version); queue entries; decision events; a changed evidence manifest
  creates a new alert version and invalidates downstream passes
- FAILURE SEMANTICS: gate-infrastructure failure ≠ gate failure — G1a replay
  unavailable → BLOCKED (retryable), not DISPROVED; a gate that ran and
  failed → terminal outcome with gate + rationale
- PROVENANCE: gate results carry evidence refs + tool versions (recipe id,
  corpus version, triage run id, validator code version)
- IDEMPOTENCY/RETRY: gates are re-runnable; the state machine ignores
  duplicate transitions; retry attempts separately numbered
- OPERATOR BOUNDARY: only the operator moves AWAITING_OPERATOR →
  PROMOTED/DISPROVED; G-1 authorization precedes creation

### Gate internals (normative)

- **G-1:** approved scope, mutation class, tool allowlist, budgets — recorded
  pre-creation; fail-closed.
- **G0:** ≥1 observed-origin evidence ref
  (`telemetry.py:26-37` OBSERVED_EVIDENCE_ORIGINS); complete hashed manifest;
  healthy telemetry. Synthetic/counterfactual never passes.
- **G1a static:** candidate SPL executes against the replayed capture and
  fires within window on the right target (capture_store + backend execution;
  mirrors `episode.py:189-213` `derive_detection_status` semantics).
- **G1b dynamic:** re-execution reproduces the behavior chain + expected
  artifact contract — `capture_recipes` where a recipe exists, else a
  directed Red re-run within MUT budget; declared 2-of-3 policy for
  nondeterministic targets. Static alone never promotes.
- **G2:** matched benign/telemetry/environment controls +
  benign-corpus zero-fire (`benign_corpus_bench`) + verdict-contract
  counter-evidence (`blue_orchestrate.py:91-103`). BQ semantics preserved.
- **G3:** §I-7a below.

### I-7a. SOC visibility (G3)

- PRODUCER: `bully/soc.py`; CONSUMER: BIN
- PURPOSE: prove the *Bully finding* reaches the real analyst path
- INPUT: redacted finding envelope, destination/config version, correlation
  marker, SLO, queue-load profile
- OUTPUT: `SOCDeliveryReceipt` {producer ack, consumer-side triage report
  (via the existing `siem/blue_triage.py` lane under the queue-load corpus),
  priority, latency, content-hash match, load profile}
- STATE EFFECT: external delivery + durable receipt
- FAILURE SEMANTICS: producer ack without a consumer query is insufficient;
  timeout/content mismatch → G3 fail/block. This validates the Bully
  finding's delivery, not the missed detector's firing.
- PROVENANCE: destination, adapter, query, load, content hashes; secrets
  excluded
- IDEMPOTENCY/RETRY: stable correlation key prevents duplicate notables;
  redelivery is a new attempt
- OPERATOR BOUNDARY: destination is configured/approved; this receipt does
  not authorize detector deployment

## I-8. Council (HEART)

```python
review(candidate: Candidate) -> CouncilRecord
```

- PRODUCER: `bully/adversary.py`; CONSUMER: BIN
- PURPOSE: adversarial falsification with a durable objection gate
- INPUT: candidate + frozen evidence pack (episode refs, gate results so far,
  decomposition, signature); roster snapshot
- OUTPUT: `CouncilRecord {packet_id, opinions: [full CouncilOpinion incl.
  strongest_objection/missing_evidence/conditions_to_change], objections:
  [durable {category, material, citations, status}], rebuttals: [...],
  unresolved: bool, participation, roster snapshot}` — reusing platform
  `council.py::parse_opinion:147-187` and participation accounting
  `:190-237`; `aggregate_opinions` is not used for the decision
- STATE EFFECT: none inside HEART; BIN persists the record and applies the
  block
- FAILURE SEMANTICS: seat failure → invalid opinion (non-participant);
  sub-floor participation → `review_valid=False` → BIN escalates to operator
  (never auto-pass); malformed/missing-citation output → abstention recorded
- PROVENANCE: seat models + families + prompt/inference versions + evidence
  packet hash recorded
- IDEMPOTENCY/RETRY: re-review produces a new record superseding the prior;
  one opinion per seat/packet/attempt; changed evidence = new packet
- OPERATOR BOUNDARY: roster + floors + materiality version are config; the
  objection waiver is a separate authenticated command with a durable reason,
  visible in the handoff

**Objection gate (code):** materiality validated against enumerated
categories (evidence contradiction; covering detection id; benign
counter-evidence per the verdict contract; scope/safety; reproducibility;
telemetry health; relationship classification; defense response; analyst
visibility; regression risk). Any material objection standing after the
rebuttal round → `unresolved=True` → BIN blocks (DISPROVED or
returned-for-evidence per operator-configured policy). Closure paths:
rebuttal with cited evidence + falsification re-pass on the same evidence
version; withdrawal by the originating (or equally independent) seat;
authorized operator waiver. Vote counts are telemetry only.

## I-9. Drift engine (BR-DRIFT)

```python
update(episode: Episode, detections: list[DetectionOutcome]) -> list[DriftFlag]
```

- PRODUCER: `bully/drift_engine.py`; CONSUMER: LOOP (flags → BR-COUSIN
  routing / ops leads), SUB (baselines)
- PURPOSE: temporal-cousin detection + baseline maintenance
- INPUT: per-detection outcomes this episode (fired?, latency, row shape,
  clause satisfaction, sourcetype completeness); matched rolling baselines
  from SUB; model-canary evidence
- OUTPUT: `DriftFlag {detection_id, class ∈ {TELEMETRY_DEGRADATION,
  ENVIRONMENT_CHANGE, ATTACKER_EVOLUTION, DETECTION_DEGRADATION,
  UNCLASSIFIED}, score, detail}` — statistics pattern from
  `drift_gate.py:35-51` (window, noise floor, min-baseline,
  INSUFFICIENT-BASELINE)
- STATE EFFECT: baseline rows updated in SUB; version changes supersede
  baselines with a warm-up
- FAILURE SEMANTICS: insufficient baseline → INSUFFICIENT-BASELINE honest
  flag; sensor failure takes precedence over attack/detection labels
- PROVENANCE: baseline window + input episode ids + canary reference
- IDEMPOTENCY/RETRY: baseline update keyed by (detection_id, episode_id); one
  sample contributes once
- OPERATOR BOUNDARY: windows/floors/critical-bounds are config; cause
  attribution itself is deterministic

## I-10. Scorer (SCORE)

```python
update(hunt_id) -> ScoreboardRow
report(scope: hunt|series) -> Scoreboard
```

- PRODUCER: `bully/scoreboard.py`; CONSUMER: CLI readouts, PLT, TRAIN gate
- PURPOSE: discovery-first scoring with preserved catch/trust semantics
- INPUT: SUB grading/gate/promotion records
- OUTPUT: per-hunt + cumulative: notify recall (ANOMALOUS is an Axis-1 catch,
  BN preserved), trust ordinal (CONFIRMED_CORRECT > HONEST_ANOMALY >
  CONFIRMED_WRONG, preserved), **discovery-value axis** (distance-weighted;
  far-NEW ≥ known-bad), benign false-flag typing (BQ preserved)
- STATE EFFECT: none (read-only compute; rows cached in SUB)
- FAILURE SEMANTICS: data absence reported, not faked
- PROVENANCE: scope + window recorded
- IDEMPOTENCY/RETRY: pure
- OPERATOR BOUNDARY: none

## I-11. Target selector (TGT)

```python
select(context: HuntContext, recall: RecallReceipt, ledger: CostView) -> TargetDecision
```

- PRODUCER: `bully/targeting.py`; CONSUMER: LOOP
- INPUT: coverage cells + known-state (SUB), recall receipt (ORG), cost
  ledger, resource/lease status
- OUTPUT: `TargetDecision` — hard-eligibility results, ordered targets, full
  factor breakdown (raw features, posterior, value, cost, priority), declined
  cells with reasons, recall influence, tie-break
- STATE EFFECT: none internally; LOOP persists the decision + reserves the
  target lease
- FAILURE SEMANTICS: empty eligible set → honest "no eligible target" stop;
  missing material cost → unrankable (blocked), never zero-cost
- PROVENANCE: factor snapshot + algorithm/config versions recorded
- IDEMPOTENCY/RETRY: deterministic for a snapshot; resource change creates a
  new decision version
- OPERATOR BOUNDARY: formula weights via config; override requires reason and
  may not bypass authorization/readiness/telemetry hard gates

## I-12. Plateau (PLT)

```python
evaluate(neighborhood, window: int) -> PlateauDecision  # continue|rotate|stop
```

- PRODUCER: `bully/plateau.py`; CONSUMER: LOOP
- INPUT: SUB valid-trial series (≥8 trials, ≥2 mutation dims), promotions,
  unique response-state gain, posterior yield bound, saturation signal,
  reset-trigger versions
- OUTPUT: decision + rationale + plateau record when stopping; reset events
  on version changes
- STATE EFFECT: plateau record (SUB + ORG via LOOP)
- FAILURE SEMANTICS: insufficient trials → not-plateaued (keep hunting) with
  a note; blocked/infrastructure trials excluded from denominators
- IDEMPOTENCY/RETRY: pure
- OPERATOR BOUNDARY: bounds/patience/saturation via config; override is a
  recorded policy exception with expiry; plateau is neighborhood-local

## I-13. Cost metering (SCORE/PLT support)

- PRODUCER: runtime metering (`bully/costing.py`); CONSUMER: TGT, PLT, SCORE
- INPUT: typed resource observations (lab minutes, inference calls/tokens/
  latency, analyst minutes, replay work, storage, training allocation) +
  pricing profile version
- OUTPUT: `CostRecord` per hunt/iteration; computed comparable units
- STATE EFFECT: append cost rows; sufficient statistics derive
- FAILURE SEMANTICS: material missing measurement → null + quality flag →
  blocks ROI claims; never zero-fills
- PROVENANCE: meter/source/profile versions
- IDEMPOTENCY/RETRY: one cost component per source key
- OPERATOR BOUNDARY: pricing profile is config; override cannot fabricate a
  valid trial

## I-14. Handoff (HND)

```python
build_package(candidate_id) -> HandoffPackage
```

- PRODUCER: `bully/handoff.py`; CONSUMER: operator (detection engineering),
  via BIN promotion
- OUTPUT contents: DESIGN §23 (11 parts). SPL/Sigma generalization drafted by
  a model from the cousin's discriminators and **validated in code**
  (`validate_spl_syntax`, extracted from growth_loop, + dry execution against
  the replayed capture); the three detection-proof legs execute for real
  (fires-on-attack via recipe replay; quiet-on-benign via benign corpus;
  no-regression via BQ/AZ lanes); regression recipe emitted in
  `capture_recipes` format; FP analysis attaches G2 results
- STATE EFFECT: package stored (SUB + files under hunt dir); queue entry
  resolved; proposal lifecycle (draft → submitted → accepted/revise/rejected/
  expired → deployed → replay-validated/failed → retired)
- FAILURE SEMANTICS: validation failure → package returned for rework
  (candidate stays PENDING), never shipped; a proof-leg failure blocks the
  package
- PROVENANCE: full lineage (hunt, episode, gates, council, operator,
  deployment, replay)
- IDEMPOTENCY/RETRY: rebuild produces a superseding package version;
  deployment ids deduplicate
- OPERATOR BOUNDARY: the spl_detections.yaml change is an operator commit
  through normal validation (BQ/AZ green pre-push); KNOWN_COVERED requires a
  deployment receipt + successful post-deploy replay

## I-15. Harvest (HARV)

```python
append_pairs(hunt_record) -> int            # per-iteration extraction
build_dataset(role, window) -> DatasetRef   # immutable version + manifest + splits
```

- PRODUCER: `bully/harvest.py`; CONSUMER: TRAIN
- INPUT: SUB records (verdicts+rationales, council objection/rebuttal
  exchanges, cousin judgments with decompositions, kill rationales)
- OUTPUT: role-tagged examples `{role, input, output, provenance {hunt_id,
  episode_id, models, distances, outcome, trust_tier}, group tags
  {family, campaign, time}, leakage/oracle flags, split}`; dataset manifest
  `{dataset_version, counts, role coverage, content_hash, source_window,
  split manifest, dedup/leakage report, config versions}`
- STATE EFFECT: corpus files under hunt dir; `dataset_versions` rows in SUB;
  examples quarantined until checks pass
- FAILURE SEMANTICS: below-size-floor → documented non-build (honest);
  missing provenance / suspect trust / leakage / duplicate → quarantine,
  never silent inclusion
- PROVENANCE: per-example + per-dataset as above; label-blind discipline:
  production modules never import recall_attribution (BM import-scan test);
  eval-side honest-miss labels only via that oracle
- IDEMPOTENCY/RETRY: same window + config → same content hash; corrected
  label supersedes and forces a new dataset version
- OPERATOR BOUNDARY: dataset build is operator-initiated; dataset release is
  a separate operator approval from model promotion

## I-16. Playbook memory (PLAY)

```python
draft_update(scenario_class, hunt_record) -> PlaybookDraft
activate(draft_id, operator_actor) -> None
for_hunt(scenario_class) -> Playbook | None
```

- PRODUCER: `bully/playbooks.py`; CONSUMER: LOOP (injection into the
  investigation context), TRAIN (playbook arm)
- INPUT: successful/structured hunt trajectories (SUB), field_journal
  reusable patterns (read-only source)
- OUTPUT: versioned learned instruction sets per scenario class; lifecycle
  `DRAFT → REPLAY_VALIDATED → CANARY → AWAITING_OPERATOR → ACTIVE → RETIRED`
- STATE EFFECT: SUB playbook records; activation supersedes the prior version
  (atomic pointer); auto-revert on canary failure with recorded cause
- FAILURE SEMANTICS: no playbook for a class → hunt proceeds unshaped
  (absence is neutral, never fabricated); canary regression → reject/rollback
- PROVENANCE: source hunts listed on every draft; replay/canary/approver refs
- IDEMPOTENCY/RETRY: drafts keyed by (class, source window); activation CAS
  on the active pointer
- OPERATOR BOUNDARY: activation is confirm-only

## I-17. Training (TRAIN)

```python
run(role) -> TrainOutcome
```

- PRODUCER: `bully/training.py`; CONSUMER: operator
- STEPS: dataset (HARV) → size gate → operator dataset release → exclusive
  lock + preflight → LoRA train (host subprocess, `mlx_lm.lora` — present via
  `mlx-lm>=0.31`, `pyproject.toml:78`) → fuse (`mlx_lm.fuse`) → GGUF convert
  (llama.cpp — installed + verified by the TRAIN phase) → `ollama create`
  (via the `cli/models.py:218-259` import-gguf mechanism) → acceptance gate →
  verdict file → role-alias canary → atomic promotion
- INPUT: dataset version, base model alias (config), hyperparams (config),
  resource lock, frozen five-arm suite, acceptance policy version
- OUTPUT: `{model_tag, dataset_version, bench_report_ref, canary_report_ref,
  pending_verdict_entry}`; artifacts under hunt dir, content-addressed
- STATE EFFECT: `trained_models` rows; candidate artifacts; NO serving change
  without operator confirm; active alias unchanged on any failure
- FAILURE SEMANTICS: toolchain missing → explicit setup error with install
  instructions (owned build step); acceptance fail → recorded, candidate not
  queued; corpus below floor → honest non-build; interruption → checkpoint,
  alias untouched; canary regression → atomic rollback
- PROVENANCE: dataset hash, base digest, seed, config, toolchain versions,
  bench/canary reports, artifact hashes
- IDEMPOTENCY/RETRY: same inputs → same model tag (content-derived); reruns
  supersede; job key resumes a compatible checkpoint
- OPERATOR BOUNDARY: serve only via operator verdict (existing
  PENDING_MODEL_VERDICTS flow); dataset release, model promotion, and
  rollback override are separate approvals

## I-18. Bench acceptance (repositioned harness)

- EXISTING producers: `execute_local_sec_bench.sh` → `bench_supervisor.py` →
  bench CLI; `candidate_eval.py` delta-vs-incumbent; `intake.py` floors
  (TPS_FLOOR=20); `toolcall_reliability.gate`; `drift_cli.py` model-canary
- NEW consumer: TRAIN gate, plus the cousin-judgment suite (a labeled
  cousin-grading eval set built from SUB history once hunts exist; label-
  blind at grading time; bootstrapped from fixtures until then)
- CONTRACT: PASS requires (a) intake floors, (b) no regression vs incumbent
  on the general security bench, (c) frozen five-arm cousin-suite win
  (+5 macro-F1, 95% CI > 0 over base+retrieval+playbook), (d) operator
  confirm
- STATE EFFECT: verdict records; no auto-routing edits (existing
  execute_pending_verdicts discipline)
- OPERATOR BOUNDARY: acceptance thresholds frozen before the final held-out
  evaluation; weakening requires a new approved policy version

## I-19. Roster (ROSTER)

```python
recompute(window) -> RosterUpdate
```

- PRODUCER: `bully/roster.py`; CONSUMER: HEART config activation
  (operator-approved)
- INPUT: council records from SUB (objection precision/recall, cousin-call
  correctness, citation validity, abstention quality, latency/cost,
  independence family) — only outcomes unavailable to the reviewer at
  decision time
- OUTPUT: eligibility/probation/additional-review determinations + bounded
  advisory ordering weights [0.5, 2.0] + full rationale; activation is a
  queue item
- CONSTRAINTS (code): the objection gate never consults weights or
  reliability; family/correlation-group diversity enforced at roster load;
  abstentions count against participation
- STATE EFFECT: `roster_records` rows (supersede); decision events
- IDEMPOTENCY/RETRY: same window → same update (content key)
- OPERATOR BOUNDARY: activation confirm-only

## I-20. Mutation budget (cross-cutting)

- ENFORCER: MUT in code; checked against `hunt.yaml::mutation` per hunt
- INPUT: planned variants; OUTPUT: approved plan ≤ budget or explicit
  truncation with recorded rationale
- FAILURE: budget exceeded → truncation, never silent overflow
- OPERATOR BOUNDARY: budget values are operator dials

## I-21. Notifications

- REUSE: `portal.platform.inference.notifications` dispatcher exactly as
  `loop.py:232-298` does (fire-and-forget, non-fatal, `LOOP_NOTIFY_ENABLED`
  pattern) for: promotion-queue arrivals, honest-BLOCKED, plateau stops,
  council escalations, training-completion/blocker events. No new channel
  code.

## I-22. Migration shadow interfaces

- **Episode dual-write:** the existing purple caller emits a shadow
  observation to the bully Episode adapter (feature-flagged;
  off/shadow/authoritative); legacy results byte-stable with the flag off.
- **Dual-run classification:** legacy unknown-defense and BR-COUSIN both
  grade during shadow; disagreements persisted and adjudicated as migration
  evidence; no new result silently reuses the old `NONE → benign` fallback.
- **Backfill:** idempotent manifest per imported record (source path/id,
  content hash, importer version, inferred fields, omissions); unverifiable
  records import as `IMPORTED_UNVERIFIED`; rollback disables consumption,
  keeps records.

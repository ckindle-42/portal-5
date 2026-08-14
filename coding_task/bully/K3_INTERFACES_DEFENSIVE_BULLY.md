# INTERFACES — Defensive Bully

Contracts the implementing agent builds to. Format per interface: PRODUCER /
CONSUMER / PURPOSE / INPUT / OUTPUT / STATE EFFECT / ERROR-FAILURE SEMANTICS /
PROVENANCE / IDEMPOTENCY-RETRY / OPERATOR BOUNDARY. Types reference
`DATA_MODEL_DEFENSIVE_BULLY.md`. Existing-code anchors cited at HEAD
`47d3e884` (re-verify at build HEAD).

---

## I-1. Red direction (bully → Red)

**Interface:** `MutationSpec` + scenario overlay, consumed by the existing Red
scenario machinery (`exec_chain._prepare_scenario` / `BenchConfig.set_scenario`,
`exec_chain.py:3144-3149`; `_config.py:49-75`).

- PRODUCER: MUT (`mutation_director.py`)
- CONSUMER: Red execution (`exec_chain._run_chain_test`, unchanged)
- PURPOSE: tell Red *which* cousin to manufacture, never *how* to execute
- INPUT: base scenario key; variant params `{timing, tool_args, artifacts,
  sub_technique_adjacency[], evasion_directive}`; target host; budget class
- OUTPUT: a rendered scenario overlay (`red_prompt`, `red_order`, ground-truth
  expectation metadata) handed to the unchanged executor
- STATE EFFECT: none on bully state (the resulting Episode is the effect)
- ERROR/FAILURE: overlay fails validation (unknown base scenario, scope
  violation via `perception.assert_in_lab`, budget exceeded) → no Red call;
  decision event recorded; iteration honest-BLOCKED
- PROVENANCE: spec carries `mutation_id, base_scenario, parent_known_record_id`
- IDEMPOTENCY: re-rendering the same spec yields the same overlay (pure
  function of spec + base scenario)
- OPERATOR BOUNDARY: mutation budget values are operator config
  (`hunt.yaml::mutation`)

## I-2. Episode (Red → bully) — EXISTING, UNCHANGED

- PRODUCER: purple/bench flow (`blue.py::run_purple_tests:1941`,
  `_score_purple:1519`; `episode.py`)
- CONSUMER: LOOP (`hunt_loop.py`)
- PURPOSE: the truth-plane input contract — reason-coded axes + evidence refs
- INPUT: red result, telemetry status, detection correlations
- OUTPUT: `Episode` dataclass (`episode.py:45-74`) + `verdict()` via
  `derive_verdict` (`:146-183`); persisted per existing surfaces (result JSON,
  `save_evidence`, provenance ledger)
- STATE EFFECT: bully records it into SUB as the iteration's anchor
- ERROR/FAILURE: telemetry failures arrive as reason codes → verdict
  INDETERMINATE (existing); LOOP treats INDETERMINATE as blocked, never as a
  miss/pass
- PROVENANCE: `episode_id` is the join key across SUB/ORG/Splunk
- IDEMPOTENCY: re-consuming the same episode_id updates the same SUB rows
- OPERATOR BOUNDARY: none (deterministic)

**Reconciliation note:** `agentic_blue_eval.py:82-91` defines a second
`Episode` (replay DTO: scenario/techniques/telemetry). The build renames its
local usages in documentation/comments to "capture replay DTO" — the
truth-plane `episode.py::Episode` is the only Episode in the bully. No
behavioral change to the replay benches.

## I-3. Hunt loop (operator/CLI → system; system internal driver)

- PRODUCER/CONSUMER: `commands/hunt_modes.py` ↔ `hunt_loop.run_hunt`
- PURPOSE: run/resume/status a hunt
- INPUT: `{neighborhood: str|"auto", budget_class, dry_run, resume_id?}`,
  config from `config/security/hunt.yaml` + `heart.yaml`
- OUTPUT: hunt report `{hunt_id, iterations, candidates graded, promotions to
  queue, plateau/stop reason, cost summary}`; exit code per `59839264`
  semantics (nonzero on honest-BLOCKED)
- STATE EFFECT: full SUB/ORG writes per iteration (§7 of DESIGN)
- ERROR/FAILURE: any gate/infra failure → recorded; run exits honestly
- PROVENANCE: `hunt_id` on every emitted record
- IDEMPOTENCY: `--resume <hunt_id>` continues from SUB state; natural keys
  prevent double-record
- OPERATOR BOUNDARY: operator starts/stops hunts; the loop never self-schedules
  (daemon is a future extension)

## I-4. Knowledge organ (ORG)

Module-internal API of `hunt_organ.py` (NOT an MCP tool):

```python
upsert(record: HuntRecord) -> None
knn(query: str | HuntRecord, k: int, filters: dict) -> list[tuple[HuntRecord, float]]
recall(context: HuntContext, k: int) -> RecallResult      # used by LOOP pre-hunt
index_emissions(iteration: IterationEmissions) -> None    # universal indexing sink
stats() -> OrganStats
```

- PRODUCER: all bully components (writes); LOOP/TGT/BR-COUSIN (reads)
- CONSUMER: same
- PURPOSE: semantic hunt memory; distance substrate for cousin grading
- INPUT: `HuntRecord` (canonical text + metadata incl. provenance_class);
  filters support `{kind, technique_id, tactic, provenance_class, hunt_id,
  time range}`
- OUTPUT: records with **raw cosine distance**; `RecallResult` includes
  hit list + utilization token recorded on the hunt
- STATE EFFECT: `hunt_memory` table rows (LanceDB); no other state
- ERROR/FAILURE: embed service unreachable → raise `OrganUnavailable`; caller
  (LOOP) converts to honest-BLOCKED (never silent lexical grading). Reranker
  failure degrades presentation only
- PROVENANCE: `provenance_class ∈ {hunt_emission, operator_assertion,
  external_intel}` mandatory; SAME grading may not rest solely on
  non-`hunt_emission` records
- IDEMPOTENCY: `upsert` keyed by `record_id` (content-derived); re-upsert
  overwrites in place
- OPERATOR BOUNDARY: `external_intel`/`operator_assertion` writes are
  operator-initiated; organ inspection CLI is read-only

## I-5. Persistent substrate (SUB)

Module-internal API of `hunt_state.py` (sole owner of `hunt_state.db`):

```python
load_context() -> HuntContext
record_decision(event: DecisionEvent) -> None
record_cousin(record: CousinRecord) -> None
update_known_state(subject: CellRef, kind: KnownKind, evidence: list[str],
                   *, supersedes: str|None) -> None
append_cost(hunt_id, cost: CostRecord) -> None
baseline_get/detection baseline_put(detection_id, Baseline) -> ...
promotion_enqueue(item) / promotion_resolve(id, actor, rationale) -> ...
plateau_get/put(neighborhood) -> ...
```

- PRODUCER/CONSUMER: all bully components via these functions only
- PURPOSE: durable compounding state
- INPUT/OUTPUT: typed records (DATA_MODEL doc)
- STATE EFFECT: the database; supersede sets `superseded_by` (never delete)
- ERROR/FAILURE: SQLite errors propagate; callers treat write failure as fatal
  to the iteration (state loss is worse than a stopped hunt); integrity check
  command provided (`hunt doctor`)
- PROVENANCE: every table has `created_at`, `hunt_id`/source refs; decision
  log is append-only
- IDEMPOTENCY: natural unique keys per table; `INSERT OR REPLACE`-class
  semantics where re-drive is legal
- OPERATOR BOUNDARY: `promotion_resolve` requires `actor="operator:*"` —
  machine-enforced confirm-only

## I-6. Cousin engine (BR-COUSIN)

```python
grade(candidate: HuntRecord, neighbors: list[tuple[HuntRecord, float]],
      coverage: CoverageView) -> CousinVerdict
explain(verdict: CousinVerdict) -> Explanation
```

- PRODUCER: `cousin_engine.py`; CONSUMER: LOOP, BIN, SCORE, HARV
- PURPOSE: SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS_UNCLASSIFIED grading
- INPUT: candidate record; k-NN neighbors with distances; coverage view
  (which knowns are covered — from SUB); discriminators from
  `spl_detections.technique_signature_full` (`:102-116`)
- OUTPUT: `CousinVerdict {grade, composite, decomposition {d1..d5},
  nearest_knowns[], explanation fields}` — thresholds from config
- STATE EFFECT: none (pure); LOOP persists the verdict
- ERROR/FAILURE: missing embeddings/degraded organ → raise; LOOP blocks
- PROVENANCE: verdict carries config-threshold version + neighbor record ids
- IDEMPOTENCY: pure function of inputs + config version
- OPERATOR BOUNDARY: thresholds/weights are operator config

## I-7. Alert bin (BIN)

```python
process(candidate: Candidate) -> BinOutcome   # drives G0→G1a→G1b→G2→HEART→G3
promote(candidate_id, operator_actor, note) -> Promotion
kill(candidate_id, gate, rationale) -> None
```

- PRODUCER/CONSUMER: LOOP → BIN; HEART invoked inside; operator resolves queue
- PURPOSE: suspect-until-proven promotion pipeline
- INPUT: `Candidate` (cousin verdict + episode refs + draft detection +
  mutation provenance)
- OUTPUT: `BinOutcome {status, gate_results{}, council_record_ref,
  queue_id?}`; gate details per DATA_MODEL
- STATE EFFECT: candidate row transitions; queue entries; decision events
- ERROR/FAILURE: gate infrastructure failure ≠ gate failure — G1a replay
  unavailable → BLOCKED (retryable), not KILLED; gate ran and failed → KILLED
  with rationale
- PROVENANCE: gate results carry evidence refs + tool versions
  (recipe id, corpus version, triage run id)
- IDEMPOTENCY: gates are re-runnable; state machine ignores duplicate
  transitions
- OPERATOR BOUNDARY: only the operator moves PENDING_OPERATOR → PROMOTED/KILLED

### Gate internals (normative)

- **G0:** ≥1 evidence ref with origin in `OBSERVED_EVIDENCE_ORIGINS`
  (`telemetry.py:25-37`).
- **G1a static:** execute candidate SPL against the replayed capture
  (`capture_store` load + `SplunkBackend.query`-class execution); pass =
  fire within window, correct target (mirror `derive_detection_status`,
  `episode.py:189-213`).
- **G1b dynamic:** deterministic re-execution via `capture_recipes` where a
  recipe exists, else directed Red re-run through MUT; pass = expected
  artifact contract observed in fresh telemetry.
- **G2:** (a) counter-evidence evaluation per the verdict-contract discipline
  (`blue_orchestrate.py:91-103`); (b) candidate discriminators executed over
  the benign corpus (`benign_corpus_bench`); pass = zero fires.
- **G3:** ship notable (HEC, observed origin) → run `siem/blue_triage.py`
  lane under the queue-load corpus → pass = report priority ≤ threshold
  within SLA (config `triage:`).

## I-8. Council (HEART)

```python
review(candidate: Candidate) -> CouncilRecord
```

- PRODUCER: `heart_council.py`; CONSUMER: BIN
- PURPOSE: adversarial falsification with an objection gate
- INPUT: candidate + evidence pack (episode refs, gate results so far,
  decomposition)
- OUTPUT: `CouncilRecord {opinions: [full platform CouncilOpinion incl.
  strongest_objection/missing_evidence/conditions_to_change], objections:
  [classified {material, kind, citations}], rebuttals: [...], unresolved:
  bool, participation, roster}` — reuse `council.py::parse_opinion`
  (`:147-187`) and participation accounting (`:190-237`)
- STATE EFFECT: none inside HEART; BIN persists the record and applies the
  block
- ERROR/FAILURE: seat failure → invalid opinion (non-participant); sub-floor
  participation → `review_valid=False` → BIN escalates to operator (never
  auto-pass)
- PROVENANCE: seat models + families + config version recorded
- IDEMPOTENCY: re-review produces a new record superseding the prior
- OPERATOR BOUNDARY: roster + floors + materiality criteria version are config

**Objection gate (code):** materiality = cites a specific evidence
contradiction OR an already-covering detection id OR verdict-contract benign
counter-evidence. Any material objection standing after the rebuttal round →
`unresolved=True` → BIN blocks (KILLED or returned-for-evidence per
operator-configured policy). Vote counts are recorded for telemetry only.

## I-9. Drift engine (BR-DRIFT)

```python
update(episode: Episode, detections: list[DetectionOutcome]) -> list[DriftFlag]
```

- PRODUCER: `drift_engine.py`; CONSUMER: LOOP (flags → BR-COUSIN routing /
  ops leads), SUB (baselines)
- PURPOSE: temporal-cousin detection + baseline maintenance
- INPUT: per-detection outcomes this episode (fired?, latency, row shape,
  clause satisfaction, sourcetype completeness); rolling baselines from SUB
- OUTPUT: `DriftFlag {detection_id, class ∈ {TELEMETRY_FAILURE,
  ENVIRONMENTAL_CHANGE, DETECTION_DEGRADATION, ATTACKER_EVOLUTION}, score,
  detail}` — statistics pattern from `drift_gate.py` (window, noise floor,
  min-baseline runs)
- STATE EFFECT: baseline rows updated in SUB
- ERROR/FAILURE: insufficient baseline → `INSUFFICIENT-BASELINE` honest flag
  (existing drift_gate semantics)
- PROVENANCE: baseline window + input episode ids
- IDEMPOTENCY: baseline update keyed by (detection_id, episode_id)
- OPERATOR BOUNDARY: window/floors are config

## I-10. Scorer (SCORE)

```python
update(hunt_id) -> ScoreboardRow
report(scope: hunt|series) -> Scoreboard
```

- PRODUCER: `hunt_scoreboard.py`; CONSUMER: CLI readouts, PLT, TRAIN gate
- PURPOSE: distance-graded discovery scoring
- INPUT: SUB grading/gate/promotion records
- OUTPUT: per-hunt + cumulative: notify recall (ANOMALOUS==catch preserved,
  BN semantics), trust ranks, distance-weighted discovery score, false-flag
  typing on benign cells (BQ semantics)
- STATE EFFECT: none (read-only compute; rows cached in SUB)
- ERROR/FAILURE: n/a beyond data absence (reported, not faked)
- PROVENANCE: scope + window recorded
- IDEMPOTENCY: pure
- OPERATOR BOUNDARY: none

## I-11. Target selector (TGT)

```python
rank(context: HuntContext, recall: RecallResult, ledger: CostView) -> RankedTargets
```

- PRODUCER: `target_selector.py`; CONSUMER: LOOP
- INPUT: coverage cells + known-state (SUB), recall (ORG), cost ledger
- OUTPUT: ordered targets + full factor breakdown (value, penalties, cost,
  score) per candidate — including declined cells with reasons
- STATE EFFECT: none; decision logged by LOOP
- ERROR/FAILURE: empty candidate set → honest "no eligible target" stop
- PROVENANCE: factor snapshot recorded on the hunt
- IDEMPOTENCY: pure
- OPERATOR BOUNDARY: formula weights via config

## I-12. Plateau (PLT)

```python
evaluate(neighborhood, window: int) -> PlateauDecision  # continue|rotate|stop
```

- PRODUCER: `plateau.py`; CONSUMER: LOOP
- INPUT: SUB discovery-rate series + saturation; config floors/patience
- OUTPUT: decision + rationale + plateau record when stopping
- STATE EFFECT: plateau record (SUB+ORG via LOOP)
- IDEMPOTENCY: pure
- OPERATOR BOUNDARY: floors/patience/saturation via config

## I-13. Handoff (HND)

```python
build_package(candidate_id) -> HandoffPackage
```

- PRODUCER: `handoff.py`; CONSUMER: operator (detection engineering), via BIN
  promotion
- OUTPUT contents: DESIGN §23 (10 parts). SPL/Sigma generalization is drafted
  by a model from the cousin's discriminators and **validated in code**
  (`growth_loop`-extracted `validate_spl_syntax` + dry execution against the
  replayed capture); FP analysis attaches G2 results; regression recipe is
  emitted in `capture_recipes` format
- STATE EFFECT: package stored (SUB + file under hunt dir); queue entry
  resolved
- ERROR/FAILURE: validation failure → package returned for rework (candidate
  stays PENDING), never shipped
- PROVENANCE: full lineage (hunt, episode, gates, council, operator)
- IDEMPOTENCY: rebuild produces a superseding package version
- OPERATOR BOUNDARY: the spl_detections.yaml change is an operator commit
  through normal validation (BQ/AZ green pre-push)

## I-14. Harvest (HARV)

```python
append_pairs(hunt_record) -> int           # per-iteration extraction
build_dataset(role, window) -> DatasetRef  # versioned JSONL + manifest + splits
```

- PRODUCER: `harvest.py`; CONSUMER: TRAIN
- INPUT: SUB records (verdicts+rationales, council objection/rebuttal
  exchanges, cousin judgments with decompositions, kill rationales)
- OUTPUT: role-tagged examples `{role, input, output, provenance
  {hunt_id, episode_id, models, distances, outcome}, split}`; dataset
  manifest `{dataset_version, counts, role coverage, content_hash,
  source_window, config versions}`
- STATE EFFECT: corpus files under hunt dir; `dataset_versions` rows in SUB
- ERROR/FAILURE: below-size-floor → documented non-build (honest), not an
  error
- PROVENANCE: per-example + per-dataset, as above; label-blind discipline:
  examples derive from production outcomes; eval-side honest-miss labels only
  via `recall_attribution` (BM boundary: production code never imports it —
  `spl_detections.py` boundary check stays green)
- IDEMPOTENCY: `build_dataset` with same window+config → same content hash
- OPERATOR BOUNDARY: dataset build is operator-initiated

## I-15. Playbook memory (PLAY)

```python
draft_update(scenario_class, hunt_record) -> PlaybookDraft
activate(draft_id, operator_actor) -> None
for_hunt(scenario_class) -> Playbook | None
```

- PRODUCER: `playbook_memory.py`; CONSUMER: LOOP (injection into investigation
  context), TRAIN (playbook arm)
- INPUT: successful/structured hunt trajectories (SUB), field_journal reusable
  patterns (read-only)
- OUTPUT: versioned learned instruction sets per scenario class
- STATE EFFECT: SUB playbook records; activation supersedes prior version
- ERROR/FAILURE: no playbook for a class → hunt proceeds unshaped (absence is
  neutral, never fabricated)
- PROVENANCE: source hunts listed on every draft
- IDEMPOTENCY: drafts keyed by (class, source window)
- OPERATOR BOUNDARY: activation is confirm-only

## I-16. Training (TRAIN)

```python
run(role) -> TrainOutcome
```

- PRODUCER: `train_flywheel.py`; CONSUMER: operator
- STEPS: dataset (HARV) → size gate → LoRA train (host subprocess, `mlx_lm`)
  → fuse → GGUF convert → `ollama create` (via the `models.py import-gguf`
  mechanism, `cli/models.py:217-259`) → bench gate → verdict file
- INPUT: dataset version, base model id (config), hyperparams (config)
- OUTPUT: `{model_tag, dataset_version, bench_report_ref,
  pending_verdict_entry}`; artifacts under hunt dir
- STATE EFFECT: `trained_models` rows; candidate artifacts; NO serving change
  without operator confirm
- ERROR/FAILURE: toolchain missing → explicit setup error with install
  instructions (owned build step); bench gate fail → recorded, candidate not
  queued; corpus below floor → honest non-build
- PROVENANCE: dataset hash, base model, seed, config, bench report
- IDEMPOTENCY: same inputs → same model tag (content-derived); reruns
  supersede
- OPERATOR BOUNDARY: serve only via operator verdict (existing
  PENDING_MODEL_VERDICTS flow)

## I-17. Bench acceptance (repositioned harness)

- EXISTING producers: `execute_local_sec_bench.sh` → `bench_supervisor.py` →
  bench CLI; `candidate_eval.py` 6-scenario delta; `intake.py` floors;
  `toolcall_reliability.gate`
- NEW consumer: TRAIN gate, plus the cousin-judgment bench (a labeled
  cousin-grading eval set built from SUB history, label-blind at grading time)
- CONTRACT: PASS requires (a) intake floors, (b) no regression vs incumbent on
  the general security bench, (c) beat best non-trained arm on the cousin
  bench, (d) operator confirm
- STATE EFFECT: verdict records; no auto-routing edits (existing
  execute_pending_verdicts discipline)

## I-18. Roster (ROSTER)

```python
recompute(window) -> RosterUpdate
```

- PRODUCER: `roster.py`; CONSUMER: HEART config activation (operator-approved)
- INPUT: council records from SUB (objection-validity, cousin-call
  correctness, participation)
- OUTPUT: bounded weights [0.5, 2.0] per seat + full rationale; activation is
  a queue item
- CONSTRAINTS (code): weights never consulted by the objection gate; family
  diversity enforced at roster load; abstentions count against participation
- STATE EFFECT: `roster_weights` rows (supersede); decision events
- IDEMPOTENCY: same window → same update (content key)
- OPERATOR BOUNDARY: activation confirm-only

## I-19. Mutation budget (cross-cutting)

- ENFORCER: MUT in code; checked against `hunt.yaml::mutation` per hunt
- INPUT: planned variants; OUTPUT: approved plan ≤ budget or explicit
  truncation with recorded rationale
- FAILURE: budget exceeded → truncation, never silent overflow
- OPERATOR BOUNDARY: budget values are operator dials

## I-20. Notifications

- REUSE: `portal.platform.inference.notifications` dispatcher exactly as
  `loop.py:232-298` does (fire-and-forget, non-fatal, `LOOP_NOTIFY_ENABLED`
  pattern) for: promotion-queue arrivals, honest-BLOCKED, plateau stops,
  council escalations. No new channel code.

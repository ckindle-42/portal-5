# VALIDATION — Defensive Bully

How the **implemented** system is proven. Success is semantic: no claim is
satisfied by the existence of a symbol, file, or mock. Each item uses CLAIM /
TEST METHOD / INPUT / EXPECTED BEHAVIOR / REQUIRED EVIDENCE / FAILURE MEANING.

Conventions: unit tests live in `portal/modules/security/tests/` (existing
surface glob — no spine cost), hermetic per Testing Rules (`tmp_path`, mocked
`httpx`, no network/lab/Splunk). Live proofs run against the lab and are
operator-invoked. Existing checks BQ/AZ/BM/BL/BN/BR/AW/BS/AL and the security
check families must stay green at every step (regression floor).

---

## 1. Component validation (unit level, hermetic)

### V-SUB — persistent substrate

- CLAIM: state survives process restart and drives later behavior.
- TEST: create SUB at `tmp_path`; record cousin + known-state + decision
  events; new process opens the same DB; TGT ranking reflects the recorded
  penalties.
- INPUT: synthetic cousin records, known-state entries with evidence refs.
- EXPECTED: identical read model after restart; supersede chains intact;
  decision log append-only (update/delete attempts rejected).
- EVIDENCE: test artifacts + DB inspection.
- FAILURE MEANING: the substrate is not actually persistent — feed closure is
  impossible; stop and fix.

- CLAIM: idempotent re-drive. Re-recording the same iteration (natural keys)
  does not duplicate rows.

### V-ORG — knowledge organ

- CLAIM: record-level upsert + k-NN with raw cosine distance + provenance
  filters; recall returns distance, not rerank scores.
- TEST: in-memory LanceDB at `tmp_path`; fake embed function (deterministic
  vectors); upsert 10 records across provenance classes; query.
- EXPECTED: distances monotonic with planted similarity; filters exclude
  other classes; SAME-grading authority rule enforced (no SAME resting solely
  on external_intel/operator_assertion).
- FAILURE MEANING: cousin metric is not semantic — BR-COUSIN would degrade to
  the lexical status quo.

### V-BR-COUSIN — grading engine

- CLAIM 1 (calibration): on a labeled fixture set of hunt records — exact
  re-executions, sibling sub-technique variants, same-tactic variants,
  unrelated attacks, benign shapes — grades match labels above the configured
  agreement floor (≥0.9 on the fixture set).
- CLAIM 2 (beats lexical): at least one fixture variant that
  `unknown_defense.compute_similarity` scores NONE/~0 is graded SIMILAR or NEW
  by the composite engine (the review-proven lexical failure case).
- CLAIM 3 (explainability): every verdict carries a full d1..d5 decomposition
  + feature citations; thresholds version recorded.
- CLAIM 4 (vetoes): discriminator contradiction downgrades SAME regardless of
  embedding proximity.
- FAILURE MEANING: the cousin engine is decoration, not discovery.

### V-BR-DRIFT — temporal engine

- CLAIM: given a synthetic firing series, the engine distinguishes the four
  drift classes; ATTACKER_EVOLUTION routes to BR-COUSIN; insufficient history
  yields the honest INSUFFICIENT-BASELINE flag.
- METHOD: planted series per class (telemetry collapse, population shift,
  partial-clause decay, behavior shift).

### V-BIN — alert bin gates

- G0: synthetic-origin-only candidate fails; observed-origin passes.
- G1a: signature that does not fire on the replayed capture fails; firing
  within window + right target passes (fixtures built from existing captures).
- G1b: dynamic re-execution mock (recipe stub) must be *required* — a
  candidate with G1a pass + no G1b evidence cannot advance.
- G2: a candidate whose discriminators fire on a benign-corpus fixture fails;
  verdict-contract counter-evidence path exercised.
- State machine: SUSPECT→…→PENDING transitions only in order; kills record
  gate + rationale; re-run idempotent.
- FAILURE MEANING: placeholder-gate regression (the growth_loop disease) —
  the bin is theater if any gate can pass without executing its check.

### V-HEART — objection gate

- CLAIM 1: a material objection (cites evidence contradiction / covering
  detection id / benign counter-evidence) left unrebutted BLOCKS promotion —
  even with all other seats supportive.
- CLAIM 2: a rebutted objection (rebuttal cites counter-evidence; falsifier
  re-pass withdraws) unblocks.
- CLAIM 3: non-material objections (generic unease without citation) do not
  block but are persisted.
- CLAIM 4: sub-floor participation invalidates the review → operator
  escalation, never auto-pass (BL semantics).
- CLAIM 5: roster family-diversity constraint rejects a mono-family roster at
  config load.
- METHOD: scripted seat responses (deterministic fixtures) through the real
  aggregation code.

### V-MUT — mutation director

- CLAIM: plans are structurally valid (overlay renders against the real
  scenario machinery), within budget (truncation recorded when exceeded),
  scope-guarded (out-of-lab targets rejected), and produce NO exec_chain/lab
  edits (guard test: overlay path imports no Red-internals beyond the public
  scenario surface).

### V-TGT / V-PLT / V-SCORE

- TGT: known-benign cell is declined with logged reasons; penalty math
  matches config; empty-eligible → honest stop.
- PLT: planted declining discovery series triggers rotate/stop per
  floor+patience+saturation; embedding-cluster-stable but discovery-positive
  series does NOT stop.
- SCORE: ANOMALOUS_UNCLASSIFIED counts as full catch (BN preserved);
  distance-weighted score orders far-NEW ≥ known-bad; benign false-flags
  typed (BQ preserved).

### V-HARV / V-PLAY / V-ROSTER

- HARV: pairs carry provenance; roles tagged; label-blind boundary test —
  production modules never import recall_attribution (import-scan test
  mirroring BM); dataset build deterministic (same window → same hash);
  below-floor corpus → documented non-build.
- PLAY: drafts only from recorded trajectories; activation requires operator;
  `for_hunt` returns none (neutral) for uncovered classes.
- ROSTER: weights bounded [0.5,2.0]; objection gate provably ignores weights
  (test: lowest-weight seat's material objection blocks); changes are
  decision-logged; activation confirm-only.

## 2. Integration validation

- CLAIM: a full iteration runs end-to-end with mocked models + synthetic lab
  (the existing `_synthetic_tool_result` path): LOAD→RECALL→SELECT→DIRECT→
  INVESTIGATE→GRADE→GATE→RECORD→STOP, with every write landing (SUB rows,
  ORG records, decision events, corpus pairs).
- EVIDENCE: post-run DB/organ inspection + report content.
- CLAIM: recall is **enforced**: a hunt whose ORG recall raises
  OrganUnavailable blocks; there is no code path that directs Red without a
  recorded RecallResult (structural test + code review gate).
- CLAIM: universal indexing: iteration close with an unindexed emission fails
  loudly (structural test).
- CLAIM: bench CLI regression: existing security check families (J/P/Q/S/U/V/
  Z/AA–AH/AM/AN/AX–BP) stay green throughout migration.

## 3. Behavioral validation (live lab, operator-invoked)

- CLAIM: live hunt manufactures a cousin — Red runs the MUT overlay against
  the lab, telemetry lands episode-scoped, the investigation arm concludes,
  grading emits a decomposition.
- INPUT: a seeded neighborhood (e.g. kerberoast family) with a planted
  variant (parameter/sub-technique perturbation the current SPL misses).
- EXPECTED: the variant is graded SIMILAR-or-ANOMALOUS with detection-blind
  evidence; the base re-run is graded SAME and caught by existing SPL.
- EVIDENCE: Episode records, Splunk episode query output, grading records.
- FAILURE MEANING: the loop manufactures but does not discover — investigate
  MUT validity, telemetry contracts, or grading calibration, in that order.

## 4. Cousin-discovery validation (the product proof)

- CLAIM: the system surfaces a previously-uncovered cousin end-to-end.
- METHOD: select a covered technique; MUT generates N budgeted variants
  (parameter, timing, artifact, sub-technique adjacency); at least one
  variant is designed (by the operator, for the proof) to evade current SPL.
- EXPECTED: the evading variant lands RED_LANDED, detection-blind, graded
  SIMILAR/ANOMALOUS, enters the bin, and its distance decomposition + nearest
  known are recorded; the non-evading variants are caught (SAME) — proving
  the grading discriminates, not merely alarms.
- REQUIRED EVIDENCE: the full per-variant record set; the caught/missed split.
- FAILURE MEANING: cousin discovery is not demonstrated; the product claim
  fails. Do not paper over with a coverage-checkmark run.

## 5. Alert-bin validation (live)

- CLAIM: promotion requires all gates incl. G3.
- METHOD: run the §4 cousin through the bin with (a) a planted benign-twin
  variant whose discriminators hit the benign corpus (must die at G2), (b)
  the real cousin (must reach PENDING_OPERATOR).
- EXPECTED: G1a static replay fires; G1b re-execution reproduces artifacts;
  G3 produces a triage report ≤P2 within SLA under the queue-load corpus;
  operator confirm promotes; operator reject kills with indexed rationale.
- FAILURE MEANING: a gate is not real — find which and fix; never relax a
  gate to force the proof.

## 6. Adversarial-council validation (live)

- CLAIM: the council kills a plausible-but-wrong candidate and passes a true
  one.
- METHOD: two candidates — (a) fabricated-evidence cousin (grounded-looking
  but contradicted by telemetry), (b) the §5 real cousin. Scripted hunt;
  live seats.
- EXPECTED: (a) at least one seat raises a material objection; unrebutted →
  BLOCKED, record persisted with dissent; (b) objections (if any) rebutted by
  evidence → eligible. Participation below floor → operator escalation.
- FAILURE MEANING: the council is a vote-aggregator in disguise — re-examine
  the gate code path.

## 7. Temporal-drift validation (live)

- CLAIM: drift classes are distinguished on real telemetry.
- METHOD: (a) suppress a sourcetype for a window (telemetry failure);
  (b) replay an evolved variant of a covered technique (attacker evolution);
  (c) normal operation (no flag).
- EXPECTED: correct classification each; (b) routes into cousin grading and
  appears as a temporal-cousin lead.
- FAILURE MEANING: drift engine is noise — recalibrate signals/baselines.

## 8. Mutation validation

- CLAIM: mutations are structurally valid and adversarially useful.
- METHOD: variant corpus from MUT across the documented dimensions
  (parameters, timing, sequence, artifacts, sub-techniques).
- EXPECTED: 100% parse/execute as valid TTPs (no "invalid format" equivalents
  — Red completes chains); measured spread across dimensions; budget
  truncation logged.
- FAILURE MEANING: mutation is random noise, not grammar fuzzing's analogue.

## 9. Compounding validation (the six feeds)

- CLAIM: hunt N+1 is measurably better than hunt N, per feed instruments.
- METHOD: a recorded hunt series (≥5 hunts over overlapping neighborhoods,
  scripted + live mix).
- EXPECTED (each is a number in the series report):
  1. recall-hit utilization > 0 and rising; neighborhood reuse visible in TGT
     choices;
  2. known-dead cells skipped automatically (waste rate falls toward 0);
  3. cost-per-promoted-cousin falls across the series;
  4. corpus grows with role coverage;
  5. (post-TRAIN) specialist arm beats base arm on cousin bench;
  6. playbook-shaped hunts consume less budget to conclusion than unshaped.
- EVIDENCE: the series report + underlying decision events.
- FAILURE MEANING: storage without learning — locate the broken link
  (retrieval? decision impact?) and fix; do not claim compounding without the
  trend.

## 10. Training-improvement validation

- CLAIM: the trained specialist earns its serve.
- METHOD: the acceptance gate's five arms (base / +retrieval / +playbook /
  +both / trained) on the cousin-judgment bench + general security bench.
- EXPECTED: trained ≥ best non-trained arm on cousin judgment (statistically
  meaningful per the bench's existing bootstrap-CI practice) AND no general
  regression; intake floors pass; operator confirm recorded.
- FAILURE MEANING: training provides no measurable gain → do not serve
  (documented non-serve; the feed remains, the model doesn't). This is a
  success path for honesty, not a build failure.

## 11. SOC-context validation

- CLAIM: G3 measures real analyst visibility.
- METHOD: queue-load corpus (seeded benign volume + concurrent notables)
  through the triage lane with the candidate notable injected.
- EXPECTED: promoted findings surface at ≤ threshold priority within SLA;
  harness-only visibility (finding present in results but absent from the
  triage report) is detected and fails G3.
- FAILURE MEANING: the consumer-context gate is asserted, not measured —
  equivalent to the concept's SYSTEM-only finding.

## 12. Performance/resource validation

- CLAIM: a hunt iteration completes within configured budgets on the host
  fleet; council serialization respects backend memory; organ upsert batch
  sizes respect the CPU embedding service.
- METHOD: instrumented live hunt; resource log review.
- EXPECTED: no OOM/backend eviction; wall-clock within `budgets` config;
  degradation (embed down) blocks honestly.

## 13. Regression validation

- All pre-existing gates stay green at every migration step: BQ, AZ, BM, BL,
  BN, BR, AW, BS, AL + security families J/P/Q/S/U/V/X/Z/AA–AI/AM/AN/AX–BP.
- The bench suite (`pytest tests/unit`, plus the security module tests)
  remains green; `pytest portal` write-through artifacts cleaned per
  CLAUDE.md testing rules.
- Spine: BR/BS green — new modules under existing globs; at most one authored
  design unit per phase; re-pin via the two-commit sequence when required.

## 14. Final end-to-end proof

The single demonstration that closes the program (mirrors DESIGN §38):

> A recorded hunt series in which: a MUT-generated cousin evades current SPL
> → is graded ANOMALOUS_UNCLASSIFIED with decomposition → survives the bin
> (G1a/G1b/G2/G3) → survives a live falsification council (one planted
> material objection shown blocking until rebutted) → is operator-confirmed →
> exits through HND with a family-generalizing detection whose regression
> recipe replays green and whose spl_detections.yaml change keeps BQ/AZ green
> → the kill of a planted nonsense candidate is indexed and demonstrably
> recalled by a later hunt → the trained cousin-specialist (post-gate,
> operator-confirmed) is used by a later hunt and beats the base model on the
> cousin bench → the cost-per-promoted-cousin series falls across the series.

Every claim cites its artifact: Episode ids, SUB rows, ORG records, gate
results, council records, handoff package, recipe run, bench reports, cost
series. Missing evidence = the claim is unproven, and the gap is reported
honestly.

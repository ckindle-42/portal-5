# FINAL VALIDATION — Defensive Bully

How the **implemented** system is proven. Success is semantic: no claim is
satisfied by the existence of a symbol, file, mock, or generated narrative.
A required case cannot pass by skip. Synthetic fixtures prove plumbing and
deterministic logic but never satisfy real-evidence promotion, SOC, or
end-to-end claims. Statistical claims publish intervals and raw counts;
thresholds and calibration artifacts are **frozen before the held-out final
runs** and may not be tuned on final results.

Conventions: unit tests live under the existing security test surface
(`portal/modules/security/tests/`, `tests/security/bully/`), hermetic per
Testing Rules (`tmp_path`, mocked `httpx`, no network/lab/Splunk). Live
proofs run against the lab and are operator-invoked. Existing checks BQ, AZ,
BM, BL, BN, BR, AW, BS, AL and the security check families must stay green at
every step (regression floor). Each item: CLAIM / TEST METHOD / INPUT /
EXPECTED BEHAVIOR / REQUIRED EVIDENCE / FAILURE MEANING. Every run emits
validation records (code commit, config/schema/algorithm/model versions,
suite/case hashes, exact inputs, expected/observed, evidence hashes, resource
use, retries/skips, failure meaning) — a required skip is a failure.

---

## 1. Component validation (unit level, hermetic)

### C1 — Authoritative state survives and rejects illegal transitions

- CLAIM: SUB is restart-safe, append-only, state-machine enforced.
- METHOD: unit/property tests plus process-kill recovery at every
  transaction/external-call boundary; corrupt a copied database/evidence
  item; attempt stale/illegal transitions.
- INPUT: representative hunts, candidates, objections, outbox items, leases,
  supersessions.
- EXPECTED: committed events recover exactly once; uncommitted work never
  appears; stable idempotency returns the original receipt; stale/illegal
  commands fail; corruption blocks affected claims; decision log rejects
  update/delete.
- EVIDENCE: DB/event-chain audit, before/after snapshots, command receipts,
  recovery logs.
- FAILURE MEANING: no higher-level capability is trustworthy; release blocks.

### C2 — Evidence integrity and truth boundaries

- CLAIM: every derived claim traces to immutable evidence; synthetic or
  unverified data cannot be promoted.
- METHOD: mutate/delete bytes after manifest creation; import incomplete
  legacy evidence; mark fixtures synthetic; exercise G0.
- EXPECTED: valid hashes verify; tampering/missing data invalid/quarantined;
  telemetry absence indeterminate; synthetic never passes G0 (checks +
  application rule).
- EVIDENCE: manifest/hash verification and gate events.
- FAILURE MEANING: the evidence-truth invariant is broken; release blocks.

### C3 — Outbox, projection, and recall

- CLAIM: all required knowledge is eventually indexed exactly once; recall
  dereferences authority; required dead letters block closure.
- METHOD: inject embed/rerank/LanceDB outages, duplicate deliveries, worker
  death, stale rows, full projection deletion/rebuild.
- EXPECTED: no lost outbox record; duplicates converge; stale/hash-mismatched
  rows rejected; rebuild equivalent; required dead letter blocks hunt closure
  and recall; a hunt cannot target without a persisted RecallReceipt.
- EVIDENCE: SQL source counts/hashes, outbox attempts, projection comparison,
  recall receipts.
- FAILURE MEANING: mandatory recall/compounding claims fail.

### C4 — Deterministic calculations

- CLAIM: signatures, distance, temporal signals, posteriors, plateau, and
  gate legality are repeatable at fixed versions.
- METHOD: golden vectors, property tests, boundary values, reordered JSON/DB
  rows, replay from stored inputs.
- EXPECTED: byte-equivalent canonical outputs; missing data not
  renormalized/zeroed; threshold ties per spec; same versions → same
  decisions.
- EVIDENCE: golden artifacts and property-test reports.
- FAILURE MEANING: decision audit cannot be reproduced.

### C5 — Cousin engine (two-axis grading)

- CLAIM 1 (calibration): on a labeled fixture set — exact re-executions,
  sibling sub-technique variants, same-tactic variants, unrelated attacks,
  benign shapes — relationship grades match labels at or above the configured
  agreement floor (≥0.9 on the fixture set).
- CLAIM 2 (beats lexical): at least one fixture variant that
  `unknown_defense.compute_similarity` scores NONE/~0 grades SIMILAR or NEW
  under the composite (the documented lexical failure case,
  `unknown_defense.py:112-128`).
- CLAIM 3 (explainability): every assessment carries the full five-dimension
  decomposition + feature citations + response-axis evidence + threshold
  version.
- CLAIM 4 (vetoes): a discriminator contradiction downgrades SAME regardless
  of embedding proximity; SIMILAR/NEW with <2 non-semantic channels is
  impossible; semantic distance alone never produces SIMILAR/NEW.
- CLAIM 5 (axis independence): a MISSED response never inflates D; a
  semantically distant but response-identical pair grades DIFFERENT, not NEW;
  `SAME×MISSED` is classified regression, not discovery.
- FAILURE MEANING: the cousin engine is decoration, not discovery.

### C6 — Drift engine

- CLAIM: given synthetic firing series, the engine distinguishes the four
  causes + UNCLASSIFIED via the deterministic attribution order;
  ATTACKER_EVOLUTION routes to BR-COUSIN; insufficient history yields
  INSUFFICIENT-BASELINE.
- METHOD: planted series per class (telemetry collapse, population shift,
  rule change with stable attack, behavior shift with healthy controls,
  ambiguous combination); model-canary evidence held constant.
- EXPECTED: correct classification each; sensor failure takes precedence;
  version change starts warm-up, not inherited confidence.
- FAILURE MEANING: drift is noise — recalibrate signals/baselines.

### C7 — BIN gates and state machine

- G-1: an unauthorized scope/mutation class cannot create a candidate.
- G0: synthetic-origin-only candidate fails; observed-origin passes.
- G1a: a signature that does not fire on the replayed capture fails; firing
  within window + right target passes (fixtures from existing captures).
- G1b: dynamic re-execution is *required* — G1a pass + no G1b evidence cannot
  advance; the declared 2-of-3 policy behaves as specified.
- G2: a candidate whose discriminators fire on a benign-corpus fixture fails;
  matched-control alternatives end BENIGN/DISPROVED; verdict-contract
  counter-evidence path exercised.
- State machine: transitions only in legal order; kills record gate +
  rationale; changed evidence creates a new alert version and invalidates
  downstream passes; re-run idempotent.
- FAILURE MEANING: placeholder-gate regression (the growth_loop disease) —
  the bin is theater if any gate can pass without executing its check.

### C8 — HEART objection gate

- CLAIM 1: a material objection left unrebutted BLOCKS promotion — even with
  all other seats supportive.
- CLAIM 2: a rebutted objection (counter-evidence cited; falsification
  re-pass on the same evidence version withdraws) unblocks.
- CLAIM 3: non-material objections do not block but persist.
- CLAIM 4: sub-floor participation invalidates the review → operator
  escalation, never auto-pass (BL semantics).
- CLAIM 5: roster family-diversity constraint rejects a mono-family roster at
  config load.
- CLAIM 6: withdrawal requires the originating/equivalent seat; an
  unauthorized waiver is denied; an authorized waiver records identity/
  reason and remains visible downstream.
- METHOD: scripted seat responses (deterministic fixtures) through the real
  aggregation code.
- FAILURE MEANING: the council is a vote-aggregator in disguise.

### C9 — Mutation director

- CLAIM: plans are structurally valid (compile against the real scenario
  machinery), within budget (truncation recorded), scope-guarded
  (out-of-lab rejected), and produce NO Red-internals edits (guard test: the
  overlay path imports nothing beyond the public scenario surface).
- Also: unknown operator / invariant conflict / unbounded parameter /
  missing control / un-collectable expected evidence → rejected, never
  partially compiled.
- FAILURE MEANING: mutation is random noise, or the Red boundary is broken.

### C10 — TGT / PLT / SCORE / COST

- TGT: a known-benign cell is declined with logged reasons; known-state
  adjusts the posterior (never a second multiplier); hard eligibility
  excludes unauthorized/unready/unhealthy/locked cells; missing material
  cost → unrankable; deterministic tie-break; empty eligible → honest stop.
- PLT: a planted declining series triggers rotate/stop per the statistical
  rule; <8 valid trials or <2 dimensions → no plateau; blocked trials
  excluded; embedding-cluster-stable but discovery-positive series does NOT
  stop; a version change resets the neighborhood.
- SCORE: ANOMALOUS_UNCLASSIFIED is an Axis-1 catch and the trust ordinal
  holds (BN); the discovery axis orders far-NEW ≥ known-bad; benign
  false-flags typed (BQ).
- COST: typed quantities recorded separately; pricing-profile conversion;
  missing measurement = null + quality flag, blocking ROI claims.

### C11 — HARV / PLAY / ROSTER

- HARV: pairs carry provenance; roles tagged; BM import-boundary test passes
  (production modules never import recall_attribution); dataset build
  deterministic (same window → same hash); below-floor corpus → documented
  non-build; leakage/duplicate/suspect examples quarantine.
- PLAY: drafts only from recorded trajectories; activation requires operator;
  `for_hunt` returns none (neutral) for uncovered classes; canary failure
  auto-reverts the pointer.
- ROSTER: advisory weights bounded [0.5, 2.0]; the objection gate provably
  ignores weights/reliability (test: the lowest-weight seat's material
  objection blocks); updates use only post-decision outcomes; changes
  decision-logged; activation confirm-only.

## 2. Integration validation

### I1 — Current Red/Purple compatibility

- CLAIM: bully integration preserves existing Red execution and Purple result
  semantics.
- METHOD: golden current bench cases with the feature flag off, shadow on,
  and bully-authoritative initiation; compare legacy outputs and tool traces.
- EXPECTED: feature-off unchanged; shadow does not affect results; the
  adapter preserves statuses/evidence/tool args; infrastructure failure is
  not discovery yield; `git diff` on `exec_chain`/`lab` after a mutation run
  is empty.
- EVIDENCE: diff/golden reports; existing security validation results.
- FAILURE MEANING: migration cannot proceed.

### I2 — Hunt iteration end-to-end (mocked models + synthetic lab)

- CLAIM: a full iteration runs LOAD→RECALL→SELECT→DIRECT→INVESTIGATE→GRADE→
  GATE→RECORD→STOP with every write landing (SUB rows, ORG records, decision
  events, corpus pairs) via the existing synthetic tool path.
- CLAIM (enforcement): a hunt whose ORG recall raises OrganUnavailable
  blocks; there is no code path that directs Red without a recorded
  RecallReceipt (structural test). An iteration closing with a required
  unindexed emission fails loudly (structural test).
- CLAIM (budgets): iteration/wall-clock/lab-action budgets are enforced by
  the orchestrator itself; admission control refuses lab actions while a
  bench/engagement lock is active.
- EVIDENCE: post-run DB/organ inspection + report content + budget ledger.

### I3 — Thin CLI/config

- CLAIM: transports call the same application contracts and own no state;
  config snapshots are taken per hunt; training libraries are not imported by
  runtime startup.
- METHOD: command equivalence, concurrent/retry/auth tests, service restart,
  import trace.
- FAILURE MEANING: authority or operability boundary fails.

## 3. Behavioral validation (live lab, operator-invoked)

### B1 — Spatial cousin discovery (the product proof)

- CLAIM: the system surfaces a previously-uncovered cousin end-to-end.
- METHOD: select a covered technique; MUT generates N budgeted variants
  (parameter, timing, artifact, sub-technique adjacency); at least one
  variant is designed (by the operator, for the proof) to evade current SPL.
- EXPECTED: the evading variant lands RED_LANDED, response=MISSED, graded
  SIMILAR-or-NEW×MISSED (or ANOMALOUS×blind), enters the bin, decomposition +
  nearest known recorded; the non-evading variants are caught (SAME×COVERED)
  — proving the grading discriminates, not merely alarms; a paired baseline
  run holds environment/telemetry equivalence.
- EVIDENCE: full per-variant record set; the caught/missed split.
- FAILURE MEANING: cousin discovery is not demonstrated; do not paper over
  with a coverage-checkmark run.

### B2 — Relationship ≠ response

- CLAIM: factorial fixtures/real replays across SAME/SIMILAR/NEW/DIFFERENT ×
  COVERED/NEAR_MISS/MISSED/INDETERMINATE behave per the two-axis model.
- EXPECTED: SAME×MISSED is regression; NEW×COVERED is family knowledge, not a
  gap; telemetry failure is INDETERMINATE; axes never overwrite each other.
- FAILURE MEANING: targeting/promotion labels are unsafe.

### B3 — Discovery yield over legacy

- CLAIM: the complete system finds blinded structural cousins that
  token-matching and current detectors miss, without reducing known-bad
  recall.
- METHOD: hold out whole cousin families; run retrieval + classification
  label-blind; compare to the legacy heuristic and known-bad baseline against
  pre-registered recall/precision policy.
- EVIDENCE: frozen manifest, raw predictions, family-grouped metrics/
  intervals, errors.
- FAILURE MEANING: final calibration/implementation is not accepted.

## 4. Mutation validation

- CLAIM (M1): plans stay in scope and create their declared structural delta
  while preserving invariants.
- METHOD: schema/property/fuzz tests + one-dimension and approved
  multi-dimension real lab executions with cleanup verification.
- EXPECTED: unsafe/unknown/unbounded plans never compile; compiled orders use
  allowlisted tools/targets; observed signature matches expected delta;
  cleanup succeeds or safety-blocks; 100% of dispatched mutants execute as
  valid TTPs (no "invalid format" equivalents — Red completes chains).
- CLAIM (M2): multi-dimensional conclusions are not attributed without
  controls (causal isolation).
- EXPECTED: a confounded/under-controlled case is UNCLASSIFIED/BLOCKED; the
  controlled case can advance.
- FAILURE MEANING: MUT cannot be enabled / causal claims are invalid.

## 5. Alert-bin and SOC-context validation (live)

- CLAIM (A1): no alert can skip gates or reuse stale proof (transition-table
  coverage; changed manifest invalidates downstream).
- CLAIM (A2): promotion requires fresh execution + clean replay (or declared
  2-of-3), healthy controls, and behavioral — not signature-only —
  reproduction. Live paired cases: true miss / irreproducible event /
  signature-only artifact / benign causal alternative / telemetry outage /
  environment change — only the true reproducible causally-supported case
  passes G1/G2.
- CLAIM (A3): the Bully finding — not the missed detector — reaches the
  actual analyst-visible path intact and within SLO. Deliver uniquely marked
  findings; query the same analyst-consumed index/notable path under replayed
  normal and peak queue load; inject producer-only ack/content
  truncation/latency.
- EXPECTED: G3 passes only on the consumer-side receipt (triage report ≤
  configured priority within SLA) with content hash match; harness-only
  visibility is detected and fails.
- FAILURE MEANING: the consumer-context gate is asserted, not measured —
  equivalent to the concept's SYSTEM-only finding.

## 6. Adversarial-council validation (live)

- CLAIM (H1): the council kills a plausible-but-wrong candidate and passes a
  true one — one material objection blocks regardless of other supports or
  reliability; reviewers are independent (isolation, frozen packet).
- METHOD: two candidates — (a) fabricated-evidence cousin (grounded-looking
  but contradicted by telemetry), (b) the §5 real cousin; scripted hunt, live
  seats; include a 4-support/1-material-reject case and a high-reliability vs
  low-reliability split.
- EXPECTED: (a) at least one seat raises a material objection; unrebutted →
  BLOCKED, record persisted with dissent; (b) objections rebutted by evidence
  → eligible. Participation below floor → operator escalation.
- CLAIM (H2): rebuttal does not self-close — withdrawal requires cited
  evidence re-review; waiver is explicit, authorized, reasoned, and visible.
- FAILURE MEANING: the council is democratic theater — re-examine the gate
  code path.

## 7. Temporal-drift validation (live)

- CLAIM (T1): causes are distinguished on real telemetry with matched
  controls: suppress a sourcetype (telemetry degradation); replay an evolved
  variant (attacker evolution); change a rule with stable attack (detection
  degradation); shift the environment (environment change); normal operation
  (no flag).
- EXPECTED: correct classification each; only attacker-evolution routes into
  cousin grading as a temporal-cousin lead; sensor failure takes precedence.
- CLAIM (T2): stationary/noisy series do not alert beyond calibrated false-
  alert policy; consecutive/critical breach rules work; key changes start
  warm-up rather than inheriting confidence.
- FAILURE MEANING: drift engine is noisy or causally stale — recalibrate.

## 8. Targeting, plateau, cost validation

- CLAIM (R1): selection uses hard eligibility, conservative posterior value,
  and nonzero measured cost without double counting.
- METHOD: golden ranking; correlated-feature cases; low-sample uncertainty;
  missing cost; tie-break; readiness/authorization exclusions.
- CLAIM (R2): only sufficiently tested exhausted neighborhoods stop; material
  version changes reopen them; blocked failures never count.
- FAILURE MEANING: hunt allocation is unauditable / the system stops too
  early or burns budget indefinitely.

## 9. Compounding validation (the six feeds)

- CLAIM (F1): each feed has an activated record and a later causal decision
  effect.
- METHOD: paired deterministic runs from identical initial snapshots, one
  with the feed activated and one without, for: recalled objection/control
  (feed 1); known benign/covered outcome (2); updated ROI yield/cost (3);
  harvested negative/positive example in a released dataset (4); accepted
  specialist alias (5); active playbook (6).
- EXPECTED: the later target ranking, control/action, model-output metric, or
  playbook action changes exactly as policy predicts; a DecisionImpact links
  the source; a no-effect is honestly recorded.
- EVIDENCE: before/after snapshots, feed activation, recall/impact receipts,
  downstream outputs.
- FAILURE MEANING: persistence exists but compounding does not — locate the
  broken link (retrieval? decision impact?) and fix; never claim compounding
  without the trend.
- CLAIM (F2): negative/contradiction/expiry/poisoning resistance — scoped
  priors adjust; blocked is not benign; contradiction forces review; expiry
  removes stale influence; suspect/retrieved instructions cannot expand
  tools/scope or clear gates.

## 10. Detection-handoff validation

- CLAIM (D1): a promoted finding produces a complete family-level proposal,
  and coverage changes only after external deployment plus real replay.
- METHOD: accept/reject/revise/expire proposals; simulate a draft-syntax pass
  without deployment; deploy a version then run positive/negative Purple
  replay.
- EXPECTED: no automatic rule write; the three proof legs execute for real
  (fires-on-attack via recipe replay; quiet-on-benign via benign corpus;
  no-regression via BQ/AZ lanes); all dispositions feed ORG; KNOWN_COVERED
  only after deployment receipt + successful deployed-version replay with
  acceptable negative noise; the regression recipe replays green.
- FAILURE MEANING: the detection-engineering exit is unsafe or fictitious.

## 11. Training-improvement validation

- CLAIM (L1 — dataset integrity): released datasets are reproducible,
  provenance-complete, deduplicated, split by family/campaign/time with the
  test set frozen before the harvest window.
- METHOD: deliberately inject duplicates, same-evidence variants, cross-split
  families, post-cutoff test-derived labels, secret/unlicensed/suspect
  records.
- EXPECTED: invalid examples quarantine; grouped split prevents leakage;
  released manifest reproduces exact ordered bytes; later correction creates
  a new version.
- CLAIM (L2 — honest refinement verdict; superseded 2026-08-15 by approved
  P6.7/A2-A3): periodic, operator-launched investigation-arm refinement runs
  only when HARV reports marginal knowledge. Intake floors, a fail-closed
  candidate-vs-incumbent general-security comparison, and a model canary must
  all pass before the candidate enters `PENDING_MODEL_VERDICTS`; serving is a
  separate operator-confirmed action. A genuine shelve/non-serve is an honest
  success path. This supersedes the earlier per-cycle multi-arm-gain framing,
  which over-read the concept source's future aspiration as an inline gate.
- CLAIM (L3 — deployment/resources/rollback): exclusive lock prevents
  conflicting lab/bench work; preflight failure leaves the active alias
  unchanged; checkpoint resumes compatibly; hashes connect
  base→adapter→GGUF→tag; canary failure/rollback atomically restores the
  prior alias.
- FAILURE MEANING: training provides no measurable gain → documented
  non-serve; TRAIN cannot activate artifacts until L3 passes.

## 12. SOC-context standing checks

- BQ (benign alert-fatigue): benign corpus through the bin → G2 rejects;
  benign notifications typed as false flags. COVERED BY BQ — must stay green.
- AZ (recall vs emergent corpus): detection recall against the emergent-miss
  corpus. COVERED BY AZ — must stay green.

## 13. Performance/resource validation

- CLAIM (P1): a hunt iteration completes within configured budgets on the
  host fleet; council serialization respects backend memory; organ upsert
  batch sizes respect the CPU embedding service; admission control prevents
  hunt/bench/lab contention; training never overlaps a live hunt; projection
  rebuild is rate-limited/resumable.
- METHOD: instrumented live hunt + induced dependency latency + resource log
  review (RSS/disk/CPU/model residency/queue/budget series).
- EXPECTED: no OOM/backend eviction; wall-clock within budgets; degradation
  blocks honestly.
- FAILURE MEANING: resource configuration must change before activation, not
  product scope.

## 14. Regression validation

- All pre-existing gates stay green at every migration step: BQ, AZ, BM, BL,
  BN, BO, BE, BF, BP, BR, AW, BS, AL + security families
  (J/P/Q/S/U/V/X/Z/AA–AI/AM/AN/AX–BH/BK).
- The unit suite (`pytest tests/unit -q`) and the security module tests
  remain green; `pytest portal` write-through artifacts cleaned per the
  testing rules (`field_journal/_index.json` checkout discipline).
- Spine: BR/BS green — the new package is covered by its deliberate surface
  entry; at most one authored design unit per phase; two-commit re-pin
  sequence when BS stales a pin.
- Public import/startup never requires training extras; legacy bench outputs
  byte-stable with the feature flag off.
- The two drift engines (bench-metric vs detection-baseline) are provably
  non-substitutable.

## 15. Final end-to-end proof

The single demonstration that closes the program — one recorded hunt series
on a clean authorized lab containing, linked in one audit graph:

> authorization + config snapshot → mandatory recall (receipt) → target
> decision (recorded factors) → a validated MutationPlan executed through
> unchanged Red → real Episode + hashed evidence manifest → two-axis
> classification (decomposition + response) → a planted false/benign
> hypothesis rejected (G2) → the true cousin reproduced (G1a/G1b) and
> causally validated → a planted material council objection blocking until
> rebutted on the same evidence version (waiver path separately exercised) →
> SOC delivery under queue load within SLO → operator promotion → HND
> family package whose proof legs execute and whose regression recipe replays
> green → deployment + post-deploy replay closing the cell → outbox/cost
> records closed → a planted nonsense candidate's kill indexed and
> demonstrably recalled by a later hunt → a later hunt's target selection
> observably changed by the first hunt's records (DecisionImpact) → a
> statistical plateau + a version-change reset → a temporal
> detection-degradation case correctly classified → playbook canary →
> cousin-calibration curve → dataset-readiness readout → one
> operator-launched refinement to a genuine serve-or-shelve verdict → model
> canary/rollback drill → injected-failure recovery (restart, outbox retry,
> lease expiry) → all standing gates green.

Every claim cites its artifact: Episode ids, SUB rows, ORG records, gate
results, council records, receipts, handoff package, recipe run, bench
reports, cost series, resource traces. Missing evidence = the claim is
unproven, and the gap is reported honestly.

## 16. Release acceptance

Release requires C1–C11, I1–I3, B1–B3, M1–M2, A1–A3, H1–H2, T1–T2, R1–R2,
F1–F2, D1, L1–L3, P1, the §12 standing checks, §13–§14, and E2E. Any
safety/truth/provenance failure is zero-tolerance. Statistical product
thresholds may be revised only through an approved new policy version
followed by a completely rerun frozen evaluation — never tuned on final test
results.

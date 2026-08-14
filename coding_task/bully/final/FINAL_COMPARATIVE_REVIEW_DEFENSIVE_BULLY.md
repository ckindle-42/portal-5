# FINAL COMPARATIVE REVIEW — Defensive Bully (K3 × O48 × SOL)

**Review of record for the three-plan synthesis.** This document preserves the
comparative evidence: what each plan says, where they agree, where they
disagree, what the current Portal code says about each disagreement, and what
the synthesis concluded. It is evidence and rationale, not the specification.
Authority order in the final package: `FINAL_DESIGN_DEFENSIVE_BULLY.md` (WHAT)
→ `FINAL_ARCHITECTURE_/FINAL_INTERFACES_/FINAL_DATA_MODEL_` (contracts) →
`FINAL_MIGRATION_` (transition) → `FINAL_VALIDATION_` (proof) →
`FINAL_BUILD_PROGRAM_` (sequence) → `FINAL_DECISION_LEDGER_` (why) → this file
(comparative evidence).

Evidence markers: **VERIFIED FACT** (read in code at HEAD by this reviewer) ·
**PLAN CLAIM** (asserted by a plan) · **INFERENCE** · **FINAL DESIGN DECISION**.
Basis tags: `K3` / `O48` / `SOL` / `ALL THREE` / `CURRENT CODE` / `NEW SYNTHESIS`.

---

## 1. Repository ground truth

Recorded before any comparison (Phase 1):

```text
pwd:        /Users/chris/projects/portal-5
branch:     main
HEAD:       47d3e884c8f0415ed26dbf77f5e817a22ce613ac
            "chore(spine): re-pin units after lane-closeout + Ollama-docs commit"
remote:     origin https://github.com/ckindle-42/portal-5.git
status:     working tree dirty with ANOTHER agent's in-flight bench work
            (config/backends.yaml, config/portal.yaml, docs/ADMIN_GUIDE.md,
            two wiki units, tests/benchmarks/* artifacts, .serena/,
            scripts/check_model_bindings.py). Not touched by this review.
git:        reads only. No mutations of any kind were performed.
coding_task/: gitignored (.gitignore:54) — the final package lives outside
            version control by design.
```

- The prior build program's reference commit was `ee9272e`; all three plans and
  this review use HEAD `47d3e884`. Between them: eval-gate instrumentation,
  slot-fixes, spine re-pins; **zero security-core `.py` changes** (O48 diffed
  this explicitly; K3 confirmed by re-verification).
- All three plans were produced against the same HEAD. Differences between
  them are therefore reasoning differences, not repository drift.
- **VERIFIED FACT:** validation suite is 76 `@register` decorators across
  `scripts/validation/*.py` at this HEAD (K3 counted 74; CLAUDE.md prose says
  72 — stale). All run pre-push.

## 2. Three-package inventory

All 27 expected documents exist; each family has exactly the 9-document set.
Four shared context files also exist and were read: `BULLY_CONCEPT_SOURCE.md`
(the Andy Gill concept blog), `HANDOFF_DEFENSIVE_BULLY_CONTEXT.md` and
`BUILD_PROGRAM_DEFENSIVE_BULLY.md` (the prior design + reasoning the three
plans reacted to), `bully_final_review.md` (this task's contract).

| Purpose | K3 file | O48 file | SOL file | Present in all? |
|---|---|---|---|---|
| Current-state review | K3_REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md (862 lines) | O48_REVIEW_… (426) | SOL_REVIEW_… (277) | YES |
| Final design | K3_DESIGN_DEFENSIVE_BULLY_FINAL.md (782) | O48_DESIGN_… (538) | SOL_DESIGN_… (390) | YES |
| Architecture | K3_ARCHITECTURE_… (292) | O48_ARCHITECTURE_… (294) | SOL_ARCHITECTURE_… (223) | YES |
| Interfaces | K3_INTERFACES_… (433) | O48_INTERFACES_… (298) | SOL_INTERFACES_… (237) | YES |
| Data model | K3_DATA_MODEL_… (241) | O48_DATA_MODEL_… (281) | SOL_DATA_MODEL_… (139) | YES |
| Migration | K3_MIGRATION_… (273) | O48_MIGRATION_… (233) | SOL_MIGRATION_… (217) | YES |
| Validation | K3_VALIDATION_… (294) | O48_VALIDATION_… (254) | SOL_VALIDATION_… (309) | YES |
| Implementation requirements | K3_IMPLEMENTATION_REQUIREMENTS_… (255) | O48_… (196) | SOL_… (232) | YES |
| Handoff | K3_HANDOFF_… (221) | O48_HANDOFF_… (193) | SOL_HANDOFF_… (172) | YES |

No family is missing documents; no family contains extra artifacts.
Filenames are semantically identical across families; no purpose-mapping
ambiguity. Total read volume: 8,562 plan lines + ~1,380 context lines.

## 3. Required reading completed

All 27 plan documents were read completely, end to end, by this reviewer (not
skimmed, not grep-inferred), plus the four context documents. Repository
verification reads are cited inline in §7 with `path:line` anchors. Subagent
use: none for the plan documents; repository tracing was done by direct reads
of every load-bearing surface listed in §7.

## 4. K3 architecture summary (independent model)

**Central thesis.** The prior build program is conceptually correct; its
implementation assertions drifted from HEAD in ten material places. Verdict:
`DESIGN REQUIRES REFINEMENT`. Cousin discovery is the product; suspect-until-
proven; adversarial council; six compounding feeds, each with a *named
measurable-change instrument* so compounding is falsifiable.

**Component model.** Sixteen components in four planes — knowledge (SUB, ORG),
brain (LOOP, BR-COUSIN, BR-DRIFT, MUT, TGT, PLT, SCORE), promotion (BIN, HEART,
HND), flywheel (HARV, PLAY, TRAIN, ROSTER) — as flat modules in
`portal/modules/security/core/`.

**Cousin model.** Five-dimension composite distance over canonical hunt
records: D1 semantic (0.30), D2 ATT&CK graph (0.20), D3 telemetry shape (0.20),
D4 behavioral sequence (0.20), D5 detection response (0.10); thresholds
τ_same 0.15 / τ_similar 0.45 / τ_new 0.70; discriminator-contradiction veto;
per-dimension decomposition mandatory; `ANOMALOUS_UNCLASSIFIED` = not
SAME/SIMILAR to any covered known ∧ detection-blind ∧ structurally deviant
from known-benign — **the product**.

**State.** SUB = new `hunt_state.py`, SQLite WAL at `PORTAL5_HUNT_DIR`
(default `/Volumes/data01/portal5_hunt/`), 15 tables, supersede-never-delete,
append-only decision log, idempotent natural keys. ORG = new `hunt_organ.py` on
existing infra (LanceDB + embed :8917 + rerank :8925) with record-level,
raw-cosine-distance, provenance-classed API; `rag_mcp` untouched.

**Boundaries.** Red directed only via MutationSpec → scenario overlay
(`_prepare_scenario`/`set_scenario` data surface); Episode sole Red→bully
contract. B/P **SPLIT**, not demolished: bench-driver shells retire;
blue_orchestrate section machinery becomes LOOP's investigation arm; telemetry
plane, grounding gates, scoreboard semantics reused.

**Council (HEART).** New `heart_council.py` on platform council mechanics
(isolation, `parse_opinion`, participation accounting); falsification-tasked
seats (≤1 per model family); deterministic materiality (evidence contradiction
∨ covering detection id ∨ benign counter-evidence); unrebutted material
objection blocks; rebuttal round; votes never promote; participation floor is
a validity floor (BL). ROSTER bounded [0.5, 2.0], advisory-only, never gates.

**Bin (BIN).** `SUSPECT → G0 evidence (observed-origin only) → G1a static
replay → G1b dynamic re-execution (capture_recipes or directed red) → G2
not-benign (verdict-contract + benign corpus zero-fire) → HEART → G3
analyst-visible (measured through the existing `siem/blue_triage.py` lane
under a queue-load corpus, priority/SLA) → PENDING_OPERATOR → PROMOTED|KILLED`.
Suspect-by-default lives at the **finding** level; `multichain.consolidate` is
already escalate-by-default and is left alone.

**Drift (BR-DRIFT).** Seeds from the existing `drift_gate.py` machinery
(rolling window, noise floor, scipy, min-baseline) retargeted to per-detection
firing baselines; four-way classification (telemetry failure / environmental /
detection degradation = weaker-late-partial firing / attacker evolution =
behavior shifted, technique persists, routed to BR-COUSIN).

**Training.** HARV role-tagged JSONL (hunter/analyst/disprover/cousin-smeller)
with objection exchanges and distance judgments; TRAIN = install `mlx-lm`
LoRA + llama.cpp GGUF convert host-native (K3 believed the whole toolchain
absent); redeploy via `models.py import-gguf`; acceptance via repositioned
bench (five arms: base / +retrieval / +playbook / +both / trained);
PENDING_MODEL_VERDICTS operator confirm; non-serve on no measured gain is an
honest success path.

**Migration.** Bridge rule: retire only when replacement is live;
honest-BLOCKED otherwise. Retires `growth_loop`/`response_loop`/
`continuous_eval` after extraction; replaces `council_agreement` in the bully
role at HRT1; keeps `multichain`; two-Episode reconciliation (truth-plane
canonical; `agentic_blue_eval` Episode documented as replay DTO).

**Important innovations.** G1a/G1b split; G3 *measured* via the discovered
`blue_triage` lane; organ provenance classes with low-authority-can't-justify-
SAME; machine-enforced `promote_policy: confirm`; per-feed measurable-change
instruments; cost-per-promoted-cousin headline series.

**Important simplifications.** Platform agent loop evaluated and **rejected**
as LOOP's base (hunt control flow is security-specific); no new MCP servers,
ports, Docker services, vector DBs, or daemons; `portal/platform/agent/*`
left alone.

## 5. O48 architecture summary (independent model)

**Central thesis.** Same thesis, but the prior design *systematically
under-credits what Portal already has*: the engagement loop, playbooks,
drift/canary, platform agent loop, model-acceptance gate, and journal are
present and wired; `episode.derive_verdict` already computes FAILED (red
landed, detection missed) deterministically; `mlx-lm>=0.31` already ships.
Verdict: `DESIGN REQUIRES REFINEMENT` — cheaper build, cleaner boundaries.

**Component model.** The same sixteen components, but with dispositions
shifted from NEW to RETROFIT/REUSE across the board.

**Cousin model.** Five axes: behavioral-sequence edit distance; ATT&CK-graph
distance (MITRE MCP :8929 + capability_graph tags); telemetry-shape distance
over `DetectionCorrelation`; detection-response distance (fired-attributed /
fired-unattributed / partial / silent — *the gap axis*); semantic (ORG
embedding — finds candidates; structured axes grade them). **NEW** = near on
ATT&CK/behavioral ∧ large detection-response distance — *"a cousin our
detection misses"* — **the product**. `ANOMALOUS_UNCLASSIFIED` = landed signal
resisting all-axis classification ("I8 unease"): full success, valued by
distance, never dropped. Detection-response movement is what separates real
novelty from arbitrary semantic distance.

**State.** SUB seeded from the investigation store (pinned to a durable path;
the `:memory:` default retires) + `capability_graph` entities persisted;
seven-memory-kinds taxonomy as a hard invariant (no agent long-term memory at
inference); `SourceAuthority` provenance; append-only + supersede; decay is a
ranking down-weight, never deletion. ORG = `rag_mcp` **retrofitted** (new
hunt-memory corpus + thin wrapper `core/org/hunt_memory.py`; retrieval
internals unchanged); `require_recall()` precondition and `index_emission()`
postcondition enforced in the tool.

**Boundaries.** Red untouched; Bully supplies scenario dicts as data
(`candidate_eval._prepare_scenario` proves the executor accepts dicts). Bench
path repositioned as the model-acceptance harness.

**Council (HEART).** Objection gate in a **new pure function beside**
`aggregate_opinions` (`council_objection.py::evaluate_with_objection_gate`),
platform primitive untouched so other council workspaces don't regress (BL);
materiality = names missing evidence or unmet condition checked in code
against evidence_refs; unrebutted material ⇒ BLOCK **regardless of votes;
otherwise the vote/quorum result stands**. `council_agreement` **refactored,
not discarded** — keep detection↔review translation + disagreement→ANOMALOUS
novelty mapping. ROSTER: retrospective weighting floored above zero;
correlation groups (shared base model) capped at a configured share of
effective weight; never override a correct minority dissent.

**Bin.** G0 has-evidence → G1 replay-reproduces (re-run the cousin against a
clean Proxmox snapshot, observe the same correlation shape; signature match
alone caps at G0) → G2 not-benign (benign corpus, BQ) → G3 analyst-visible
(Splunk notable surfaces in the real console under queue load). Only all-pass
findings reach HEART.

**Drift.** `drift_gate` engine retargeted to (technique, detection) firing
signatures; four-way disambiguation — attacker-evolution (weaker/later/partial,
sources intact), telemetry-failure (source zeroed), environmental (baseline
shift across all detections), detection-degradation (**rule/version changed —
a lineage event**); `model-canary` holds the model constant.

**Training.** `mlx_lm.lora`/`mlx_lm.fuse` **present**; the one new tool is
llama.cpp `convert_hf_to_gguf` + quantize; acceptance = `candidate_eval` +
`model-canary`; comparison arms base/+ORG/+playbook/+both/trained; training
never concurrent with a live hunt; decline-on-no-gain is honest.

**Migration.** Additive first; eight-step retirement order behind
replacements; all CLI subcommands keep working; gates green each step.
`response_loop` **KEPT as sibling** (response IR + reverse red-scenario
generation + threat intake are distinct value); `growth_loop` is the
**detection-exit proof** (fires-on-attack/quiet-on-benign/no-regression), not
the finding bin — its legs move to HND and become real.

**Important innovations.** Detection-response as the novelty arbiter; gate
beside (never inside) the platform primitive; correlation-group roster caps;
model-canary for drift attribution; seven-kinds as design invariant;
uncertainty-as-targeting signal (council dissent → TGT); detection lineage.

**Important simplifications.** Compose LOOP from `loop.py` + `platform.agent`;
retrofit rather than replace wherever wired; no second knowledge store.

## 6. SOL architecture summary (independent model)

**Central thesis.** Same product ambition, but `DESIGN REQUIRES MATERIAL
REDESIGN`: semantic distance is not cousinhood; generic RAG is not authority;
vote aggregation is not adversarial review; prompt gates are not gates;
compounding claims are not loops. Replace those with deterministic contracts
and proof requirements.

**Component model.** Same sixteen component names, implemented as one
security-owned package `portal/modules/security/core/bully/` (24 modules
including contracts, store, events, outbox, evidence, recall, signatures,
cousins, temporal, targeting, mutation, executor, promotion, adversary,
roster, plateau, handoff, harvest, playbooks, training, soc, observability).

**Cousin model.** Versioned `BehaviorSignature` (typed action/event sequence,
entity/event graph, parameter families, identity/privilege, topology/protocol/
timing, artifacts, ATT&CK mappings+version, telemetry distribution, detector
predicate outcomes, evidence manifest + completeness). Candidate generation is
a **union** (semantic top-50 ∪ ATT&CK ≤2 edges ∪ event-graph motifs ∪
scenario-family) and **candidate absence never establishes novelty**.
Structural distance `D = .30 behavior_sequence + .25 event_telemetry_graph +
.15 semantic + .15 attack_graph + .15 context_topology`; **detection response
is a separate axis** (`COVERED/NEAR_MISS/MISSED/INDETERMINATE`), never inside
`D`, so a miss cannot make an unrelated attack look like a cousin. **At least
two non-semantic relationship channels are required** before SIMILAR/NEW.
Grades: SAME ≤.10/fingerprint; SIMILAR ≤.35 + two channels + meaningful delta;
NEW .35–.60 + two channels + security-relevant delta; DIFFERENT >.60 or no
family relation; ANOMALOUS = credible anomaly without stable placement — not a
cousin until placed. **Product = `SIMILAR|NEW × NEAR_MISS|MISSED`**;
`SAME × MISSED` is a regression, high-priority but not a discovery.

**State.** SQLite WAL authoritative at
`${PORTAL_DATA_DIR}/security/defensive_bully/bully.sqlite3` (migration-managed,
FKs, closed enums, CAS coordination fields, hash-chained decision events);
evidence content-addressed in the existing capture store; LanceDB a
**rebuildable derived projection** whose rows are never legal truth inputs
until dereferenced against SQL. **Transactional outbox**: every
knowledge-bearing event appends an outbox row in the same transaction;
required dead-letters block hunt closure. **RecallReceipt** before targeting
and **DecisionImpact** records after — the compounding chain is auditable.
Trust tiers: `VALIDATED / OPERATOR_CONFIRMED / SUSPECT / IMPORTED_UNVERIFIED /
SUPERSEDED`; only high tiers change promotion priors; contradictions link and
force review, never averaged away. Retention classes AUDIT/EVIDENCE/DERIVED/
TRAINING.

**Hunt lifecycle.** SUB orchestrator is recovery-safe (lease, idempotency
keys, one external action per tick): `DRAFT → AUTHORIZED → RECALL_READY →
TARGETED → MUTATION_READY → EXECUTING → ANALYZING → PROMOTING → COMPOUNDING →
CLOSED` (+ BLOCKED/CANCELLED/FAILED). Platform agent loop used only as a
bounded **inner executor** after adding enforceable budget hooks (verified: it
lacks `max_lab_actions`).

**Bin (promotion machine).** `CREATED → EVIDENCE_READY → REPRODUCED →
CAUSALLY_VALIDATED → SOC_VISIBLE → ADVERSARIAL_CLEAR → AWAITING_OPERATOR →
PROMOTED`; terminals DISPROVED/BENIGN/BLOCKED/SUPERSEDED. Gates: G-1
authorization; G0 evidence integrity (hashes, versions, healthy telemetry;
synthetic never passes); G1 reproduction (fresh execution + clean-snapshot
replay, or 2-of-3 nondeterministic policy; behavioral **and** telemetry
artifacts); G2 causality/alternatives (matched benign/telemetry/environment
controls); G3 SOC visibility (the **Bully finding's delivery** to the
analyst-facing path within SLO under replayed queue load — producer ack
insufficient, consumer query receipt required); G4 adversarial clearance; G5
operator promotion. Changed evidence creates a new alert version and
invalidates downstream passes.

**Council (HEART).** Independent reviewer execution reused; majority
aggregation never used by the Bully. Seats are role-typed: evidence integrity,
causal/benign alternative, detection engineering, SOC consumer, safety/scope.
≥2 independent model families (or one family + human review). Materiality is
code-validated against enumerated categories. **Objections are durable
objects**: a finding cannot advance until each material objection is rebutted
with cited evidence and re-reviewed, withdrawn by its originating (or equally
independent) seat, or **explicitly waived by an authorized operator with a
reason** — the waiver is itself an audited command visible downstream.
ROSTER reliability governs eligibility/probation/additional-review only; it
**never** weights truth or suppresses an objection; it is updated only from
outcomes unavailable to the reviewer at decision time.

**Mutation.** Typed operators (ordering, technique substitution,
protocol/transport, identity/privilege, host/topology, timing, artifact,
observable behavior). `MutationPlan` declares invariants, expected deltas,
observables, matched controls, replay policy, allowed targets/tools, cleanup,
risk, approval. Code validates and compiles to Red orders; models propose but
never emit raw shell or expand scope. Operator confirms new/widened mutation
classes. Multi-dimension mutations require constituent controls (causal
isolation). Paired baseline run when environment/telemetry equivalence
unproven.

**Targeting/ROI/plateau/cost.** Hard eligibility gates (authorization,
readiness, telemetry, resource lock) precede ranking. Value uses Beta
posteriors with conservative lower bounds for low-sample neighborhoods;
correlated signals never double-multiplied; versioned pricing profile over
separately-measured quantities (lab minutes, tokens/time, analyst minutes,
replay, storage, training); **missing material cost blocks ROI claims** rather
than becoming zero. Plateau: per-neighborhood, ≥8 valid trials spanning ≥2
mutation dimensions, no promotions, <1 unique defense-response marginal gain,
upper-95% discovery-yield bound <5%; blocked/infrastructure trials excluded;
version changes reset. Deterministic tie-breaks; full candidate/exclusion
recording.

**Handoff.** Evidence-linked detection proposal (rule, tests, predicted noise,
rollout/rollback, owner, expiry); never auto-deploys; `KNOWN_COVERED` only
after deployment receipt + post-deploy Purple replay.

**Training.** Offline, isolated, exclusive resource lock; 9B-class ceiling
unless revalidated; dataset splits by cousin family/campaign/time with the
test set frozen before the harvest window; five-arm frozen evaluation;
acceptance = +5 absolute macro-F1 over arm 4 (base+retrieval+playbook) with
bootstrap 95% CI above zero and ≤2-point regressions on benign FPR,
calibration, tool reliability, known-bad recall; 30% replay-mix forgetting
control; dataset release, model promotion, rollback override are **separate
approvals**; canary + atomic alias promotion/rollback; production serving
stays Ollama; training deps never imported at runtime startup.

**Migration.** Additive, shadow-first, componentwise, reversible: feature
flags (off/shadow/authoritative); dual-write Purple Episodes; dual-run
classifications with **disagreements persisted and adjudicated as migration
evidence**; trust-conservative backfill (`IMPORTED_UNVERIFIED` unless hashes
verify); per-component cutover gates (caller inventory, shadow window,
disagreement analysis, fault/restart/idempotency proof, resource proof,
operator approval, rollback drill); no retirement while callers remain.

**Validation.** Claim-ID rigor (C1–C4, I1–I3, B1–B3, M1–M2, A1–A3, H1–H2,
T1–T2, R1–R2, F1–F2, D1, L1–L3, P1, G1, E2E); required-skip-is-failure;
zero-tolerance safety/truth/provenance failures; thresholds frozen before the
held-out final evaluation; one linked audit graph as the final proof.

## 7. Normalized comparison model

The three plans share one skeleton: sixteen named components with nearly
identical responsibilities. Terminology normalized:

| Normalized term | K3 | O48 | SOL |
|---|---|---|---|
| Persistent state | SUB (`hunt_state.py`, SQLite) | SUB (`core/substrate/`, SQLite) | SUB (orchestrator + SQLite WAL authority) |
| Semantic memory | ORG (`hunt_organ.py`, new LanceDB table) | ORG (rag_mcp retrofit + wrapper) | ORG (recall service + rebuildable LanceDB projection) |
| Hunt driver | LOOP (`hunt_loop.py`, new) | LOOP (retrofit `loop.py` + platform.agent) | LOOP (platform agent loop as bounded inner executor; SUB orchestrates) |
| Cousin engine | BR-COUSIN (5-dim composite incl. detection-response) | BR-COUSIN (5-axis composite incl. detection-response) | BR-COUSIN (5-dim structural composite; response separate) |
| Drift engine | BR-DRIFT (drift_gate machinery, retargeted) | BR-DRIFT (same + model-canary) | BR-DRIFT (matched baselines; deterministic attribution order) |
| Alert bin | BIN (G0/G1a/G1b/G2/HEART/G3) | BIN (G0–G3 then HEART) | BIN (G-1–G5 incl. causality; state machine) |
| Council | HEART (objection gate; votes telemetry-only) | HEART (gate beside aggregate; else vote stands) | HEART (durable objections; veto; operator waiver) |
| Mutation | MUT (MutationSpec → scenario overlay) | MUT (scenario-dict perturbation) | MUT (typed MutationPlan, validated/compiled) |
| Scoring | SCORE (distance-graded extension of notify_scoreboard) | SCORE (distance-weighted value; BN preserved) | SCORE (calibrated value/cost/outcome) |
| Targeting | TGT (value × penalty / cost) | TGT (risk-reduction/cost) | TGT (hard eligibility → posterior ranking) |
| Plateau | PLT (marginal discovery floor + saturation) | PLT (transition-rate/cost floor, drift engine) | PLT (statistical: ≥8 trials, 95% yield bound <5%) |
| Handoff | HND (10-part family package + regression recipe) | HND (new sibling; growth_loop legs as proof) | HND (proposal lifecycle; deploy+replay before covered) |
| Harvest | HARV (role-tagged pairs) | HARV (pairs; recall_attribution labeler) | HARV (quarantined, leakage-governed examples) |
| Playbooks | PLAY (new learned-memory module) | PLAY (retrofit playbooks.py + learning leg) | PLAY (lifecycle: draft→replay→canary→active) |
| Training | TRAIN (install toolchain; 5-arm gate) | TRAIN (mlx-lm present; +GGUF convert only) | TRAIN (offline; frozen 5-arm; +5 macro-F1; canary) |
| Roster | ROSTER (bounded advisory weights) | ROSTER (correlation-group caps) | ROSTER (eligibility/reliability only; never truth) |

Component responsibilities are functionally equivalent across plans. The real
divergence is in **dispositions** (new vs retrofit), **state machinery**
(transaction rigor), **cousin adjudication** (one-axis vs two-axis), **gate
formalism** (four prompt-described gates vs code-owned state machine), and
**council semantics** (what exactly blocks promotion).

## 8. Agreement matrix

| Design area | K3 | O48 | SOL | Agreement strength | Current-code support |
|---|---|---|---|---|---|
| Thesis: cousin discovery = product; known-bad = floor | YES | YES | YES | IDENTICAL | Supported — concept translation stands |
| ANOMALOUS_UNCLASSIFIED first-class | YES (the product) | YES (full catch, never dropped) | YES (but redefined: unplaced anomaly) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | `notify_scoreboard.py:21` (catch set); BN check |
| Red untouched; directed via scenario data | YES (MutationSpec overlay) | YES (scenario dicts) | YES (RedOrderRequest) | FUNCTIONALLY_EQUIVALENT | `exec_chain.py::_prepare_scenario:3071`, `set_scenario` |
| Episode = sole Red→bully contract | YES | YES | YES (via adapter) | IDENTICAL | `episode.py:45-74,146-183` |
| Six compounding feeds | YES (with instruments) | YES (must prove behavior change) | YES (DecisionImpact chain) | FUNCTIONALLY_EQUIVALENT | No feed closes today (all agree; verified §9) |
| Universal indexing + mandatory pre-hunt recall, code-enforced | YES | YES | YES (+ outbox/receipts) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | Nothing enforces today |
| Suspect-until-proven bin with real gates | YES | YES | YES | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | `growth_loop` gates placeholder-true (`growth_loop.py:209,215,221`) |
| Static+dynamic pairing (signature alone insufficient) | YES (G1a+G1b) | YES (G1) | YES (G1 both artifacts) | FUNCTIONALLY_EQUIVALENT | `capture_recipes.py`, `capture_store` |
| G2 not-benign via benign corpus | YES | YES | YES (inside causality gate) | FUNCTIONALLY_EQUIVALENT | `benign_corpus_bench.py`; BQ |
| G3 analyst-visible measured, not asserted | YES (blue_triage lane) | YES (notable in console) | YES (consumer-query receipt) | FUNCTIONALLY_EQUIVALENT | `siem/blue_triage.py:38-80` exists |
| Council falsifies; objection blocks | YES (gate) | YES (gate beside) | YES (veto + waiver) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | `council.py:77-96` fields exist; `aggregate_opinions:190-237` discards them |
| Platform council mechanics reused; primitive untouched | YES | YES | YES | IDENTICAL | `council.py` parse/isolation/participation |
| Participation floor = validity floor (BL) | YES | YES | YES | IDENTICAL | `council.py:196-210`; BL check |
| Roster weighting never gates truth | YES | YES | YES | IDENTICAL | NEW (no roster learning exists) |
| Two cousin surfaces (spatial + temporal) | YES | YES | YES | IDENTICAL | `drift_gate.py` seed (bench metrics today) |
| Telemetry failure ≠ behavioral drift | YES | YES | YES (explicit precedence) | FUNCTIONALLY_EQUIVALENT | NEW classification |
| Structural-validity mutation (not noise) | YES | YES | YES (typed operators) | FUNCTIONALLY_EQUIVALENT | `SCENARIOS` grammar; `exec_sequences.json` fallback_techniques (`exec_chain.py:2722`) |
| Mutation budget in code, operator dial | YES | YES | YES (+ approval for new classes) | FUNCTIONALLY_EQUIVALENT | NEW |
| Off-script emergent feed reused | YES | YES | YES (as feed) | IDENTICAL | `emergent_gaps.py:32-80` |
| Evasion-feedback channel reused | YES (MUT seed) | not named | not named | K3 ONLY (verified real) | `blue.py:2185-2214` |
| Detection-response distinguishes novelty | YES (D5 in composite) | YES (axis; arbiter of NEW) | YES (separate axis) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | `episode.py::DetectionCorrelation:80-106` |
| Anti-"embedding-astrology" control | YES (blindness + structural deviation) | YES (response axis must move) | YES (≥2 non-semantic channels) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | U1 lexical failure documented `unknown_defense.py:112-128` |
| Feature-overlap explanation layer kept | YES | YES | YES (evidence citations) | FUNCTIONALLY_EQUIVALENT | `unknown_defense.py:60-154` |
| Known-state DB steers targeting multiplicatively/posterior | YES | YES | YES (posterior adjustment) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | Nothing persists today |
| ROI pessimistic value/cost targeting | YES | YES | YES (posteriors + pricing) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | NEW |
| Plateau on discovery-rate, never cluster-stability | YES | YES | YES (statistical) | FUNCTIONALLY_EQUIVALENT | NEW |
| Cost-per-cousin tracked and must fall | YES | YES | YES (typed quantities + pricing) | FUNCTIONALLY_EQUIVALENT | NEW |
| Family-generalizing handoff, operator-confirmed | YES | YES | YES (+ deploy+replay before covered) | FUNCTIONALLY_EQUIVALENT | `spl_detections.yaml` structure; BQ/AZ lanes |
| Harvest role-tagged pairs incl. adversarial exchanges | YES | YES | YES (+ leakage governance) | FUNCTIONALLY_EQUIVALENT | `recall_attribution.py` (eval-side) |
| 5-arm training acceptance; serve only on measured gain | YES | YES | YES (+5 F1, CI, regression bounds) | FUNCTIONALLY_EQUIVALENT | `candidate_eval.py`, `intake.py:16`, `model-canary` CLI |
| Operator-confirm on all consequential promotion | YES (machine-enforced) | YES (culture) | YES (separate authenticated commands) | SAME_PRINCIPLE_DIFFERENT_IMPLEMENTATION | PROMOTE_POLICY is prose-only today (K3 verified) |
| Honest-BLOCKED over faked-green | YES | YES | YES | IDENTICAL | Pervasive in current code style |
| Label-blind production (BM); synthetic never PROVEN | YES | YES | YES | IDENTICAL | `episode.py:171-172`; BM check |
| multichain.consolidate left alone (already fail-safe) | YES | YES | YES | IDENTICAL (all three corrected the handoff) | `multichain.py:127-138,162-172` |
| Bench harness repositioned as model-acceptance gate | YES | YES | YES (as regression lanes) | FUNCTIONALLY_EQUIVALENT | `candidate_eval.py`, `intake.py` |
| Spine: design-facts-only; hunt state never enters it | YES | YES | YES | IDENTICAL | `config/spine_surfaces.yaml` |
| No new MCP servers/ports/services | YES | YES | YES (thin read surfaces only) | IDENTICAL | Rule 3/7 |
| Training on-host, offline, never concurrent with hunt | YES | YES | YES (exclusive lock) | FUNCTIONALLY_EQUIVALENT | M4 Pro 64GB envelope |
| Production serving stays Ollama | YES | YES | YES | IDENTICAL | Rule 8; `models.py:218-259` |

**Reading of the matrix:** the sixteen-component skeleton, the invariants, and
the six-feed compounding ambition are IDENTICAL or FUNCTIONALLY_EQUIVALENT
across all three plans. Every one of those shared positions was spot-checked
against code and holds. The disagreements are all in *how* — and those are
where the design work lives.

## 9. Disagreement register

Thirty meaningful disagreements were registered and traced. "Verified" anchors
were read by this reviewer at HEAD `47d3e884`.

| ID | Topic | K3 position | O48 position | SOL position | Why they differ | Evidence needed |
|---|---|---|---|---|---|---|
| D-001 | Training toolchain presence | No training deps in pyproject; install mlx-lm + llama.cpp | `mlx-lm>=0.31` already a dep; only llama.cpp GGUF convert missing | Select/pin toolchain after a spike | Different pyproject reads | pyproject.toml |
| D-002 | Embedding service identity | CPU-pinned sentence-transformers harrier-oss (:8917) | MLX mxbai (:8917) | Existing configured service | Env names say "MLX" | scripts/embedding-server.py |
| D-003 | multichain default | Escalate-by-default (verified) | Escalate-by-default (verified) | "Clear-by-default" claim stale | All correct the handoff | multichain.py:110-218 |
| D-004 | ANOMALOUS vs CONFIRMED semantics | Full catch "equal to CONFIRMED" | Ordinal ranks ANOMALOUS *below* CONFIRMED; handoff imprecise | (uses response axis instead) | Two axes in scoreboard conflated | notify_scoreboard.py:21-37 + BN check |
| D-005 | EvidenceStore/CaseNotebook | In-memory / :memory:, no prod callers | PARTIALLY_WIRED, pin durable | In-memory; replace as authority | Minor framing only | evidence.py:111-119, case_notebook.py:53 |
| D-006 | LOOP disposition | NEW hunt_loop.py; platform loop rejected | RETROFIT loop.py + compose platform.agent | Platform loop as bounded inner executor + security orchestrator | Three different loop philosophies | loop.py, platform/agent/loop.py |
| D-007 | ORG disposition | NEW module on shared infra; rag_mcp untouched | RETROFIT rag_mcp (new corpus + wrapper) | Security-owned projection; share endpoints not tables | What "reuse rag_mcp" means | rag_mcp.py:60-112,216-310,412-464 |
| D-008 | growth_loop disposition | Extract shapes → BIN/HND, retire | It's the *detection-exit* proof → HND; legs made real | Placeholder proof never satisfies gates; replace | What growth_loop *is* | growth_loop.py:120-224 |
| D-009 | response_loop disposition | Extract primitives → retire | KEEP-SIBLING (3 distinct functions) | Adapt contracts; retain till callers mapped | Value assessment differs | response_loop.py:1-115 |
| D-010 | council_agreement disposition | REPLACE in bully role at HRT1 | RETROFIT (keep translation + novelty map) | Legacy stays; Bully never uses it | Scope of replacement | council_agreement.py:44-66 |
| D-011 | HEART gate placement & votes | New security-core module; votes telemetry-only | Gate beside aggregate_opinions; else vote stands | New adversary module; vote never clears | Placement + residual role of votes | council.py:190-237 |
| D-012 | NEW vs ANOMALOUS definitions | NEW = distance band; ANOMALOUS = uncovered+blind+deviant = product | NEW = near + detection-response large = product; ANOMALOUS = unclassifiable | Relationship × response axes; product = SIMILAR\|NEW × NEAR_MISS\|MISSED; ANOMALOUS = unplaced | Three different grade-space semantics | Design analysis (§10) |
| D-013 | Detection-response in distance? | Yes (D5, w=0.10) | Yes (axis in composite) | NO — separate axis (a miss must not fake relatedness) | Conflation risk assessment | DetectionCorrelation fields |
| D-014 | Gate set & ordering | G0→G1a→G1b→G2→HEART→G3→operator | G0→G1→G2→G3→HEART→operator | G-1→G0→G1→G2(causality)→G3(SOC)→G4(council)→G5(operator) | Cost ordering + gate inventory | Design analysis (§13) |
| D-015 | SOC visibility semantics | Triage-lane report ≤P2 in SLA under queue load | Notable surfaces in console | Consumer-query receipt of the *Bully finding* (not the missed detector) | Precision of what is proven | blue_triage.py |
| D-016 | SUB location/convention | PORTAL5_HUNT_DIR → /Volumes/data01/portal5_hunt/ | configured state dir | ${PORTAL_DATA_DIR}/security/defensive_bully/ | Env-convention choice | .env.example; PORTAL5_LANCE_DIR precedent |
| D-017 | Transactional indexing | Universal indexing invariant (unindexed = failed iteration) | require_recall/index_emission enforced | Outbox + dead-letter blocks closure + receipts + impact records | Enforcement mechanism depth | Feasibility vs SQLite/LanceDB |
| D-018 | Drift class semantics | DEGRADATION = weaker/later/partial; EVOLUTION = behavior shifted | DEGRADATION = rule changed (lineage); EVOLUTION = weaker/later/partial | Deterministic attribution order; 5 causes incl. UNCLASSIFIED | Class boundary definitions | Design analysis (§15) |
| D-019 | Plateau rule | Rate floor + patience + saturation ceiling | Transition-rate/cost floor via drift engine | ≥8 valid trials, ≥2 dims, 95% yield bound <5%, resets | Statistical rigor | Design analysis |
| D-020 | Cost model | Tokens/wall/lab/operator-minutes; unit costs | Compute + lab-hours + analyst-effort | Typed quantities + versioned pricing; missing cost blocks ROI | Rigor of measurement | Design analysis |
| D-021 | Training acceptance | 5 arms; cousin bench; intake floors; PENDING_VERDICTS | candidate_eval + canary; arms; decline on no gain | Frozen 5-arm; +5 macro-F1 CI>0; ≤2pt regressions; 30% replay | Statistical acceptance bar | candidate_eval.py, intake.py |
| D-022 | PLAY disposition | New playbook_memory.py (static YAMLs stay red-side) | Retrofit playbooks.py + learning leg | Full lifecycle (draft→replay→canary→active→retired) | Reuse depth | playbooks.py:34-60 |
| D-023 | ROSTER model | ≤1 seat/family; weights [0.5,2.0] advisory-only | Correlation-group caps; floor above zero | Eligibility/reliability only; never weights; only post-hoc outcomes | How much weighting is safe | Design analysis |
| D-024 | Migration approach | Bridge rule; retire-when-replacement-live | Additive-first; 8-step order | Shadow/dual-run/feature-flags + cutover gates | Migration formality | Design analysis |
| D-025 | Spine coverage of new code | Flat modules → zero new units (globs cover) | Same assumption | Nested package NOT covered — add deliberate surface | Glob semantics | spine_surfaces.yaml:360-376 |
| D-026 | Package layout | 17 flat modules in core/ | Sub-packages (substrate/, cousin/, bin/…) | One core/bully/ package | Layout preference | core/ has 70 files + subpackages |
| D-027 | Verdict severity | REFINEMENT | REFINEMENT | MATERIAL REDESIGN | What counts as "the design" | Synthesis: WHAT stands; HOW materially corrected |
| D-028 | ATT&CK graph source | spl_detections.yaml sibling_ids + tactics | MITRE MCP :8929 + capability_graph | ATT&CK mappings w/ source/version | Data source choice | spl_detections.yaml (11 sibling_ids); mitre MCP live |
| D-029 | PROMOTE_POLICY enforcement | Machine-readable hunt config (prose-only today — verified) | Pervasive culture; config dials | Separate authenticated commands per action | Enforcement mechanism | grep: only .md mentions |
| D-030 | Two Episode shapes | Truth-plane canonical; agentic Episode = replay DTO (comment-level) | Treats both as Episode producers | EpisodeReference adapter | Reconciliation approach | agentic_blue_eval.py:82-91 (second dataclass confirmed) |

## 10. Repository verification of disagreements

Format per the task contract. Each was resolved by reading the cited code.

### D-001 — training toolchain

DISAGREEMENT: K3: no training deps exist. O48: mlx-lm present, only GGUF
convert missing. SOL: verify at build time.

CURRENT PORTAL FACTS:
- `pyproject.toml:78` — `"mlx-lm>=0.31"` is a hard dependency (comment at
  :75-76 ties it to the MLX dual-server era); `uv.lock` pins mlx_lm 0.31.3.
- `mlx-lm` ships `mlx_lm.lora` (LoRA train) and `mlx_lm.fuse` (adapter fuse).
- No llama.cpp `convert_hf_to_gguf`/quantize anywhere in the repo; no
  training *pipeline* (no dataset code, no train orchestration) exists.
- `portal/platform/inference/cli/models.py:218-259` — `import-gguf` (tempfile
  Modelfile + `ollama create`) exists. `candidate_eval.py` + `drift_cli.py`
  `model-canary` exist.

WHAT EACH GOT RIGHT: O48 — the dependency fact. K3 — the *pipeline* absence.
WHAT EACH MISSED: K3 — the pyproject entry (its "VERIFIED FACT" was wrong on
this point). O48 — nothing material.
FINAL CONCLUSION: Adopt O48's fact pattern with K3's caution: LoRA/fuse tools
ship with the environment (verify at TRAIN phase); llama.cpp GGUF convert is
the one tool to install (host-native); the training *orchestration* is
genuinely new. The TRAIN phase owns toolchain verification, not discovery.
CONFIDENCE: HIGH.

### D-002 — embedding service

CURRENT PORTAL FACTS: `scripts/embedding-server.py:37,46-51` —
sentence-transformers `microsoft/harrier-oss-v1-0.6b`, `device="cpu"`
deliberately (MPS not thread-safe). `rag_mcp.py:36` reads
`MLX_EMBEDDING_URL` (default :8917) — the env var name says MLX; the service
is CPU sentence-transformers. Reranker :8925 is MLX
(`reranker_mcp.py:30` Qwen3-Reranker-0.6B-mxfp8).
CONCLUSION: **K3 right**, O48 wrong on identity. Design consequence: ORG must
batch-embed (CPU service) and must never treat rerank scores as distance.
CONFIDENCE: HIGH.

### D-003/D-004 — consolidation + scoreboard

CURRENT PORTAL FACTS: `multichain.py:127-138` (no concluder → ESCALATE/
ANOMALOUS_UNCLASSIFIED), `:162-172` (DISMISS requires unanimous RULED_OUT ∧
zero signal), `:155-161,178-179` (unnamed anomaly forces escalation).
`notify_scoreboard.py:21` `NOTIFY_VERDICTS = {CONFIRMED,
ANOMALOUS_UNCLASSIFIED}`; `:32-37` trust ordinal CONFIRMED_CORRECT(3) >
HONEST_ANOMALY(2) > SILENCE(1) > WRONG(0), ordinal-only. BN check
(`blue_orchestration.py:1289-1348`) asserts both: anomaly is an Axis-1 catch
∧ confirmed-correct > honest-anomaly > confirmed-wrong.
CONCLUSION: All three right on multichain (handoff stale). On the scoreboard,
K3 and O48 each caught half: **catch-set equality** (Axis 1) and **trust
ordinal below confirmed-correct** are both true. FINAL DESIGN DECISION:
SCORE keeps BN's catch/trust semantics untouched and adds a *separate*
discovery-value axis where a far NEW cousin can out-value a known-bad catch —
the two axes are never conflated (this is where both plans' phrasing was
imprecise). CONFIDENCE: HIGH.

### D-005 — investigation stores

CURRENT PORTAL FACTS: `evidence.py:111-119` EvidenceStore in-memory dict,
docstring "In-memory evidence store for one investigation case";
`case_notebook.py:53` `:memory:` default, real `supersede()` at :162; the
seven-memory-kinds doctrine at `case_notebook.py:1-17` (kind 7: agent
long-term memory NOT PERMITTED at inference).
CONCLUSION: All three right. SUB is NEW; what transfers is the EvidenceRecord
schema, SourceAuthority hierarchy, the SQLite+supersede pattern, and the
seven-kinds doctrine. CONFIDENCE: HIGH.

### D-006 — LOOP disposition

CURRENT PORTAL FACTS:
- `loop.py:176-216` `run_engagement` — playbook-driven
  perceive/decide/act/verify/learn with hard caps, checkpoint/resume, notify
  with resume command. **But** its journal recall (`:205-211`) feeds only
  `len(prior)` into reports (`:452,471`) — the recalled *content* never
  changes a decision (K3's sharper finding, verified).
- `portal/platform/agent/loop.py:30-89` `run_loop` — generic bounded
  decide/execute/fold; enforces only `max_iterations` + `max_wall_clock_sec`
  from `goal.budget` (:52-53). **No `max_lab_actions`** — SOL's verified gap.
- The hunt iteration (recall → select → direct-red → episode → grade → gates
  → council → record → plateau) is a fixed, stage-transactional pipeline, not
  a generic decide-execute-fold search.

WHAT EACH GOT RIGHT: K3 — the hunt loop is security-specific; platform loop
rejected as base; journal recall is not behavior-changing. O48 — loop.py's
discipline (caps, checkpoint, notify) is worth carrying; playbooks machinery
is real. SOL — budget enforcement must live in the security orchestrator; a
recovery-safe stage machine with leases/idempotency is required.
WHAT EACH MISSED: K3 — undervalued loop.py's operational discipline. O48 —
over-credited loop.py's "learn" leg (it doesn't change behavior) and
platform.agent's fit. SOL — under-acknowledged that the investigation arm
(blue_orchestrate sections) is the natural per-iteration engine.
FINAL CONCLUSION (**NEW SYNTHESIS**): LOOP is a NEW security-owned
orchestrator (`hunt_loop.py`) implementing the stage pipeline with SUB-
transactional state (SOL), carrying loop.py's discipline — hard caps
including `max_lab_actions`, checkpoint/resume, notify-with-resume-cmd via the
existing dispatcher (O48) — and reusing blue_orchestrate's section runners as
the per-Episode investigation arm over `spl_backend.query_episode` (K3).
Platform `run_loop` is not the base (K3's rejection upheld); `loop.py` stays
as the red-side engagement runner, untouched. CONFIDENCE: HIGH.

### D-007 — ORG disposition

CURRENT PORTAL FACTS (all read): `rag_mcp.py:60-80` schema is chunk-oriented
(chunk_id/kb_id/source_file/chunk_index/text/vector/char_start/char_end);
`kb_ingest` (:216-310) ingests *directories* of doc files; `kb_search`
(:412-464) returns `rerank_score` only — **no vector distance, no
metadata-filtered record API, no record-level upsert**.
CONCLUSION: **K3 and SOL right.** O48's "retrofit rag_mcp, retrieval internals
unchanged" cannot yield raw distances or record-level filtering without
bypassing the MCP API — at which point it is a new security-side module
sharing infra, which is what K3/SOL specify. FINAL: ORG = security-owned
module (`hunt_organ`) owning a `hunt_memory` LanceDB table/projection on the
same infra (LanceDB dir, :8917 embed, :8925 rerank); rag_mcp untouched
(Rule 3). CONFIDENCE: HIGH.

### D-008/D-009 — growth_loop + response_loop

CURRENT PORTAL FACTS: `growth_loop.py:120-224` — ProofResult's three legs are
placeholder-true (:209,215,221) AND the legs are semantically *detection-exit*
proofs (fires-on-fresh-attack / quiet-on-benign / no-regression) — both
readings verified. `response_loop.py:1-13,53-104` — three distinct functions:
response IR playbook drafting (RESPONSE_PRIMITIVES + technique map), reverse
red-scenario generation (blue→red), threat intake (CVE→gaps). Test-only
callers for both.
CONCLUSION: O48's reading is the precise one: growth_loop's legs are the
HND *detection* proof made real (not the finding bin); response_loop carries
distinct keepable value. K3's extract-then-retire would lose reverse-gen and
intake. FINAL: growth_loop's shapes + `validate_spl_syntax` extracted into
BIN/HND, its legs made real inside HND, module retires when HND is live and
tests are ported (K3's retirement + O48's mapping). `response_loop` is
**KEPT-SIBLING** (O48): its reverse-gen seeds MUT, its primitives seed HND's
IR section, its intake seeds the future external-cadence extension; it is not
in the Bully's authoritative path. CONFIDENCE: HIGH.

### D-010/D-011 — council_agreement + HEART placement

CURRENT PORTAL FACTS: `council_agreement.py:44-66` — `_platform_opinions`
builds bare SUPPORT/REJECT/ABSTAIN opinions and **never populates**
`strongest_objection`/`missing_evidence`/`conditions_to_change` (K3's sharpest
finding, verified). Its translation + disagreement→ANOMALOUS mapping
(:159-167) and zero-participation fail-safe (:89-102) are real value.
`council.py:190-237` — `aggregate_opinions` counts votes over the full roster,
never reads objections; isolation/parse/participation mechanics are solid and
production-wired (`router/handlers.py`).
CONCLUSION: HEART is NEW code in the security bully package reusing platform
council *execution/parse/participation* mechanics with its own objection-gated
aggregation (K3+SOL over O48 on placement — a security-specific gate does not
belong in the platform router dir). Votes are recorded as telemetry; the
promotion condition is the **absence of an unrebutted material objection**
(K3+SOL over O48's "otherwise the vote stands" — a vote-quorum pass is not
falsification). `council_agreement` and `multichain` are **LEFT ALONE** on the
legacy bench lane (SOL's compatibility framing) — no refactor, no retirement
obligation; HEART does not route through them. BO/BL/BE/BP checks keep
passing untouched. CONFIDENCE: HIGH.

### D-012/D-013 — the cousin model (deepest disagreement)

CURRENT PORTAL FACTS:
- Available structured data per Episode: `DetectionCorrelation`
  (has_detection_rule, has_spl_hit, row_count, within_window, target_match,
  source, evidence_refs — `episode.py:80-106`); red_order step sequence
  (`exec_chain.py::SCENARIOS`); telemetry field signatures via
  `spl_backend.query_episode` (`:161-205`, label-blind, episode-scoped);
  `spl_detections.yaml` discriminator_tokens + sibling_ids (11 sibling links)
  + spl_variants.
- U1's documented failure: lexical containment scored a real variant 0.09
  (`unknown_defense.py:112-128`) — pure text similarity silently zeroes out.
- The concept's product definition: "ANOMALOUS_UNCLASSIFIED — cousin-of-X but
  not X, and nothing catches it — is the primary product" (all three inherit
  this), and BN makes ANOMALOUS a first-class catch.

WHAT EACH GOT RIGHT: K3 — per-dimension decomposition + discriminator veto +
the uncovered-blind-deviant ANOMALOUS definition. O48 — detection-response as
the novelty arbiter; "semantic finds, structure grades". SOL — the two-axis
separation (a miss must not manufacture relatedness), ≥2 non-semantic
channels, candidate-absence-≠-novelty, `SAME×MISSED` = regression.
WHAT EACH MISSED: K3 — putting detection-response *inside* D lets a detection
gap inflate cousin distance (SOL's critique lands). O48 — same conflation;
and its NEW/ANOMALOUS boundary strands the concept's product semantics. SOL —
underweights that the *concept's* ANOMALOUS is itself a product band, not just
an unplaced residue.
FINAL CONCLUSION (**NEW SYNTHESIS**, the strongest fourth option): a two-axis
model — structural relationship D over five dims (behavior .30 /
telemetry-event-graph .25 / semantic .15 / ATT&CK .15 / context-topology .15;
SOL weights, K3's band discipline) with vetoes (discriminator contradiction;
≥2 non-semantic channels required) — crossed with an independent
defense-response axis (`COVERED/NEAR_MISS/MISSED/INDETERMINATE`, derived in
code from DetectionCorrelation + Episode). Product bands: `SIMILAR|NEW ×
NEAR_MISS|MISSED` plus `ANOMALOUS × blind` (the concept's product, first-class,
BN-safe); `SAME × MISSED` = detection regression (high-priority, not a
discovery). Full derivation in the DECISION LEDGER (DEC-02) and DESIGN §10.
CONFIDENCE: HIGH.

### D-014/D-015 — bin gates + SOC visibility

CURRENT PORTAL FACTS: `capture_store`/`capture_recipes.py` (deterministic
re-execution with success markers) exist; `blue_triage.py` (Splunk poll →
pipeline enrich → P1–P4 report) exists; `telemetry.py:26-37`
OBSERVED_EVIDENCE_ORIGINS exists; `blue_orchestrate.py:91-103`
`_VERDICT_GROUNDING_POLICY` (dual-use counter-evidence) exists;
`benign_corpus_bench.py` exists; BQ check governs alert fatigue.
CONCLUSION: Gate set = SOL's inventory (authorization G-1, evidence G0,
reproduction G1, causality/not-benign G2, council G4, SOC G3, operator G5)
with K3's G1a/G1b split inside G1 and K3's **ordering** — adversarial council
before the SOC lane (a candidate the council kills must never consume
analyst-visible surface; BQ discipline) — and K3's G3 measurement
(blue_triage lane under a queue-load corpus) with SOL's delivery-receipt
semantics (consumer-query proof of the *Bully finding's* delivery, not the
missed detector's firing). CONFIDENCE: HIGH.

### D-016/D-017 — substrate location + transactional indexing

CURRENT PORTAL FACTS: `PORTAL5_LANCE_DIR` (default
`/Volumes/data01/portal5_lance`) is the existing out-of-repo data-dir
convention (`rag_mcp.py:33`, `memory_mcp.py:27`, docker-compose :827). No
`PORTAL_DATA_DIR`/`PORTAL5_HUNT_DIR` exists. SQLite WAL is used by
case_notebook already; LanceDB time-travel exists in rag_mcp.
CONCLUSION: `PORTAL5_HUNT_DIR` (K3's name, following the existing
`PORTAL5_LANCE_DIR` convention; default `/Volumes/data01/portal5_hunt/`) over
SOL's `${PORTAL_DATA_DIR}` invention. SOL's authority/projection split,
content-addressed evidence, **transactional outbox with closure-blocking dead
letters, RecallReceipt, and DecisionImpact records** are adopted wholesale —
they are the mechanism that turns "universal indexing" from an assertion into
an auditable guarantee (K3's invariant gets SOL's machinery). CONFIDENCE:
HIGH.

### D-018/D-019/D-020 — drift classes, plateau, cost

CURRENT PORTAL FACTS: `drift_gate.py:35-51` (TRACKED_METRICS over bench
results, NOISE_FLOOR 0.03, MIN_BASELINE_RUNS 3, DEFAULT_WINDOW 7, scipy,
canary; flags-never-verdicts). It measures bench/model drift, not detection
behavior — all three agree; the machinery seeds BR-DRIFT.
CONCLUSION: Drift classes adopt SOL's deterministic attribution order
(telemetry → environment → attacker-evolution → detection-degradation →
UNCLASSIFIED) with corrected class semantics: DETECTION_DEGRADATION = rule
edit/version change or weaker firing with a stable attack signature (O48's
lineage framing + K3's tuning lead); ATTACKER_EVOLUTION = behavior/fields
shifted while the technique persists (K3+SOL) — routed to BR-COUSIN as a
temporal cousin. O48's model-canary model-constancy control adopted. Plateau
adopts SOL's statistical rule (≥8 valid trials, ≥2 mutation dims, no
promotion, <1 unique response-state gain, 95% yield upper bound <5%,
blocked-trials excluded, version-change resets) with K3's known-state
saturation as a recorded secondary signal. Cost adopts SOL's typed quantities
+ versioned pricing profile + missing-cost-blocks-ROI, with K3's
cost-per-promoted-cousin headline series. CONFIDENCE: HIGH.

### D-021–D-023 — training acceptance, PLAY, ROSTER

CURRENT PORTAL FACTS: `candidate_eval.py` (delta-vs-incumbent), `intake.py:16`
(TPS_FLOOR=20), `model-canary` CLI, PENDING_MODEL_VERDICTS flow all exist.
`playbooks.py:34-60` (authored YAML with scope/budget/stop validation incl.
`max_lab_actions`) wired into loop.py.
CONCLUSION: Training acceptance = SOL's statistical bar (frozen 5-arm suite,
+5 macro-F1 with 95% CI > 0 over base+retrieval+playbook, ≤2pt regression
bounds, 30% replay mix, family/campaign/time splits, frozen test set,
exclusive lock, 9B-class ceiling, separate approvals, canary + atomic alias
rollback) + K3's role-tagged corpus and cousin-judgment bench +
PENDING_MODEL_VERDICTS integration. PLAY = learned per-scenario-class records
in SUB (K3) with SOL's lifecycle (DRAFT→REPLAY_VALIDATED→CANARY→
AWAITING_OPERATOR→ACTIVE→RETIRED, auto-revert) and playbooks.py's
container/validation pattern (O48); static red-side YAMLs untouched. ROSTER =
SOL's eligibility/reliability-only model (never weights truth; updated only
from outcomes unavailable at decision time) + family/correlation-group
diversity caps (K3's ≤1-per-family ≈ O48's group caps; adopt as
config-enforced diversity) + K3's bounded advisory weight used only for
seat-selection *order*. CONFIDENCE: HIGH.

### D-024–D-027 — migration, spine, layout, verdict severity

CURRENT PORTAL FACTS: `config/spine_surfaces.yaml:360-376` — sec-core globs
are `core/*.py` + `core/commands/*.py` (non-recursive); siem/ and
investigation/ subpackages have their own surface entries. core/ has 70 flat
`.py` files.
CONCLUSION: SOL is right that a nested package needs a deliberate surface
entry; K3 is right that flat modules cost zero. **FINAL:** one
`portal/modules/security/core/bully/` package (SOL's layout — 17-24 new
modules do not belong as flat clutter in a 70-file directory) + one new
three-line surface entry (`unit-surface-sec-bully`, precedent:
unit-surface-siem/-investigation). Migration adopts SOL's shadow-first
framework (feature flags off/shadow/authoritative; dual-write; dual-run with
disagreement adjudication; trust-conservative backfill; per-component cutover
gates) + K3's bridge rule (retire only when replacement is live;
honest-BLOCKED) + O48's compatibility guarantees (all CLI keeps working).
Verdict severity (D-027): the honest reading is — the prior program's WHAT
(thesis, components, invariants, feeds) stands (K3/O48 right); the HOW
(state machinery, cousin adjudication, gate formalism, council semantics)
required material correction (SOL right). The final package is therefore a
synthesis, not a base-plus-patches. CONFIDENCE: HIGH.

### D-028–D-030 — ATT&CK source, promote-policy, two Episodes

CURRENT PORTAL FACTS: `spl_detections.yaml` carries sibling_ids (11 links) +
discriminator_tokens + spl_variants; MITRE MCP :8929 is live (used by this
reviewer). PROMOTE_POLICY appears only in prose (grep: config/*.md docs only).
`agentic_blue_eval.py:82-91` defines a second Episode dataclass (replay DTO).
CONCLUSION: ATT&CK graph distance uses spl_detections sibling_ids + tactic
structure as the deterministic primary source, MITRE MCP as enrichment (K3
primary + O48 enrichment). PROMOTE_POLICY becomes machine-readable
(`promote_policy: confirm` in hunt config) with queue actor checks (K3) and
separate authenticated operator commands per consequential action (SOL).
Two-Episode reconciliation per K3 (truth-plane `episode.py::Episode`
canonical; agentic Episode documented as "capture replay DTO",
comment-level). CONFIDENCE: HIGH.

## 11. Shared assumptions found incorrect

Places where **all three plans agreed with each other (or with the prior
handoff) and the code says otherwise**, plus lone-plan claims the code
refutes:

1. **(Prior handoff, corrected by ALL THREE)** "`multichain.consolidate` is
   clear-by-default" — false; it is escalate-by-default
   (`multichain.py:127-138,162-172`). No consolidation surgery; suspect-by-
   default lands at the finding level.
2. **(Prior handoff, corrected by ALL THREE)** "EvidenceStore/CaseNotebook are
   the seed of persistent state" — both are memory-resident
   (`evidence.py:111-119`, `case_notebook.py:53`). SUB is new; only schema +
   pattern transfer.
3. **(Prior design, corrected by ALL THREE)** "BR-DRIFT is NEW" —
   `drift_gate.py` machinery exists and seeds the temporal engine.
4. **(K3 lone claim, refuted)** "No training deps in pyproject" —
   `mlx-lm>=0.31` is a dependency (`pyproject.toml:78`). The *pipeline* is
   absent; the *tools* ship.
5. **(O48 lone claim, refuted)** ":8917 is MLX mxbai" — it is CPU-pinned
   sentence-transformers harrier-oss (`scripts/embedding-server.py:37-51`);
   only the :8925 reranker is MLX.
6. **(K3+O48 partial imprecision, corrected)** "ANOMALOUS == CONFIRMED" /
   "ANOMALOUS below CONFIRMED" — code has both a catch-set equality (Axis 1)
   and a trust ordinal (confirmed-correct > honest-anomaly). The final SCORE
   keeps both intact and adds a separate discovery-value axis.
7. **(Prior design, corrected by K3+SOL)** "ORG = retrofit rag_mcp" — rag_mcp
   is directory-ingest, rerank-score-returning, chunk-schema'd; ORG is a new
   security-owned module/projection on shared infra.
8. **(O48 partial, corrected)** "field_journal learn leg is wired" — wired,
   but the recalled content never changes a decision (`loop.py:452,471` use
   `len(prior)` only); the one behavior-changing read is
   `capability/index.py::_journal_prior_score:189-199`.
9. **(K3+O48 partial, corrected by SOL)** "New security-core modules cost zero
   spine units" — true only for flat `core/*.py` placement; a nested package
   needs one deliberate surface entry (`spine_surfaces.yaml:360-376`).
10. **(All three, confirmed true)** Platform council carries objection fields
    but `aggregate_opinions` discards them; the security adapter never even
    populates them (`council_agreement.py:44-66`).

## 12. Minority insights that proved important

Insights held by exactly one plan that verification or analysis proved
load-bearing for the final design:

- **SOL:** transactional outbox + recall receipts + decision-impact records —
  the only mechanism in any plan that makes "compounding" *auditable* rather
  than asserted. Adopted as the feed-proof backbone.
- **SOL:** two-axis cousin model (relationship × response) — resolved the
  deepest disagreement (D-012/013) and exposed the conflation in both other
  plans.
- **SOL:** durable objection objects + operator waiver as an audited command;
  causality as its own gate; authorization as a pre-creation gate;
  shadow/dual-run migration; statistical plateau; missing-cost-blocks-ROI;
  leakage-safe dataset construction; nested-package spine gap. All adopted.
- **O48:** `mlx-lm` already present (corrected K3); growth_loop's legs are the
  *detection-exit* proof (→ HND); response_loop keep-sibling; model-canary
  holds the model constant during drift attribution; correlation-group roster
  caps; uncertainty-as-targeting signal. All adopted.
- **K3:** `blue_triage` lane as the G3 measurement asset (the only plan that
  found it); evasion-feedback channel as a MUT seed; G1a/G1b static/dynamic
  split; council-before-SOC gate ordering (BQ discipline); per-feed measurable
  instruments; machine-enforced promote_policy; two-Episode reconciliation;
  `PORTAL5_HUNT_DIR` convention. All adopted.

## 13. Improvements derived from disagreement

Things none of the three plans fully captured that the comparison itself
exposed (NEW SYNTHESIS):

1. **Catch/trust/discovery tri-axial scoring.** The BN check's two semantics
   (catch-set; trust ordinal) plus the plans' discovery-value ambition are
   three different axes that both K3 and O48 partially conflated. Final SCORE
   keeps all three separate (D-004 resolution).
2. **The cousin product is a 2-D band, not a grade.** The concept's
   "ANOMALOUS is the product" and O48's "NEW is the product" reconcile into
   `relationship × response` product bands, which also yields the
   `SAME×MISSED` regression case for free (DEC-02).
3. **Gate ordering is a BQ (alert-fatigue) decision, not just a cost
   decision.** Council-before-SOC means unvetted candidates never touch the
   analyst-visible surface — neither K3 nor SOL stated this rationale
   explicitly; it follows from holding BQ green.
4. **The hunt loop's enforcement surface is exactly the gap list of the two
   existing loops**: loop.py lacks behavior-changing recall; platform run_loop
   lacks lab-action budgets. The new orchestrator is precisely their union
   plus SUB transactions (D-006 synthesis).
5. **Migration needs both a bridge rule AND shadow evidence.** K3's
   retire-when-live and SOL's dual-run are complementary: dual-run
   *disagreements* are the evidence that justifies each retirement (adopted
   jointly).

## 14. Capabilities all three missed

Checked per Phase 20; only justified additions:

1. **Hunt/bench contention guard.** The repository shows a continuously
   running nightly bench supervisor (this worktree's dirty artifacts are its
   output). None of the plans address scheduling hunts around the bench
   supervisor's lab/backend usage. Final design: LOOP's admission control
   (SOL) includes an active-bench/engagement lock check before lab actions —
   an operational requirement, not a feature. (Basis: NEW SYNTHESIS from
   observing runtime state + SOL's admission control.)
2. **Promotion-queue notifications.** Only K3 specified notify-on-queue-
   arrival via the existing dispatcher (I-20). Adopted.
3. **Config snapshot per hunt.** Only SOL required snapshotting effective
   non-secret config per hunt. Adopted (provenance completeness).
4. **Emergency stop.** SOL's kill-switch (revoke leases) + K3's config-flag
   halt of new Red direction — complementary; both adopted.
5. **No plan missed a component** — the sixteen-component skeleton is
   complete; what was missing was machinery depth, which the synthesis adds.

Evaluated and **rejected** as additions (no demonstrated value now):
behavioral-graph/causal-event DBs, active-learning toolchains, new vector
DBs, experiment trackers, daemon scheduler (documented future extension),
shadow/canary *deployment* infrastructure beyond the existing model-canary
analogue (K3's rejection list, concurred).

## 15. Final synthesis verdict

- **All three plans independently converged on the same product, the same
  sixteen components, the same invariants, and the same six feeds.** That
  convergence is strong evidence the prior program's *architecture skeleton*
  is right. Verified: current code supports every shared position.
- **The disagreements were all in machinery depth**, and tracing them against
  the code produced a design stronger than any single plan: SOL's
  transactional state + two-axis cousin model + gate/council formalism; K3's
  asset discoveries and operational precision (triage lane, evasion channel,
  gate ordering, feed instruments); O48's disposition corrections (mlx-lm,
  growth_loop, response_loop, model-canary, correlation caps) and
  reuse-first costing.
- **No plan is the base.** The final package is a synthesis: K3's component
  map and operational flow, SOL's state/proof machinery, O48's dispositions
  and cost realism, plus five new-synthesis improvements (§13) and two
  beyond-all-three operational additions (§14).
- **Verdict on the prior build program:** REFINEMENT of the WHAT, MATERIAL
  correction of the HOW — implemented by the final package that follows.

The resulting authoritative artifacts: `FINAL_DESIGN_DEFENSIVE_BULLY.md`
(what), `FINAL_ARCHITECTURE_/INTERFACES_/DATA_MODEL_` (contracts),
`FINAL_MIGRATION_` (transition), `FINAL_VALIDATION_` (proof),
`FINAL_BUILD_PROGRAM_` (sequence), `FINAL_DECISION_LEDGER_` (why).

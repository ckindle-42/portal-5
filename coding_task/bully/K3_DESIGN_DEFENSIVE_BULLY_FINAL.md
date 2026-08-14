# DESIGN — Defensive Bully (FINAL)

**Status: authoritative definition of WHAT is being built.** Reviewed against
HEAD `47d3e884` (see `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` for evidence).
This document is standalone: a fresh coding agent must be able to build the
complete system from this package without the original conversation.

Authority order among package documents: this file (WHAT) →
`ARCHITECTURE_DEFENSIVE_BULLY.md`, `INTERFACES_DEFENSIVE_BULLY.md`,
`DATA_MODEL_DEFENSIVE_BULLY.md` (contracts) → `MIGRATION_DEFENSIVE_BULLY.md`
(transition) → `VALIDATION_DEFENSIVE_BULLY.md` (proof) →
`IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY.md` (build constraints) →
`HANDOFF_DEFENSIVE_BULLY_FINAL.md` (orientation) →
`REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` (rationale).

---

## 1. Thesis

Modern offense hunts the *shape* of a weakness and chases everything
structurally adjacent to it — cousins. The Defensive Bully is the mirror:
**given everything Portal knows, surface the cousins it doesn't** — the
near-neighbor attack one valid mutation from a covered one that existing
detections do not catch — and alarm on it, graded by distance from known.

- Known-bad detection is the **floor**. Unknown-cousin discovery is the
  **product**. `ANOMALOUS_UNCLASSIFIED` ("cousin-of-X but not X, and nothing
  catches it") is first-class, valued by cousin distance.
- **Two cousin surfaces**: spatial (near-neighbor in hunt-memory space) and
  temporal (a detection drifting from its own baseline — a technique that
  evolved into a cousin of itself).
- Findings begin as **suspects and earn promotion** through executable gates.
  The council is **adversarial, not democratic**: seats falsify; an unrebutted
  material objection blocks; votes never promote.
- The system **compounds**: six feeds + a train→redeploy flywheel make hunt
  N+1 measurably better than hunt N. Storage is not learning; every feed must
  demonstrably change later behavior.
- **Models reason and explain. Code governs state transitions, distance,
  thresholds, gates, and mandatory control flow. Operators confirm
  consequential promotion.**

## 2. Goals

1. A hunt loop that directs Red to manufacture structurally-valid cousins of
   known attacks in the lab, consumes the resulting Episodes, grades cousin
   distance, and alarms on uncovered cousins.
2. A persistent substrate and semantic organ so every hunt starts from
   everything prior hunts learned (positive and negative).
3. An alert bin with real, executable promotion gates (evidence → static +
   dynamic reproduction → not-benign → adversarial council → analyst-visible),
   operator-confirmed promotion.
4. A self-bullying fleet council whose unresolved objections block promotion.
5. Family-generalizing detection handoff: a promoted cousin exits as coverage
   for its whole family, with a regression test.
6. The six compounding feeds, each with a measurable effect on later hunts.
7. A fleet-local training flywheel: harvest → train → fuse → GGUF →
   `ollama create` → bench-gate → operator confirm → serve, where training
   survives only on measured gain.
8. Cost accounting that proves the economics compound (cost per promoted
   cousin falls).

## 3. Non-goals

- Not a SIEM, SOAR, or EDR replacement; Splunk remains the telemetry plane.
- Not modifying Red execution (`exec_chain`, `lab.py`, attack image) — the
  bully directs, never rewrites. Editing Red execution is scope creep.
- Not a production intrusion-detection deployment; output is detection
  engineering + hunt intelligence for the lab defense program.
- Not auto-promotion of anything consequential (findings, detections, models,
  playbooks, roster) — operator confirms, machine-enforced.
- Not a new vector DB, orchestration framework, experiment tracker, or daemon
  (a continuous hunt daemon is a documented future extension, not this build).
- Not training foundation models; only LoRA-scale adapters on fleet models.
- Not moving the doc spine's design facts into the organ, or the organ's hunt
  memory into the spine. They are different organs.
- Not reopening P5-SEC-BENIGN-CORPUS-001 (resolved) or the model-catalog
  spine re-pin tax (separate task).

## 4. Core principles

1. **Suspect-until-proven.** Every finding starts in the bin as a SUSPECT.
   Promotion is earned through gates, in code.
2. **Structural validity + adversarial variation.** Mutation produces valid
   TTPs with perturbed parameters/timing/artifacts — never noise.
3. **Consumer context defines value.** A finding invisible to the SOC console
   under queue load is not promotable.
4. **Negative results are first-class.** Kills, dead ends, benign cells, and
   known defenses are recorded and steer future hunts.
5. **Universal indexing.** Nothing the hunt emits is un-indexed, positive or
   negative. Pre-hunt recall is mandatory and enforced in code.
6. **Code decides, model explains.** Distance, thresholds, gates, quorum,
   state transitions: code. Content, hypotheses, objections, rationales:
   models.
7. **Honest-BLOCKED over faked-green.** A killed cousin is a correct
   non-finding; a missing capability blocks loudly; a too-small corpus is a
   documented non-build of the train leg, not a skipped feed.
8. **Red is the means.** Directed, never modified.
9. **Label-blind production.** Production cousin grading, grounding, and
   verdict paths never read eval answer keys (`answer_key_visibility:
   scorer_only` is preserved).
10. **The council falsifies.** Seats are tasked to break candidates; absence
    of an unrebutted material objection is the promotion condition.

## 5. System boundaries

**Inside:** the hunt brain and heart — hunt loop, cousin engine, drift engine,
alert bin, adversarial council, mutation director, target selector, plateau +
cost metering, detection handoff, knowledge organ, persistent substrate,
harvest, playbook memory, training orchestration, roster weighting, scoring.

**Outside (consumed, not modified):** Red execution (`exec_chain`, `lab.py`,
attack image, sandbox/proxmox MCPs); the Episode truth plane (`episode.py`);
the telemetry plane (`siem/*` shipping, capture store, Splunk); the detection
library (`spl_detections.yaml` — modified only through operator-confirmed
handoff); the inference fleet (Ollama, pipeline, backends registry); the
embedding/reranker services (:8917/:8925); the bench harness (repositioned as
model-acceptance gate); the wiki spine (design facts only); Open WebUI.

**Boundary crossings:** (a) bully → Red: MutationSpec (direction only);
(b) Red → bully: Episode + evidence refs (existing contract); (c) bully →
Splunk: candidate notables + detection rules (operator-confirmed); (d) bully →
fleet: review/investigation prompts; (e) fleet → bully: structured verdicts/
objections parsed into code gates; (f) bully → operator: promotion queues and
cost/score readouts; (g) operator → bully: confirms, config, budgets.

## 6. Final architecture (component model)

Sixteen components, four planes:

```text
┌──────────────────────────── KNOWLEDGE PLANE ───────────────────────────┐
│ SUB  persistent hunt substrate (SQLite; state, decision log, cost,     │
│      baselines, known-state DB)                                        │
│ ORG  semantic hunt organ (LanceDB hunt_memory; embed :8917,            │
│      rerank :8925; record-level, distance-returning)                   │
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────── BRAIN ───────────────────────────────────┐
│ LOOP hunt driver (directs Red, consumes Episode, enforces recall/      │
│      indexing invariants, owns the iteration)                          │
│ BR-COUSIN spatial cousin engine (composite distance, grading,          │
│      explanation)                                                      │
│ BR-DRIFT temporal cousin engine (detection-baseline drift)             │
│ MUT  mutation director (MutationSpec → Red direction surface; budget)  │
│ TGT  target selector (ROI × known-state penalties)                     │
│ PLT  plateau + cost meter (marginal-discovery stopping; economics)     │
│ SCORE discovery-first, distance-graded scoreboard                      │
└────────────────────────────────────────────────────────────────────────┘
┌───────────────────────── BIN & HEART (promotion) ──────────────────────┐
│ BIN  alert bin (G0 → G1a/G1b → G2 → G3; suspect-by-default state       │
│      machine)                                                          │
│ HEART self-bullying council (falsification seats; objection gate)      │
│ HND  family-generalizing detection handoff (the exit)                  │
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────── FLYWHEEL (fleet sharpening) ─────────────────────┐
│ HARV training-pair harvest (role-tagged, provenance, label-blind)      │
│ PLAY per-scenario-class playbook memory (learned shapes)               │
│ TRAIN fleet-local LoRA flywheel (train→fuse→GGUF→create→bench→serve)   │
│ ROSTER retrospective council weighting (bounded, non-gating)           │
└────────────────────────────────────────────────────────────────────────┘
```

### Component responsibilities (summary; full detail in ARCHITECTURE doc)

| Component | Responsibility | Disposition |
|---|---|---|
| SUB | Owns all persistent hunt state: coverage cells, known-benefit/benign/covered/defense DB, cousin records, decision-event log, cost ledger, plateau state, detection baselines, hunt runs | NEW (`hunt_state.py`) seeded from EvidenceRecord schema + CaseNotebook SQLite/supersede pattern |
| ORG | Semantic memory of everything the hunt has emitted; k-NN with raw distances; provenance classes; universal indexing sink | NEW module (`hunt_organ.py`) on existing LanceDB + :8917/:8925 infra; rag_mcp untouched |
| LOOP | The hunt iteration driver; enforces mandatory recall before direction and universal indexing after; owns stop/plateau consult | NEW (`hunt_loop.py`); reuses blue_orchestrate section machinery as investigation arm |
| BR-COUSIN | Grades SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS_UNCLASSIFIED via composite multi-dimensional distance; emits per-dimension explanation | NEW (`cousin_engine.py`); retrofits unknown_defense's grading vocabulary + explainability |
| BR-DRIFT | Per-detection rolling baselines; classifies drift (telemetry failure / environmental / detection degradation / attacker evolution) | NEW (`drift_engine.py`) extending drift_gate machinery |
| BIN | Promotion gate pipeline + suspect state machine; real G1a/G1b proof | NEW (`alert_bin.py`); extracts DraftDetection/ProofResult shapes from growth_loop; gates real |
| HEART | Falsification council; objection-presence promotion gate; dissent persistence | NEW (`heart_council.py`) on platform council mechanics; replaces council_agreement |
| MUT | Turns a chosen known into structurally-valid variants directed at Red within a code-enforced budget; harvests off-script emergent misses | NEW (`mutation_director.py`); reuses evasion-feedback channel + capture recipes + emergent_gaps |
| SCORE | Distance-graded discovery scoreboard; ANOMALOUS_UNCLASSIFIED == full catch preserved | REUSE+EXTEND notify_scoreboard semantics (`hunt_scoreboard.py`) |
| TGT | Ranks cousin neighborhoods by ROI with multiplicative known-state penalties | NEW (`target_selector.py`) |
| PLT | Stops exhausted neighborhoods; tracks cost-per-promoted-cousin trend | NEW (`plateau.py`) |
| HND | Family-generalizing detection package + regression recipe + FP analysis; operator-confirmed exit | NEW (`handoff.py`); extracts response_loop primitives |
| HARV | Role-tagged (evidence → verdict+rationale) pair extraction into versioned corpus | NEW (`harvest.py`); reuses recall_attribution for eval-side labels |
| PLAY | Learned per-scenario-class instruction sets, versioned, operator-confirmed | NEW (`playbook_memory.py`); retrofits playbooks.py container pattern |
| TRAIN | LoRA train/fuse/convert/redeploy/bench-gate orchestration | NEW (`train_flywheel.py`); toolchain install is an owned build step; redeploy + bench legs exist |
| ROSTER | Retrospective seat weighting from objection-validity + cousin-call correctness; bounded, advisory-only | NEW (`roster.py`) |

## 7. Runtime execution flow

One hunt run (invoked via `python3 -m portal.modules.security.core hunt …`;
also resumable) iterates neighborhoods until plateau or budget:

```text
1. LOAD      SUB.load() — known-state, plateau, cost, baselines, open cells
2. RECALL    ORG.recall(context) — MANDATORY, in LOOP code (never model
             discretion): prior cousins, defenses, kills, plateaus for the
             candidate neighborhoods
3. SELECT    TGT.rank(cells, known_state, cost_ledger, recall) → target
             neighborhood + cousin hypothesis
4. DIRECT    MUT.plan(known, budget) → MutationSpec → scenario overlay →
             Red executes UNCHANGED (exec_chain) → telemetry ships UNCHANGED
             (collect_and_ship) → Episode minted UNCHANGED (episode.py)
5. INVESTIGATE  investigation arm (blue_orchestrate sections: Retriever →
             Hunter → Expert) over episode-scoped label-blind telemetry
             (spl_backend.query_episode); _cite_or_drop grounding; verdict +
             similarity carry (SectionOutput)
6. GRADE     BR-COUSIN: composite distance vs ORG knowns → grade + per-
             dimension decomposition; BR-DRIFT: update detection baselines,
             flag temporal cousins (route attacker-evolution to BR-COUSIN)
7. GATE      BIN: G0 evidence → G1a static replay → G1b dynamic re-exec →
             G2 not-benign → HEART falsification council (objection gate) →
             G3 analyst-visible (triage-lane measurement) → PENDING_OPERATOR
8. RECORD    SUB: decision-event log, cousin record, known-state updates,
             cost ledger append; ORG: index ALL emissions (invariant);
             HARV: append role-tagged pairs; PLAY: draft shape update;
             SCORE: distance-graded scoreboard update
9. STOP?     PLT: marginal discovery rate vs floor + known-state saturation
             → continue / rotate neighborhood / stop
10. PROMOTE  Operator confirms PENDING_OPERATOR items → HND emits family
             package + regression recipe → spl_detections.yaml change through
             normal validation (BQ/AZ hold) → coverage cell closes in SUB
```

Failure at any gate records the outcome (negative learning) and the iteration
continues or rotates; infrastructure failure marks the Episode INDETERMINATE
(existing reason codes) and blocks the iteration honestly.

## 8. Data flow

```text
Red (lab) ──telemetry──> Splunk (portal5_lab, episode_id-indexed)
   │                          │
   └──Episode+evidence_refs──>LOOP──query_episode──> investigation arm
                                 │                      │ verdict+carry
                                 ▼                      ▼
                    ORG <──index── emissions      BR-COUSIN ──> grade
                    │  ▲                                │
                    │  └────────recall──────────────────┤
                    ▼                                   ▼
                   SUB <──decision events/cost/known-state── BIN/HEART gates
                    │                                   │
                    ▼                                   ▼
            TGT/PLT/SCORE readouts            HND package → operator confirm
                    │                                   │
                    └──HARV corpus ──> TRAIN ──> fleet ──> later hunts (LOOP)
```

## 9. State model

**SUB owns (SQLite, `PORTAL5_HUNT_DIR/hunt_state.db`, default
`/Volumes/data01/portal5_hunt/`):** hunts, cousin records, coverage cells,
known-state entries (benign/covered/defense/dead-end), detection baselines,
decision events, cost ledger rows, plateau records, promotion queue,
supersession links. All records carry provenance (hunt_id, episode_id,
created_at, source authority class). Supersede never deletes.

**ORG owns (LanceDB `hunt_memory` table under the existing LANCE dir):**
embedded hunt emissions — cousin narratives, kill rationales, benign patterns,
plateau records, playbook summaries, detection-change summaries. Record-level
metadata: `record_id, hunt_id, episode_id, kind, provenance_class,
technique_ids, tactic, field_signature, behavior_sequence, detection_response,
grade, outcome, ingested_at`.

**Transient:** Episode (existing), MutationSpec, gate results, council
opinions (persisted as decision events), composite distance decomposition.

**Explicitly NOT state:** the doc spine (design facts only); field_journal
(existing behavior preserved; its patterns are a PLAY/HARV source, its store
is superseded in role, not migrated); capability_graph (rebuilt on demand as a
readout over SUB, not a store).

Full schemas in `DATA_MODEL_DEFENSIVE_BULLY.md`.

## 10. Cousin definition (normative)

An attack B is a cousin of attack A when their **hunt records** are near in
composite distance and the relationship is defensible per-dimension.

Composite distance (weights `w*` in config, sum=1):

```text
D(A,B) = w1·d_semantic   (cosine over organ embeddings of canonical records)
       + w2·d_attack     (0 same-tech / sibling / same-tactic / cross-tactic)
       + w3·d_telemetry  (1 − field-signature Jaccard, sourcetype-weighted)
       + w4·d_behavior   (normalized edit distance over step-kind sequences)
       + w5·d_detection  (distance between per-detection outcome vectors)
```

Defaults (calibration set in VALIDATION doc): `w = [0.30, 0.20, 0.20, 0.20,
0.10]`. Every grading emits the full decomposition — no unexplained scores.

### Same/similar/new/different semantics (code-enforced)

| Grade | Rule (all deterministic) | Meaning |
|---|---|---|
| SAME | d_attack=0 ∧ discriminators match (spl distinguishing tokens present in B's telemetry) ∧ d_semantic ≤ τ_same (0.15) | B is A. Known coverage applies. Veto: discriminator contradiction → downgrade |
| SIMILAR | D ≤ τ_similar (0.45) ∧ (d_attack ∈ {sibling, same-tactic} ∨ d_telemetry ≤ 0.4) | B is a variant of A. Coverage transfer question is live |
| NEW | τ_similar < D ≤ τ_new (0.70) ∧ tactic-family related | B is new but neighborhood-anchored |
| DIFFERENT | D > τ_new | Not a cousin. Not interesting |
| ANOMALOUS_UNCLASSIFIED | not SAME/SIMILAR to any COVERED known ∧ detection-response blind ∧ d_telemetry/d_behavior deviate from known-benign shapes | **Cousin-of-X but not X, and nothing catches it — the product** |

Thresholds live in `config/security/hunt.yaml`; calibrated per VALIDATION doc;
changes are operator config edits (and recorded decision events).

**How Portal explains it to a human:** grade + decomposition + feature-overlap
citations (the U1-preserved layer) + nearest-known references, e.g. "SIMILAR
to T1558.003 (D=0.41): same tactic; field overlap {EventCode, TargetUserName,
ServiceName}; persistence reordered before lateral; no rule fired."

**Meaningful novelty vs arbitrary distance:** novelty requires detection
blindness + structural (telemetry/behavior) deviation. Pure semantic distance
never alone produces NEW/ANOMALOUS.

## 11. Spatial-cousin design

Neighborhoods: k-NN (k=25 default) around known-bad records in ORG, bounded at
D ≤ τ_new. A hunt picks a neighborhood (TGT), MUT manufactures variants of its
knowns, each manufactured Episode is graded; SIMILAR+blind or
ANOMALOUS_UNCLASSIFIED candidates enter the bin. Resolved/open cell map
persists in SUB — the next hunt starts from the enriched map.

## 12. Temporal-cousin design

Per-detection baseline in SUB (rolling window, 20 firings or 30 days default):
fire rate, hit latency, row shape, clause-level partial satisfaction,
sourcetype completeness. `drift_engine` recomputes per hunt over the Episode's
telemetry + detection outcomes, using drift_gate's rolling-window statistics.

Classification (code):

| Signal pattern | Class |
|---|---|
| sourcetype volume collapse / index gaps | TELEMETRY_FAILURE (ops alert, not a cousin) |
| host/identity population shift, rules unchanged | ENVIRONMENTAL_CHANGE |
| rule fires weaker/later/partial-clause-only | DETECTION_DEGRADATION (tuning lead) |
| behavior/fields shifted, technique persists, rule weak | ATTACKER_EVOLUTION → temporal cousin → routed to BR-COUSIN for spatial grading + bin entry |

## 13. Alert/promotion design

State machine (BIN owns; all transitions code, logged as decision events):

```text
SUSPECT ──G0 evidence (observed-origin only)──▶ G1a static replay
  ──▶ G1b dynamic re-execution ──▶ G2 not-benign ──▶ COUNCIL (HEART)
  ──▶ G3 analyst-visible ──▶ PENDING_OPERATOR ──confirm──▶ PROMOTED
                                          └──reject──▶ KILLED (rationale indexed)
  any gate fail ──▶ KILLED (gate + rationale recorded; organ indexed)
```

- **G0 evidence-exists:** ≥1 observed-origin evidence ref
  (`telemetry.OBSERVED_EVIDENCE_ORIGINS`); synthetic/counterfactual never
  passes.
- **G1a static:** candidate signature executes against the replayed capture
  and fires within window on the right target (capture_store replay +
  SplunkBackend; mirrors `derive_detection_status` semantics).
- **G1b dynamic:** re-execution reproduces the behavior chain and expected
  artifacts — deterministic recipe re-run (`capture_recipes`) where one
  exists, else a directed Red re-run within MUT budget; artifacts verified via
  telemetry contracts. **Static alone is never sufficient.**
- **G2 not-benign:** (a) verdict-contract counter-evidence evaluation
  (dual-use ≠ malicious discipline from `_VERDICT_GROUNDING_POLICY`); (b)
  candidate discriminators executed against the benign corpus — zero fires
  required (BQ semantics preserved).
- **HEART:** §14.
- **G3 analyst-visible:** candidate shipped as a Splunk notable (HEC,
  observed origin); the `blue_triage` lane runs against it under the
  queue-load corpus; pass = triage report at priority ≤ configured threshold
  (default P2) within configured SLA. The harness's god-view is not evidence.
- **PENDING_OPERATOR → PROMOTED:** operator confirms in the promotion queue.
  Machine-enforced: `promote_policy: confirm` in hunt config.

Suspect-by-default applies at the **finding** level: every candidate enters as
SUSPECT; silence/incompletion escalates (consistent with the existing
multichain/council fail-safe philosophy), never auto-clears.

## 14. Self-bullying council (HEART)

**Pattern (normative):**

```text
candidate cousin + evidence pack
   ↓
N falsifier seats (isolated; tasked to BREAK it: benign? already-covered?
   hallucinated-evidence? — cite specific evidence)
   ↓
objections + missing evidence + conditions_to_change (platform contract fields)
   ↓
deterministic materiality classification (code): material if it cites
   (a) a specific evidence contradiction, (b) an already-covering detection id,
   or (c) benign-context counter-evidence per the verdict contract
   ↓
material objection present? ──YES──▶ rebuttal round (promoting chain answers
   │                                  with evidence; falsification re-pass)
   │                                  └── still standing ──▶ BLOCK (KILLED or
   │                                                       returned for evidence)
   └──NO──▶ eligible for next gate
```

- Seats: ≥3, **≤1 per model family** (config-enforced diversity), roster from
  `config/security/heart.yaml`; models resolved via the backends registry
  (never hardcoded).
- Reuse: platform `council.py` isolation, parsing, participation accounting,
  ESCALATE floors (BL preserved: non-voters count against the roster).
- Participation floor is a *validity* floor, not a decision rule: sub-floor →
  the review is invalid → candidate escalates to operator (never auto-passes).
- Dissent is persisted to the decision log in full (minority views are never
  dropped).
- `aggregate_opinions`'s vote-counting is NOT the promotion mechanism; the
  objection gate is. `council_agreement.py` is retired in this role.

## 15. Red interaction model

The bully directs Red through a **MutationSpec**:

```text
MutationSpec = { base_scenario, variant_params {timing, tool_args, artifacts,
  sub_technique_adjacency[], evasion_directive}, target_host, budget_class,
  expected_artifact_contract }
```

Consumed by a **scenario overlay** path: the overlay renders `red_prompt` +
`red_order` variants from the base scenario (existing `_prepare_scenario`
substitution mechanics), then hands to the unchanged `_run_chain_test` /
`lab_dispatch` / telemetry pipeline. Off-script emergent behavior continues to
feed gaps via `emergent_gaps`. Deterministic re-execution uses
`capture_recipes`. Budget (in code): `max_variants_per_neighborhood`,
`max_perturbation` (mutation-step distance from the base), scope unchanged
(`perception.assert_in_lab`). Red execution code is never edited — a required
edit is a stop-and-file condition.

## 16. Knowledge organ (ORG)

- One LanceDB table `hunt_memory` (sibling of rag KBs under `PORTAL5_LANCE_DIR`).
- Record-level API (module-internal, not an MCP tool): `upsert(record)`,
  `knn(vector|record, k, filters) → [(record, distance)]`,
  `delete(record_id)` (supersede preferred), `rebuild` guarded.
- Embedding via :8917 (batch), rerank via :8925 (fallback dense order —
  existing rag_mcp pattern). Distance returned is **raw cosine** — rerank
  scores are presentation, never the cousin metric.
- Provenance classes: `hunt_emission`, `operator_assertion`, `external_intel`.
  Retrieval filters by class; a SAME grading may not rest solely on
  low-authority classes.
- **Invariants (code-enforced by LOOP):** (1) pre-hunt recall executed and its
  result attached to the hunt record before direction; (2) every emission
  (candidate, verdict, kill, plateau, defense, benign pattern) indexed before
  the iteration closes — an unindexed emission is a failed iteration, not a
  skipped step.

## 17. Persistent substrate (SUB)

SQLite (WAL), one file per deployment, tables per DATA_MODEL doc. Access only
through `hunt_state.py` (no raw SQL elsewhere). Append-mostly; supersede links
(`superseded_by`) instead of mutation for known-state and cousin verdicts;
decision log is strictly append-only. All writes idempotent on natural keys
(hunt_id, record kind, subject id) so a crashed iteration can be re-driven
without double-recording. Backup = file copy; restore = file replace +
integrity check command.

## 18. Compounding model

Compounding = feeding + learning + training, and it must be *traceable*:
observation → capture → validation → persistence → retrieval → decision →
changed behavior → new observation. SUB+ORG close the loop; PLT measures it;
SCORE reports it; TRAIN sharpens the fleet from it. The falsifiable claim:
**hunt N+1 selects better targets, grades cousins faster, and wastes fewer
cycles than hunt N, and cost-per-promoted-cousin falls over hunt count.**

### Six feeds (each with its measurable-change instrument)

| # | Feed | Loop closure (retrieve→decide→change) | Instrument proving change |
|---|---|---|---|
| 1 | Semantic hunt memory | LOOP recall → TGT/BR-COUSIN use priors → neighborhood reuse | recall-hit utilization; neighborhood reuse rate |
| 2 | Known-state DB | TGT multiplicative penalties → dead cells skipped | waste rate (hunts into known-dead cells) → 0 |
| 3 | ROI/target intelligence | TGT ranking from cost+yield history | cost-per-promoted-cousin trend (falling) |
| 4 | Training-pair harvest | corpus grows → TRAIN consumes | corpus size/coverage by role; dataset versions |
| 5 | Fleet-local fine-tune | trained specialist served → later hunts use it | cousin-bench delta vs base; hunt budget consumption delta |
| 6 | Playbook memory | class playbook injected into hunt context | time-to-conclusion / budget use: shaped vs unshaped hunts |

## 19. Target selection (TGT)

Score per candidate cell/neighborhood:

```text
value  = asset_criticality × technique_severity × novelty_prior × prior_miss_rate
penalty = Π known-state factors (benign 0.0 / covered 0.1 / defended 0.3 /
          dead-end 0.2 / recent-kill decay)
cost   = projected model-turns + lab-minutes + analyst-minutes (from ledger)
score  = value × penalty / cost
```

All factors from SUB/ORG; the formula is config-tunable but the *inputs* are
mandatory. Deterministic; fully logged (why this target, what was declined and
why — including the known-benign decline case in success criteria).

## 20. ROI model

ROI per hunt = risk-reduction value realized / total cost. Risk-reduction
value realized = Σ over promoted cousins of (family coverage closed × asset
weight × severity), pessimistically estimated (minimums, mirroring the
concept's conservative payout rule). Reported per hunt and cumulative; never
used to auto-continue — it informs TGT and the operator.

## 21. Plateau model (PLT)

A neighborhood is exhausted when BOTH: rolling marginal discovery rate
(SIMILAR+NEW+ANOMALOUS records per iteration, window=5) < `plateau_floor`
(default 0.2) for `plateau_patience` (default 3) consecutive iterations; AND
known-state saturation (resolved cells / mapped cells) > `saturation_ceiling`
(default 0.8). Embedding-cluster stability is explicitly NOT a stop signal.
Plateau events are recorded (SUB + ORG) and steer future TGT away from the
exhausted neighborhood until its known-state changes (new detection, new
external intel, new detection-baseline drift).

## 22. Cost model

Ledger per hunt: model tokens (in/out per role), wall-clock, lab actions,
lab-minutes, operator minutes (confirm queue dwell). Unit costs in config.
Headline: cost per promoted cousin over hunt number; secondary: cost per
graded candidate, per gated candidate. Compounding economics are falsifiable
against these series.

## 23. Detection-engineering exit (HND)

A promoted cousin exits as a family-generalizing package:

1. Generalized SPL (family-level discriminators lifted from the cousin's
   distinguishing features) + per-sourcetype variants (`spl_variants` shape);
2. Sigma rule (YAML);
3. Required-telemetry statement;
4. ATT&CK mapping delta (new sub-technique coverage / sibling extension);
5. Evidence package (episode refs, gate history, council record);
6. Reproduction instructions = **new capture recipe** (regression test —
   becomes part of the certified corpus);
7. FP analysis (benign-corpus results attached from G2);
8. Known limitations;
9. IR implications (seeded from the RESPONSE_PRIMITIVES technique map);
10. Coverage impact (SUB delta preview).

Portal generates all deterministic parts; a model drafts prose where useful;
the operator confirms the `spl_detections.yaml` change through the normal
validation pipeline (BQ/AZ must stay green). The handoff is complete when the
regression recipe replays green.

## 24. Training flywheel

```text
HUNT → HARV (role-tagged pairs) → CORPUS (versioned JSONL) → TRAIN
  (mlx_lm LoRA on a fleet base) → FUSE → GGUF convert → ollama create
  (models.py import-gguf) → BENCH GATE → OPERATOR CONFIRM → SERVE →
  later HUNT uses the specialist
```

- Corpus roles: hunter / analyst / disprover / cousin-smeller. Example types:
  evidence→verdict+rationale; objection↔rebuttal exchanges; distance judgments
  with decompositions; kill rationales (negative examples are first-class).
- Provenance per example: hunt_id, episode_id, source models, distances,
  outcome. Label-blind discipline preserved: production grading never reads
  answer keys; eval-side honest-miss labels come from `recall_attribution`.
- Splits: by hunt date + a scenario-family holdout. Dataset versioned
  (content hash + manifest). Model tag `<base>-cousin<dv>`; seeds/config
  recorded; prior GGUF retained for rollback.
- **Acceptance gate (the repositioned bench):** candidate must (a) beat the
  incumbent on the cousin-judgment bench, (b) not regress the general security
  bench (catastrophic-forgetting control), (c) pass intake floors (TPS,
  tool-call reliability), then (d) operator confirm via the existing
  PENDING_MODEL_VERDICTS flow.
- **Comparison arms** the gate runs: base / base+retrieval / base+playbook /
  base+retrieval+playbook / trained. Training ships only on measurable gain
  over the best non-trained arm. Difficulty is not a reason to skip; lack of
  measured gain is a reason not to serve.
- Toolchain: `mlx-lm` (LoRA train + fuse) + `llama.cpp` GGUF convert,
  host-native on Apple Silicon; installation and verification are explicit
  build steps owned by the TRAIN phase.

## 25. Model lifecycle

Trained models enter exactly like any candidate (import-gguf → intake floors →
candidate delta vs incumbent → operator verdict), plus the cousin-bench delta
and the dataset-version provenance recorded in the verdict file. Serving a
specialist means pointing the relevant hunt role (e.g. disprover seat,
cousin-smeller) at it via config — never a code change. Rollback = re-point
config; the prior GGUF/model tag remains.

## 26. Playbook lifecycle (PLAY)

Drafted from successful hunt trajectories per scenario class (ransomware,
credential-theft, lateral-movement, web-exploit, …): instruction sets
(what to recall first, which discriminators decide, common kills, budget
shapes). Versioned records in SUB; promoted to active only by operator
confirm; injected by LOOP into the investigation arm's context for hunts of
that class; effectiveness tracked (budget consumption, time-to-conclusion)
and fed to ROSTER/TRAIN as hunt-quality signal. The static
`playbooks/security/*.yaml` engagement playbooks remain for the red-side loop
— PLAY is the defensive learned memory, not a rename of those files.

## 27. Roster / council-learning model (ROSTER)

Per seat, tracked in SUB from decision events: objection-validity rate
(objections that stood vs rebutted), cousin-call correctness (retrospective
grading vs eventual outcome), participation. Weight = bounded [0.5, 2.0],
recomputed per hunt window. Weights order seat selection and inform advisory
aggregates; **the objection gate ignores weights** — any seat's standing
material objection blocks. All weight changes are decision-logged and visible.
Monoculture guard: family-diversity constraint at roster config + minority
dissent persisted make correlated-seat dominance structurally visible.

## 28. Operator controls

- Promotion queue (findings/detections/models/playbooks/roster changes) —
  confirm or reject with rationale; rejections are indexed (negative learning).
- Hunt config: budgets (iteration, wall-clock, lab-action, mutation),
  thresholds (τ bands, plateau), cost rates, roster, triage SLA, promote
  policy.
- CLI surfaces: `hunt run|resume|status`, promotion queue review, scoreboard /
  cost / plateau readouts, organ inspection (read-only).
- Emergency stop: config flag halts direction of new Red runs (in-flight
  iterations complete their recording and stop).

## 29. Deterministic-vs-model responsibility

| Code (deterministic) | Models (reasoning) |
|---|---|
| recall/index enforcement; distance + grading; thresholds; gate logic; state transitions; quorum/participation floors; objection materiality classification; blocking on unrebutted objection; budget enforcement; scope guard; plateau detection; cost accounting; corpus schema + splits; bench gating | hypotheses; investigation reasoning; verdict content (grounded); objection content; rebuttal content; SPL/Sigma prose drafting; playbook prose; explanation narratives |

A model never emits a state transition; code never invents content.

## 30. Failure semantics

- Lab unreachable / Splunk down / telemetry unindexed: existing reason codes
  → Episode INDETERMINATE; iteration records honest-BLOCKED and stops or
  rotates; never scored as a miss or a pass.
- Embedding/reranker down: organ degrades to lexical fallback **flagged
  degraded**; grading that required distance is blocked, not approximated
  silently.
- Council seat failure: non-participation counts against the floor (BL);
  sub-floor → review invalid → escalate to operator.
- Model refusal/stall mid-investigation: existing chain semantics (stall caps,
  UNRESOLVED) → candidate stays SUSPECT, recorded.
- Train leg with too-small corpus: documented non-build of that leg (the feed
  exists; the data isn't there yet) — never a fabricated result.
- Crashed iteration: idempotent keys allow re-drive; SUB never double-records.

## 31. Provenance

Every SUB/ORG record carries: ids (hunt, episode, parent records), source
authority class, model ids involved, distances/decompositions, gate history,
timestamps, and supersession links. Council opinions and rebuttals persist in
full. Promotions append to the wiki provenance ledger (existing
`provenance_ledger.append_entry` surface) as the operator-facing audit trail.
Detection lineage: every detection rule traces to the cousin(s) and hunt(s)
that produced it via the handoff package.

## 32. Observability

- Decision-event log (SUB) — every gate, grade, block, confirm, kill with
  rationale.
- Scoreboard (SCORE) — distance-graded discovery metrics per hunt and
  cumulative; ANOMALOUS_UNCLASSIFIED valued.
- Plateau/cost readouts (PLT) — compounding economics.
- Notifications reuse the existing dispatcher (loop.py pattern) for
  promotion-queue arrivals, BLOCKED states, plateau stops.
- Organ stats (record counts by kind/class), retrieval-utilization metrics.

## 33. Security boundaries

- Lab scope guard unchanged (`perception.assert_in_lab`, 10.10.11.0/24);
  MutationSpecs resolve through the same guard.
- Label-blindness: production grading/grounding/verdicts never read answer
  keys (BM boundary preserved; corpus config unchanged).
- The organ's hunt memory is local-only; no external egress.
- Operator confirm is required for: spl_detections.yaml changes, model
  serving, playbook activation, roster activation. The pipeline's existing
  guardrails for exec workspaces are unchanged.
- No new MCP tools required for the core loop (the bully is security-core
  modules + CLI); MCP boundaries (Rule 3) respected.

## 34. Resource considerations

- Hunt iteration cost ≈ one red chain + one investigation arm + one council
  review; bounded by hunt budgets and backend memory budgets.
- Embedding is CPU-pinned — batch upserts; reranker MLX — tolerate fallback.
- Council: ≥3 seats × one call each (+1 rebuttal round when objections
  material) — schedule seats sequentially if backend memory requires; the gate
  is correctness, not latency.
- TRAIN: LoRA-scale on host (M4 Pro 64GB); corpus sizes are hunt-scale (hundreds
  to low thousands of pairs), not foundation-scale; training runs are
  operator-initiated, never automatic mid-hunt.

## 35. Configuration requirements

New `config/security/hunt.yaml` (convention of config/security/*):

```yaml
organ: { table: hunt_memory, k: 25, provenance_classes: [...] }
distance: { weights: [0.30,0.20,0.20,0.20,0.10], tau_same: 0.15,
            tau_similar: 0.45, tau_new: 0.70 }
mutation: { max_variants_per_neighborhood: 4, max_perturbation: 2 }
budgets: { max_iterations: 20, max_wall_clock_sec: 7200, max_lab_actions: 60 }
plateau: { floor: 0.2, patience: 3, saturation_ceiling: 0.8, window: 5 }
costs: { token_in: …, token_out: …, lab_minute: …, analyst_minute: … }
triage: { priority_threshold: P2, sla_minutes: 30 }
promote_policy: confirm        # machine-enforced
roster_ref: config/security/heart.yaml
```

New `config/security/heart.yaml`: seats (id, model, family, role=falsifier),
participation floor, materiality criteria version. Portal.yaml: a
`blueteam-heart`-style variant entry only if workspace addressing is needed —
prefer config files + registry resolution; no changes to derived files
except through `sync-config`.

Spine: new modules land under `unit-surface-sec-core` globs → zero new units;
at most one authored design unit per phase.

## 36. Migration assumptions

Summarized (full table in MIGRATION doc): Red untouched; Episode contract
preserved; section machinery extracted from blue_orchestrate's bench shell;
growth_loop/response_loop/continuous_eval retired after extraction;
council_agreement replaced; multichain kept; capability_graph becomes a
readout over SUB; bench harness repositioned as the train gate. Every
retirement lands only when its replacement is live (honest-BLOCKED rule).

## 37. Final invariants

1. Same/similar/new is the product; known-bad catch is the floor.
2. `ANOMALOUS_UNCLASSIFIED` is first-class, valued by cousin distance.
3. Two cousin surfaces — spatial and temporal — both live.
4. Red is directed, never modified.
5. The council falsifies; unrebutted material objection blocks; votes never
   promote.
6. Six feeds all live, each with a measured effect on later hunts.
7. Universal indexing; mandatory pre-hunt recall — in code.
8. Static+dynamic pairing: a signature alone never promotes.
9. Consumer context: analyst-visibility is measured, not asserted.
10. Confirm-only on all consequential promotion — machine-enforced.
11. Code decides, model explains.
12. Honest-BLOCKED over faked-green.
13. Label-blind production paths (BM) preserved; BQ/AZ/BL/BN gates held green.
14. The spine gets lighter; runtime hunt state never enters the spine.
15. Training serves only on measured gain over non-trained arms.

## 38. Complete success criteria

The system is complete when ALL hold, demonstrated on its own artifacts:

1. **Hunt loop + cousins:** a hunt consumes a Red Episode, grades cousin
   distance with per-dimension decomposition, and a second hunt starts from
   the enriched neighborhood (recall demonstrably changes target selection);
   a NEW cousin the lexical scorer (U1) graded ~0/NONE is surfaced and graded
   correctly by the composite engine.
2. **Bin + heart:** a manufactured cousin is SUSPECT-by-default; passes G0 →
   G1a/G1b (static replay + dynamic re-execution) → G2 (benign corpus clean)
   → council (a planted material objection blocks until rebutted) → G3
   (triage lane reports within SLA under queue load) → operator confirm →
   PROMOTED; a planted nonsense candidate is KILLED with rationale and its
   kill is indexed and retrievable by the next hunt's recall.
3. **Mutation + drift:** Red produces a budgeted near-neighbor the current
   detections miss and the system alarms; a detection whose firing shifts
   from its baseline is flagged, correctly classified (telemetry failure /
   environmental / degradation / attacker evolution), and the evolution case
   routes into cousin grading.
4. **Selection + stopping:** far NEW cousins score ≥ known-bad catches;
   TGT declines a known-benign cell (logged with reasons); plateau stops an
   exhausted neighborhood; cost-per-promoted-cousin is computable per hunt
   and the series is reportable.
5. **Exit:** a promoted cousin yields a family-generalizing package whose
   regression recipe replays green and whose detection change passes BQ/AZ.
6. **Flywheel:** HARV corpus (all four roles, incl. adversarial + distance
   pairs, label-blind-clean) versioned; playbooks accumulate and measurably
   shape hunts; a LoRA adapter trains from the corpus, fuses → GGUF →
   `ollama create` → passes the bench gate (beats incumbent on cousin bench,
   no general regression) → serves on operator confirm; ROSTER reweights on
   retrospective correctness with the objection gate unaffected. **A later
   hunt uses the trained specialist and is measurably better at cousin
   judgment.**
7. **Compounding proof:** on a recorded hunt series, the six feed instruments
   (§18) show the required trends; the learning chain
   (observation→…→changed behavior) is traceable end-to-end for at least one
   decision per feed.

## 39. Architecture diagrams

Primary diagrams live in `ARCHITECTURE_DEFENSIVE_BULLY.md` (component map,
call-paths, data/state boundaries) and §6-§8 above (component planes, runtime
flow, data flow). The promotion pipeline diagram is §13; the council pattern
is §14; the flywheel is §24.

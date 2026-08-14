# FINAL DESIGN — Defensive Bully (AUTHORITATIVE)

**Status: the authoritative definition of WHAT is being built.** Standalone: a
fresh coding agent must be able to build the complete system from this package
without the source plans (K3/O48/SOL), the prior build program, or the
original conversations. Grounded against Portal 5 HEAD `47d3e884`; every
existing-code anchor cited here was verified by direct reads at that HEAD and
must be re-verified at the build session's own HEAD (grounding contract —
drift is a finding; adjust the implementation, never the invariants, without
operator review).

Authority order within this package: this file (WHAT) →
`FINAL_ARCHITECTURE_DEFENSIVE_BULLY.md`, `FINAL_INTERFACES_DEFENSIVE_BULLY.md`,
`FINAL_DATA_MODEL_DEFENSIVE_BULLY.md` (contracts) →
`FINAL_MIGRATION_DEFENSIVE_BULLY.md` (transition) →
`FINAL_VALIDATION_DEFENSIVE_BULLY.md` (proof) →
`FINAL_BUILD_PROGRAM_DEFENSIVE_BULLY.md` (sequence) →
`FINAL_DECISION_LEDGER_DEFENSIVE_BULLY.md` (why) →
`FINAL_COMPARATIVE_REVIEW_DEFENSIVE_BULLY.md` (evidence).

---

## 1. Thesis

Modern offense hunts the *shape* of a weakness and chases everything
structurally adjacent to it — found the TIFF-parser OOM, go break the SFNT
parser for the same bug class. Cousins. The Defensive Bully is the mirror:
**given everything Portal knows, surface the cousins it doesn't** — the
near-neighbor attack one valid mutation from a covered one that existing
detections do not catch — and alarm on it, graded by distance from known.

- Known-bad detection is the **floor**. Unknown-cousin discovery is the
  **product**.
- The product is precise: a finding whose **structural relationship** to a
  known attack is defensible (SIMILAR or NEW, or a credible unplaced anomaly)
  **and** whose **defense response** is NEAR_MISS or MISSED.
  `ANOMALOUS_UNCLASSIFIED` — "cousin-of-X but not X, and nothing catches it" —
  is first-class, valued by distance. `SAME × MISSED` is a detection
  regression: high priority, not a discovery.
- **Two cousin surfaces**: spatial (near-neighbor in hunt-memory space) and
  temporal (a detection drifting from its own baseline — a technique that
  evolved into a cousin of itself).
- Findings begin as **suspects and earn promotion** through executable gates.
  The council is **adversarial, not democratic**: seats falsify; an unrebutted
  material objection blocks; votes never promote.
- The system **compounds**: six feeds + a train→redeploy flywheel make hunt
  N+1 measurably better than hunt N. Storage is not learning; every feed must
  demonstrably change a later decision, and the change is recorded.
- **Models reason and explain. Code governs state transitions, distance,
  thresholds, gates, scope, and mandatory control flow. Operators confirm
  consequential promotion.**

## 2. Goals

1. A hunt loop that directs Red to manufacture structurally-valid cousins of
   known attacks in the lab, consumes the resulting Episodes, grades cousin
   distance, and alarms on uncovered cousins.
2. A persistent, recovery-safe substrate and a semantic organ so every hunt
   starts from everything prior hunts learned — positive and negative — with
   the recall provably influencing the hunt.
3. An alert bin with real, executable promotion gates: authorization →
   evidence integrity → static + dynamic reproduction → causality/not-benign
   → adversarial council → SOC visibility → operator confirmation.
4. A self-bullying fleet council whose unresolved material objections block
   promotion, with durable objection/rebuttal/waiver audit.
5. Family-generalizing detection handoff: a promoted cousin exits as coverage
   for its whole family, with a regression test, operator-confirmed.
6. The six compounding feeds, each with a recorded effect on later hunts.
7. A fleet-local training flywheel: harvest → train → fuse → GGUF →
   `ollama create` → frozen five-arm acceptance gate → operator confirm →
   canary → serve, where training serves only on measured gain.
8. Cost accounting that proves the economics compound (cost per promoted
   cousin falls).

## 3. Non-goals

- Not a SIEM/SOAR/EDR replacement; Splunk remains the telemetry plane.
- Not modifying Red execution (`exec_chain`, `lab.py`, attack image, sandbox /
  proxmox MCPs) — the bully directs, never rewrites. A required Red edit is a
  stop-and-file condition.
- Not a production intrusion-detection deployment; output is detection
  engineering + hunt intelligence for the lab defense program.
- Not auto-promotion of anything consequential (findings, detections, models,
  playbooks, roster) — operator confirms, machine-enforced.
- Not a new vector DB, agent framework, experiment tracker, MCP server, port,
  Docker service, or OWUI function. Not a hunt daemon (a documented future
  extension; the loop is built to allow it).
- Not training foundation models; LoRA-scale adapters on fleet models only.
  Training infrastructure never serves production chat (Ollama stays the sole
  chat tier) and is never imported at runtime startup.
- Not moving doc-spine design facts into the organ or hunt memory into the
  spine — different organs.
- Not reopening P5-SEC-BENIGN-CORPUS-001 (resolved; G2 is its concept-native
  home) or the model-catalog spine re-pin tax (separate task).
- Not claiming every anomaly is a cousin; not claiming compounding without a
  recorded later-decision effect.

## 4. Core principles

1. **Suspect-until-proven.** Every finding starts in the bin; promotion is
   earned through gates, in code.
2. **Structural validity + adversarial variation.** Mutation produces valid
   TTPs with perturbed parameters/timing/artifacts — never noise.
3. **Relationship ≠ coverage.** Structural cousin distance and defense
   response are independent axes; a blind spot never manufactures relatedness.
4. **Consumer context defines value.** A finding invisible in the real
   analyst path under queue load is not promotable.
5. **Negative results are first-class.** Kills, dead ends, benign cells, and
   known defenses are recorded and steer future hunts.
6. **Universal indexing, mandatory recall — in code.** Nothing the hunt emits
   is un-indexed; no hunt targets without a recorded recall. Enforcement is
   transactional (outbox), not prompt-level.
7. **Code decides, model explains.** Distance, thresholds, gates, state
   transitions, materiality, quorum floors: code. Hypotheses, objections,
   rationales, prose: models.
8. **Honest-BLOCKED over faked-green.** A killed cousin is a correct
   non-finding; a missing capability blocks loudly; a too-small corpus is a
   documented non-build of that leg.
9. **Red is the means.** Directed, never modified.
10. **Label-blind production.** Production grading, grounding, and verdict
    paths never read eval answer keys (BM boundary).
11. **The council falsifies.** Absence of an unrebutted material objection is
    the promotion condition; participation floors are validity floors.
12. **Synthetic never proves.** Synthetic evidence develops plumbing; it never
    passes a promotion gate (existing Episode invariant, preserved).
13. **Truth is append-only.** Conclusions are superseded, never rewritten;
    evidence is immutable and content-addressed.

## 5. System boundaries

**Inside (new, security-owned):** the hunt brain and heart — hunt
orchestrator, cousin engine, drift engine, alert bin, adversarial council,
mutation director, target selector, plateau + cost metering, detection
handoff, knowledge organ, persistent substrate, harvest, playbook memory,
training orchestration, roster governance, scoring.

**Outside (consumed, not modified):** Red execution (`exec_chain`, `lab.py`,
attack image, sandbox :8914 / proxmox :8927 MCPs); the Episode truth plane
(`episode.py`); the telemetry plane (`siem/*` shipping, capture store,
Splunk); the detection library (`spl_detections.yaml` — modified only through
operator-confirmed handoff); the inference fleet (Ollama, pipeline, backends
registry); embedding/reranker services (:8917/:8925); the platform council
primitive (`portal/platform/inference/router/council.py` — mechanics reused,
code untouched); the bench harness (repositioned as the model-acceptance
gate); the legacy bench analysis lane (`multichain.py`,
`council_agreement.py`, `blue.py`/`blue_orchestrate.py` drivers — kept
working); `loop.py` (red-side engagement runner — untouched); the wiki spine
(design facts only); Open WebUI.

**Boundary crossings:** (a) bully → Red: a compiled MutationPlan as scenario
overlay data (direction only); (b) Red → bully: Episode + evidence refs (the
existing contract); (c) bully → Splunk: candidate notables + detection-rule
changes (operator-confirmed); (d) bully → fleet: investigation/review prompts;
(e) fleet → bully: structured verdicts/objections parsed into code gates;
(f) bully → operator: promotion queues, cost/score readouts; (g) operator →
bully: confirms, config, budgets, authorizations.

## 6. Final architecture (component model)

Sixteen components in four planes, plus the orchestrator's transaction
infrastructure:

```text
┌──────────────────────── KNOWLEDGE PLANE ─────────────────────────┐
│ SUB  persistent hunt substrate (SQLite WAL authority; state,      │
│      decision log, outbox, cost, baselines, known-state, leases)  │
│ ORG  semantic hunt organ (LanceDB hunt_memory projection;         │
│      embed :8917, rerank :8925; record-level, raw distances;      │
│      recall receipts + decision-impact records)                   │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────── BRAIN ───────────────────────────────┐
│ LOOP hunt orchestrator (stage pipeline; recall/index enforcement; │
│      budgets incl. lab actions; checkpoint/resume; investigation  │
│      arm = blue_orchestrate section runners)                      │
│ BR-COUSIN spatial cousin engine (two-axis grading + explanation)  │
│ BR-DRIFT temporal cousin engine (baseline drift + cause)          │
│ MUT  mutation director (typed plans → scenario overlays; budget)  │
│ TGT  target selector (eligibility + posterior ROI)                │
│ PLT  plateau + cost meter (statistical stopping; economics)       │
│ SCORE discovery-first scoreboard (catch/trust/discovery axes)     │
└──────────────────────────────────────────────────────────────────┘
┌────────────────────── BIN & HEART (promotion) ───────────────────┐
│ BIN  alert bin (G-1 → G0 → G1a/G1b → G2 → HEART → G3 → G5;        │
│      append-only state machine)                                   │
│ HEART self-bullying council (falsification seats; durable         │
│      objections; veto; operator waiver)                           │
│ HND  family-generalizing detection handoff (the exit)             │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────── FLYWHEEL (fleet sharpening) ─────────────────┐
│ HARV training-pair harvest (role-tagged, leakage-governed)        │
│ PLAY per-scenario-class playbook memory (learned, canaried)       │
│ TRAIN fleet-local LoRA flywheel (train→fuse→GGUF→create→bench→    │
│      canary→serve)                                                │
│ ROSTER retrospective seat governance (eligibility/reliability;    │
│      never truth-weighting)                                       │
└──────────────────────────────────────────────────────────────────┘
```

Component responsibilities (contract detail in the ARCHITECTURE doc):

| Component | Responsibility | Disposition |
|---|---|---|
| SUB | Owns all durable hunt state and the stage machine: hunts, iterations, cousin records, candidates/gates, council records/objections, coverage cells, known-state DB, detection baselines, decision events, outbox, cost ledger, plateaus, promotion queue, playbooks, datasets, trained models, roster records, leases | NEW (`bully/` package) seeded from EvidenceRecord schema + CaseNotebook SQLite/supersede pattern |
| ORG | Semantic memory of all hunt emissions; k-NN with raw cosine distance; trust-tier/provenance filters; outbox-coupled universal indexing; mandatory recall with receipts | NEW module on existing LanceDB + :8917/:8925 infra; rag_mcp untouched |
| LOOP | The hunt iteration driver; enforces recall-before-direction and indexing-before-close; enforces all budgets itself; checkpoint/resume; notify-with-resume | NEW; investigation arm reuses blue_orchestrate section runners; discipline mirrored from loop.py |
| BR-COUSIN | Two-axis cousin grading (structural D + defense response) with vetoes and full decomposition | NEW; retrofits unknown_defense's vocabulary + explanation layer |
| BR-DRIFT | Per-detection rolling baselines; deterministic four-cause attribution; temporal cousins routed to BR-COUSIN | NEW; extends drift_gate machinery |
| BIN | Promotion gate pipeline + suspect state machine | NEW; extracts DraftDetection/ProofResult/validate_spl_syntax shapes from growth_loop |
| HEART | Falsification council; durable objection lifecycle; promotion gate | NEW on platform council mechanics; council_agreement/multichain left alone on the legacy lane |
| MUT | Typed mutation plans, validation, compilation to scenario overlays; budget enforcement | NEW; seeds: emergent_gaps, evasion-feedback, fallback_techniques, response_loop reverse-gen, capture_recipes |
| SCORE | Catch/trust/discovery scoreboard | REUSE+EXTEND notify_scoreboard semantics |
| TGT | Hard eligibility + posterior ROI ranking with full decision recording | NEW over SUB/ORG reads |
| PLT | Statistical plateau + cost-per-cousin metering | NEW over SUB reads |
| HND | Family-generalizing detection package + detection-proof legs + proposal lifecycle | NEW sibling to response_loop; growth_loop's legs made real here |
| HARV | Role-tagged, provenance-locked, leakage-safe pair extraction | NEW; recall_attribution as eval-side labeler (BM) |
| PLAY | Learned per-class playbooks, versioned, canaried, operator-activated | NEW records in SUB; playbooks.py container pattern reused |
| TRAIN | LoRA train/fuse/convert/redeploy/accept orchestration | NEW orchestration; mlx-lm present; llama.cpp convert installed by the phase; redeploy/accept legs exist |
| ROSTER | Seat eligibility/diversity/reliability governance; never truth-weighting | NEW over SUB decision events |

## 7. Runtime execution flow

One hunt (invoked via `python3 -m portal.modules.security.core hunt run …`;
resumable) iterates neighborhoods until plateau or budget. Every stage
transition is a SUB transaction with a decision event; knowledge-bearing
transitions append outbox entries in the same transaction.

```text
0. AUTHORIZE  Operator creates the hunt (scope, budgets, config snapshot).
              SUB acquires the hunt lease; HUNT_CREATED appended.
1. LOAD       SUB.load_context() — cells, known-state, plateaus, cost,
              baselines, open neighborhoods.
2. RECALL     ORG.recall(context) — MANDATORY, in LOOP code. Produces a
              RecallReceipt (query, projection version, candidates,
              exclusions, selected context). No receipt → no targeting.
3. SELECT     TGT: hard eligibility → posterior ROI ranking → target
              neighborhood + cousin hypothesis; TargetDecision recorded
              (candidates, exclusions, factors, recall influence).
4. DIRECT     MUT: typed MutationPlan → code validation (scope, invariants,
              controls, budget) → compiled scenario overlay → Red executes
              UNCHANGED → telemetry ships UNCHANGED → Episode minted
              UNCHANGED (episode.py). Idempotency keys prevent duplicate
              executions.
5. INVESTIGATE  The investigation arm (blue_orchestrate section runners:
              Retriever → Hunter → Expert) over the episode-scoped label-blind
              haystack (spl_backend.query_episode); _cite_or_drop grounding;
              verdict + similarity carry (SectionOutput).
6. GRADE      BR-COUSIN: signature build → candidate union → structural D +
              response axis → grade + decomposition. BR-DRIFT: update
              detection baselines; classify drift; route attacker-evolution
              to BR-COUSIN.
7. GATE       BIN: G-1 → G0 → G1a → G1b → G2 → HEART (G4) → G3 →
              AWAITING_OPERATOR. Any gate fail → terminal outcome recorded
              (DISPROVED/BENIGN/BLOCKED), rationale indexed (negative
              learning).
8. RECORD     SUB: cousin record, gate results, decision events, known-state
              updates, cost ledger. ORG: ALL emissions indexed via outbox
              (universal invariant). HARV: role-tagged pairs appended. PLAY:
              draft updates. SCORE: scoreboard update.
9. STOP?      PLT: statistical exhaustion rule + saturation signal →
              continue / rotate neighborhood / stop. Plateau events recorded.
10. PROMOTE   Operator confirms AWAITING_OPERATOR items → HND emits the
              family package + regression recipe → detection change through
              normal validation (BQ/AZ hold) → deployment + post-deploy
              replay → coverage cell closes in SUB.
```

Infrastructure failure at any point marks the Episode INDETERMINATE (existing
reason codes) and blocks the iteration honestly — never scored as miss or
pass. A crashed iteration re-drives idempotently from the last committed
event; the lease permits recovery.

## 8. Data flow

```text
Red (lab) ──telemetry──> Splunk (portal5_lab, episode_id-indexed)
   │                          │
   └──Episode+evidence_refs──>LOOP──query_episode──> investigation arm
                                 │                      │ verdict+carry
                                 ▼                      ▼
            ORG <─outbox/index─ emissions         BR-COUSIN ─> grade+decomp
            │  ▲                                          │
            │  └────────recall (receipt)──────────────────┤
            ▼                                             ▼
           SUB <────decision events / cost / known-state── BIN/HEART gates
            │                                             │
            ▼                                             ▼
    TGT/PLT/SCORE readouts            HND package → operator → deploy+replay
            │                                             │
            └──HARV corpus ──> TRAIN ──> fleet ──> later hunts (LOOP)
```

Authority: SQLite is the truth; LanceDB is a rebuildable projection whose rows
are never truth inputs until dereferenced and hash-validated against SQL.
Evidence bytes live in the existing capture store, content-addressed.

## 9. State model

**SUB owns** (SQLite WAL, `PORTAL5_HUNT_DIR/hunt_state.db`, default
`/Volumes/data01/portal5_hunt/`; new env convention following
`PORTAL5_LANCE_DIR`): hunts, iterations, cousin_records, candidates +
gate_results, council_packets/opinions/objections/rebuttals, coverage cells,
known_state, detection_baselines, drift_flags, decision_events (append-only,
hash-chained), index_outbox, recall_receipts, decision_impacts, cost_ledger,
plateaus, promotion_queue, playbooks, dataset_versions, trained_models,
roster_records, leases. Provenance on every row (hunt/episode ids, actor,
config/algorithm versions, timestamps). Supersede never deletes. Trust tiers:
`VALIDATED / OPERATOR_CONFIRMED / SUSPECT / IMPORTED_UNVERIFIED /
SUPERSEDED` — only VALIDATED or OPERATOR_CONFIRMED records may change
promotion priors. Retention classes: AUDIT (indefinite), EVIDENCE (bytes per
policy, hashes forever), DERIVED (rebuildable), TRAINING (immutable
artifacts).

**ORG owns** (LanceDB `hunt_memory` under the existing LANCE dir): embedded
canonical hunt records — cousin narratives, kill rationales, benign patterns,
defenses, plateaus, playbook deltas, detection changes, known-bads — with
metadata (record_id, hunt_id, episode_id, kind, trust tier, technique ids,
tactic, field_signature, behavior_sequence, detection_response, grade,
outcome, source hash, ingested_at). The projection is disposable; deletion is
recoverable by replay from SUB.

**Transient:** Episode (existing), MutationPlan, gate results, council
opinions (persisted as records), distance decompositions, hunt context
snapshots.

**Explicitly NOT state:** the doc spine (design facts only); field_journal
(legacy, left alone — a PLAY/HARV *source*, never a Bully store or decision
input); capability_graph (rebuilt on demand as a readout over SUB);
process memory; model context.

Full schemas in `FINAL_DATA_MODEL_DEFENSIVE_BULLY.md`.

## 10. Cousin model (normative)

An attack B is a cousin of attack A when their **BehaviorSignatures** are near
in structural distance and the relationship is defensible per-dimension —
independently of whether our detection catches B.

### BehaviorSignature (versioned)

Constructed in code per evaluated Episode:

```text
signature = {
  action_sequence:     ordered typed verbs/objects (recon→exploit→persist→…),
  event_graph:         entity/event relationships from observed telemetry,
  parameter_families:  normalized numeric/categorical ranges,
  context:             identities, privilege transitions, hosts, topology,
                       protocols, timing,
  artifacts:           tools, hashes, paths, accounts; expected cleanup,
  attack_mappings:     candidate ATT&CK ids + tactic + mapping source/version,
  telemetry_shape:     sourcetypes + field-name histogram + completeness,
  detector_outcomes:   per-detection predicate outcomes, latency, visibility,
  evidence_manifest:   content hashes + completeness score,
}
```

### Candidate generation (retrieval ≠ adjudication)

Candidate references are the union of: semantic top-k in ORG (k=25 default) ∪
ATT&CK neighborhood (≤2 edges via sibling_ids + tactic structure, MITRE MCP
enrichment) ∪ shared event-graph motifs ∪ scenario-family membership.
**Candidate absence never establishes novelty.** A failed candidate source is
recorded as degraded, never treated as an empty result.

### Structural distance (axis 1)

```text
D(A,B) = .30·d_behavior_sequence  (normalized edit distance, step kinds)
       + .25·d_telemetry_event    (field-signature Jaccard + event-graph delta)
       + .15·d_semantic           (cosine over organ embeddings)
       + .15·d_attack_graph       (same-tech 0 / sibling / same-tactic / cross)
       + .15·d_context_topology   (identity/host/protocol/topology delta)
```

Weights live in config; missing dimensions lower confidence — weights are
never renormalized around missing data. **Vetoes (code):** a discriminator
contradiction (spl_detections distinguishing tokens) downgrades SAME
regardless of proximity; SIMILAR/NEW require ≥2 non-semantic channels.

### Relationship grades (axis 1, code-enforced, config-thresholded)

| Grade | Rule (algorithm cousin-v1 defaults; calibration artifact) | Meaning |
|---|---|---|
| SAME | canonical fingerprint match, or D ≤ τ_same (.10) ∧ discriminators match | B is A; known coverage applies |
| SIMILAR | D ≤ τ_similar (.35) ∧ ≥2 non-semantic channels ∧ meaningful delta within the same behavioral objective | B is a variant of A |
| NEW | τ_similar < D ≤ τ_new (.60) ∧ ≥2 non-semantic channels ∧ ≥1 security-relevant delta | Genuinely new, family-anchored |
| DIFFERENT | D > τ_new ∨ no defensible family relation | Not a cousin |
| ANOMALOUS_UNCLASSIFIED | credible anomaly with incomplete/conflicting evidence or no stable family placement | First-class; not a cousin until placed |

### Defense response (axis 2, independent)

Derived in code from the Episode's DetectionCorrelation set + verdict
machinery: **COVERED** (rule fired, in window, right target) / **NEAR_MISS**
(partial: unattributed, out-of-window, or clause-partial) / **MISSED** (rule
absent or silent on real telemetry) / **INDETERMINATE** (telemetry unhealthy
or synthetic — never counted as a miss).

### The product bands

- **Discovery product:** `(SIMILAR | NEW) × (NEAR_MISS | MISSED)` — cousins
  our coverage does not catch, graded by distance.
- **`ANOMALOUS_UNCLASSIFIED × blind`** — the concept's primary product;
  first-class catch (scoreboard catch-set semantics preserved).
- **`SAME × MISSED`** — detection regression: high-priority finding, not a
  discovery.
- **`NEW × COVERED`** — family knowledge gain, not a gap.

**Explanation (mandatory):** every grading emits the per-dimension
decomposition, the vetoes evaluated, the feature-overlap citations (the
U1-preserved layer: embedding *finds*, features *explain*), nearest-known
references, and the response-axis evidence. Example: "SIMILAR × MISSED
(D=0.41): same tactic (attack_graph), shared fields {EventCode,
TargetUserName} (telemetry), persistence reordered before lateral (behavior),
no rule fired (response=MISSED); nearest: T1558.003 record hr-…".

**Anti-astrology controls (all code):** ≥2 non-semantic channels;
discriminator veto; candidate-absence-≠-novelty; semantic distance never alone
produces SIMILAR/NEW; pure D never establishes a coverage claim.

## 11. Spatial-cousin design

Neighborhoods: k-NN around known-bad records in ORG, bounded at D ≤ τ_new. A
hunt picks a neighborhood (TGT), MUT manufactures structurally-valid variants
of its knowns within budget, each manufactured Episode is signatured and
graded; candidates in the product bands enter the bin. Resolved/open cell map
persists in SUB — the next hunt starts from the enriched map. A paired
baseline run is required whenever environment/telemetry equivalence is not
already proven (causal isolation).

## 12. Temporal-cousin design

Per-detection rolling baseline in SUB (window: 20 firings or 30 days default;
minimum-sample floor), keyed by detection id/version + environment fingerprint
+ telemetry schema version. Tracked signals: fire rate, hit latency
(event→index→alert), row shape, clause-level partial satisfaction, sourcetype
completeness. Statistics follow drift_gate's rolling-window machinery (noise
floor, min-baseline, INSUFFICIENT-BASELINE honest flag); model-canary evidence
holds the model constant so a quant/template shift is not misread.

Deterministic attribution order (code; models never choose the cause):

| Signal pattern | Class | Routing |
|---|---|---|
| sourcetype volume collapse / index gaps | TELEMETRY_DEGRADATION | ops alert, not a cousin |
| environment fingerprint / population shift, rules unchanged | ENVIRONMENT_CHANGE | baseline recalibration |
| behavior/fields shifted, technique persists, controls healthy | ATTACKER_EVOLUTION | **temporal cousin** → BR-COUSIN spatial grading + bin |
| stable attack signature + degraded/changed rule | DETECTION_DEGRADATION | tuning lead + lineage event |
| otherwise | UNCLASSIFIED | honest ambiguity |

Alerting: three consecutive breaches, or a configured critical breach.
Version changes (detection/telemetry/environment/algorithm) reset baselines
through explicit supersession with a warm-up period.

## 13. Alert bin (BIN) — promotion design

Append-only state machine (all transitions code, logged as decision events;
changed evidence creates a new alert version and invalidates downstream
passes):

```text
CREATED(suspect) ─G-1 authorization─▶ EVIDENCE_READY(G0) ─▶ REPRODUCED(G1a+G1b)
  ─▶ CAUSALLY_VALIDATED(G2) ─▶ ADVERSARIAL_CLEAR(HEART) ─▶ SOC_VISIBLE(G3)
  ─▶ AWAITING_OPERATOR ─confirm─▶ PROMOTED
                     └─reject─▶ (terminal) DISPROVED / BENIGN / BLOCKED
Any gate fail → terminal outcome with gate + rationale recorded and indexed.
Corrections supersede (SUPERSEDED), never rewrite.
```

- **G-1 Authorization:** approved target scope, mutation class, tool
  allowlist, budgets — recorded before creation. Fail-closed.
- **G0 Evidence integrity:** ≥1 observed-origin evidence ref
  (`telemetry.OBSERVED_EVIDENCE_ORIGINS`); complete manifest with hashes;
  environment/config/model versions; healthy telemetry. Synthetic or
  counterfactual evidence never passes (existing Episode invariant).
- **G1 Reproduction — two legs, both required:**
  - **G1a static:** the candidate signature executes against the replayed
    capture and fires within window on the right target (capture_store replay
    + backend execution; mirrors `derive_detection_status` semantics).
  - **G1b dynamic:** re-execution reproduces the behavior chain and expected
    artifacts — deterministic recipe re-run (`capture_recipes`) where one
    exists, else a directed Red re-run within MUT budget; artifacts verified
    via telemetry contracts. A declared 2-of-3 nondeterministic policy covers
    flaky targets. **A signature hit alone never promotes.**
- **G2 Causality / not-benign:** (a) matched benign/telemetry/environment
  controls do not sustain an alternative explanation; (b) candidate
  discriminators executed against the benign corpus — zero fires (BQ
  preserved); (c) verdict-contract counter-evidence discipline (dual-use ≠
  malicious).
- **HEART (adversarial clearance):** §14.
- **G3 SOC visibility:** the candidate is shipped as a Splunk notable (HEC,
  observed origin); the existing `blue_triage` lane runs against it under a
  queue-load corpus (seeded benign + concurrent alert volume); pass = a
  consumer-side triage report at or above the configured priority (default
  P2) within the configured SLA with content intact. This validates the
  *Bully finding's delivery* to the analyst path — not the missed detector's
  firing. Harness-only visibility fails.
- **G5 Operator promotion:** an authorized operator confirms classification,
  impact, handoff, and permitted feed outputs. Machine-enforced:
  `promote_policy: confirm` + queue actor checks; there is no code path that
  promotes without it.

**Suspect-by-default** lives at the finding level: every candidate enters as a
suspect; silence/incompletion escalates (consistent with the existing
multichain/council fail-safe philosophy, which is verified already
escalate-by-default and is left untouched).

## 14. Self-bullying council (HEART)

```text
candidate + frozen evidence pack (episode refs, gate results, decomposition)
   ↓
N role-typed falsifier seats (isolated; same frozen packet; tasked to BREAK
   it: benign? already-covered? hallucinated evidence? scope/safety?
   reproducibility? — cite specific evidence)
   ↓
opinions (platform contract: findings, strongest_objection, missing_evidence,
   conditions_to_change)
   ↓
durable Objection objects; materiality classified in code against enumerated
   categories (evidence contradiction / covering detection id / benign
   counter-evidence / scope-safety / reproducibility / telemetry health /
   classification / analyst visibility / regression risk)
   ↓
material objection standing? ─YES─▶ rebuttal round (cited counter-evidence;
   │                                 falsification re-pass on the SAME evidence
   │                                 version) ─still standing─▶ BLOCK
   │                                 (or: originating-seat withdrawal, or
   │                                  authorized operator waiver with reason —
   │                                  both audited, visible downstream)
   └─NO─▶ ADVERSARIAL_CLEAR (eligible for the next gate)
```

- Seats: ≥3, role-typed (evidence integrity, causal/benign alternative,
  detection engineering, SOC consumer, safety/scope), **≥2 independent model
  families** (config-enforced diversity), roster from
  `config/security/heart.yaml`; model ids resolved via the backends registry —
  never hardcoded.
- Reuse: platform `council.py` isolation, `parse_opinion`, participation
  accounting, ESCALATE floors. `aggregate_opinions` is **not** used for the
  decision; vote counts are recorded as telemetry only.
- Participation floor is a *validity* floor (BL preserved: non-voters count
  against the roster); sub-floor → review invalid → operator escalation,
  never auto-pass.
- Objections, rebuttals, withdrawals, waivers, and full dissent persist
  permanently (durable records; minority views never dropped).
- The waiver is a separate authenticated operator command — one approval never
  implies another.

## 15. Red interaction model

The bully directs Red through a compiled **MutationPlan**:

```text
MutationPlan = { plan_id, reference_signature/scenario, typed operators +
  parameters, invariants, expected delta + observables, matched controls,
  replay policy, allowed targets/tools, cleanup, risk, approval ref,
  budget class, idempotency key }
```

Code validates the plan (unknown operator, invariant conflict, unauthorized
target/tool, unbounded parameter, missing control, un-collectable expected
evidence → reject; never partially compiled) and compiles it to a scenario
overlay dict (`red_prompt` + `red_order` variants) consumed by the unchanged
`_prepare_scenario`/`set_scenario`/`_run_chain_test` machinery. Operator
confirms any new or widened mutation class. Budgets in code
(`max_variants_per_neighborhood`, `max_perturbation`). Scope guard unchanged
(`perception.assert_in_lab`, 10.10.11.0/24). Off-script emergent behavior
continues to feed via `emergent_gaps`; the evasion-feedback channel
(`blue.py::_build_evasion_feedback`) generalizes to "these detections fired —
vary within validity"; `response_loop`'s reverse generator seeds directed
mutations from existing detections; `capture_recipes` provides deterministic
re-execution. Red execution code is never edited.

## 16. Knowledge organ (ORG)

- One LanceDB `hunt_memory` projection under the existing LANCE dir, sibling
  of the rag/memory stores; those services are untouched.
- Record-level module-internal API: `upsert(record)`, `knn(query, k,
  filters) → [(record, raw_cosine_distance)]`, `recall(context) →
  RecallReceipt`, `index_emissions(iteration)`, `stats()`.
- Embedding via :8917 (batched — CPU sentence-transformers service); rerank
  via :8925 for presentation only (dense fallback); **the cousin metric is
  raw cosine + structured dims, never rerank scores**.
- Trust tiers + provenance classes on every record
  (`hunt_emission`/`operator_assertion`/`external_intel` mapped onto the
  SUB trust tiers); retrieval filters by them; a SAME grading may not rest
  solely on low-authority classes; retrieved content is tagged and can never
  introduce tools, scope, or policy (prompt-injection guard).
- **Invariants (code-enforced by LOOP + the outbox):** (1) pre-hunt recall
  executed and its RecallReceipt persisted before targeting; (2) every
  emission indexed via the transactional outbox before the iteration closes —
  a required dead-lettered index item blocks closure; (3) projection rows are
  dereferenced and hash-validated against SUB before use; stale rows are
  rejected, never trusted.
- Recall influence is recorded: TGT appends a **DecisionImpact** (which
  recalled records changed selection/ranking, how). This is the auditable
  compounding chain: source outcome → typed record → indexed version → later
  recall → recorded decision delta.

## 17. Persistent substrate (SUB)

SQLite (WAL), one migration-managed file per deployment. Access only through
the bully store module (no raw SQL elsewhere). Append-mostly; supersede links
instead of mutation; decision log strictly append-only and hash-chained.
Writes idempotent on natural keys; coordination fields (leases, outbox
attempts, active pointers) use compare-and-swap. One external action per
orchestrator tick; intent persisted before the action, result after, same
idempotency key. Backup = file copy; restore = file replace + integrity
command (`hunt doctor`). Migration-managed schema; code refuses a newer
unsupported schema.

## 18. Compounding model — the six feeds

Compounding = feeding + learning + training, and it must be *traceable*:
observation → capture → validation → persistence → retrieval → decision →
changed behavior → new observation. The falsifiable claim: **hunt N+1 selects
better targets, grades cousins faster, and wastes fewer cycles than hunt N,
and cost-per-promoted-cousin falls over hunt count.**

| # | Feed | Loop closure (retrieve→decide→change) | Instrument proving change |
|---|---|---|---|
| 1 | Semantic hunt memory (ORG) | LOOP recall → TGT/BR-COUSIN use priors | RecallReceipt + DecisionImpact records; recall-hit utilization; neighborhood reuse rate |
| 2 | Known-state DB (SUB) | validated outcomes → versioned priors → TGT deprioritization | waste rate (hunts into known-dead cells) → 0; deprioritized-cell skip rate |
| 3 | ROI/target intelligence | yield/cost observations → posterior updates → next pick | cost-per-promoted-cousin trend (falling) |
| 4 | Training-pair harvest | corpus grows → TRAIN consumes | corpus size/role coverage; dataset versions |
| 5 | Fleet-local fine-tune | trained specialist served → later hunts use it | cousin-bench delta vs non-trained arms; hunt budget delta |
| 6 | Playbook memory | class playbook injected into hunt context | time-to-conclusion / budget use: shaped vs unshaped hunts |

Cross-cutting: provenance = hunt/episode ids on every record; negative
observations first-class; contradiction = supersede with reason codes and a
forced-review link (never averaged away); aging = confidence half-life with
staleness flags (stale entries decay toward neutral and surface as re-test
leads); poisoning resistance = trust tiers + label-blind production +
retrieved-content tagging + the seven-memory-kinds doctrine (no agent
long-term memory at inference); retrieval evaluation = periodic
recall-precision probe against held-out hunts.

## 19. Target selection (TGT)

Hard eligibility first (authorization, target readiness, telemetry health,
resource/lease availability, playbook compatibility) — ineligible cells never
rank. Then:

```text
value(t)    = criticality × technique_relevance
              × lower_bound(uncovered_yield posterior)   # Beta posterior,
              × novelty_confidence × remediation_leverage × realism
priority(t) = value(t) / (estimated_cost_units + ε)
```

Known-state evidence adjusts the uncovered posterior — it is never a second
multiplier; correlated features are recorded separately and never
double-counted. `estimated_cost_units` comes from a versioned pricing profile
over separately measured quantities; **missing material cost blocks the ROI
ranking** rather than becoming zero. Deterministic tie-break: higher
uncertainty reduction → lower cost → stable target id. The full candidate
set, exclusions, raw factors, posterior, recall influence, and the selected
target are persisted as a TargetDecision; declines (including known-benign
declines) carry reasons. Council-dissent uncertainty about a neighborhood is
a recorded novelty-confidence input.

## 20. ROI model

ROI per hunt = risk-reduction value realized / total cost. Value realized = Σ
over promoted cousins of (family coverage closed × asset weight × severity),
pessimistically estimated (minimums — the concept's conservative payout rule).
Reported per hunt and cumulative; informs TGT and the operator; never
auto-continues a hunt.

## 21. Plateau model (PLT)

A neighborhood is exhausted when ALL hold over its valid trials: ≥8 valid
trials spanning ≥2 mutation dimensions; no promoted discovery in the window;
marginal unique defense-response gain < 1; and the upper 95% bound of
discovery yield < `plateau_yield_bound` (default 5%). Blocked/infrastructure-
failed trials never count. Embedding-cluster stability is explicitly NOT a
stop signal. Known-state saturation (resolved/mapped cells) is recorded as a
secondary signal. Detection, telemetry, environment, ATT&CK, cousin-algorithm,
or material evidence version changes reset the neighborhood through an
explicit event. Plateau is neighborhood-local, never system-wide; the record
steers TGT away until known-state changes.

## 22. Cost model

Typed quantities per hunt/iteration: lab minutes, inference calls/tokens/
latency, analyst minutes, replay work, storage, allocated training. A
versioned pricing profile converts them to comparable units. Missing material
measurement is null + quality flag, never zero — and blocks ROI claims.
Headline metric: cost per promoted cousin over hunt number (the falsifiable
economic-compounding claim); secondary: cost per graded candidate, per gated
candidate.

## 23. Detection-engineering exit (HND)

A promoted cousin exits as a versioned **family-generalizing proposal**:

1. Generalized SPL (family-level discriminators) + per-sourcetype variants
   (spl_variants shape); 2. Sigma rule (YAML); 3. required-telemetry
   statement; 4. ATT&CK mapping delta; 5. evidence package (episode refs,
   gate history, council record); 6. reproduction instructions = a new
   **capture recipe** (the regression test, joining the certified corpus);
   7. FP analysis (G2 benign-corpus results); 8. known limitations; 9. IR
   implications (seeded from response_loop's RESPONSE_PRIMITIVES technique
   map); 10. coverage-impact preview (SUB delta); 11. rollout/rollback plan,
   owner, expiry.

Detection-proof legs (made real, replacing growth_loop's placeholders):
**fires-on-attack** (recipe replay), **quiet-on-benign** (benign corpus),
**no-regression** (BQ/AZ + detection lanes green). Portal generates all
deterministically derivable parts (models draft prose where useful); the
`spl_detections.yaml` change is an operator commit through the normal
validation pipeline. HND never auto-deploys; the coverage cell becomes
KNOWN_COVERED only after a deployment receipt **and** a successful
post-deploy Purple replay. Rejected/revised/expired dispositions feed ORG as
negative learning. The handoff is complete when the regression recipe replays
green.

## 24. Training flywheel

```text
HUNT → HARV (role-tagged, quarantined pairs) → DATASET (immutable version;
  family/campaign/time splits; test set frozen pre-harvest; operator release)
  → TRAIN (mlx_lm.lora, host-native, exclusive lock) → FUSE (mlx_lm.fuse)
  → GGUF (llama.cpp convert+quantize — the one installed tool)
  → ollama create (existing import-gguf mechanism)
  → ACCEPTANCE (frozen five-arm suite + intake floors + candidate delta +
    model-canary) → OPERATOR CONFIRM (PENDING_MODEL_VERDICTS flow)
  → role-alias canary → atomic promotion → SERVE → later hunts
```

- Corpus roles: hunter / analyst / disprover / cousin-smeller. Example types:
  evidence→verdict+rationale; objection↔rebuttal exchanges; distance
  judgments with decompositions; kill rationales (negatives first-class).
  Provenance per example (hunt, episode, models, distances, outcome, trust
  tier); label-blind discipline: production grading never reads answer keys;
  eval-side honest-miss labels only via recall_attribution (BM boundary
  enforced by import-scan test).
- Dataset governance: dedup by behavior/evidence fingerprint; splits by
  cousin family/campaign/time with the test set frozen before the harvest
  window; leakage/oracle flags; consent/licensing classification; dataset
  release is a separate operator approval from model promotion.
- **Acceptance gate (frozen five-arm suite):** base / base+retrieval /
  base+playbook / base+retrieval+playbook / specialist+retrieval+playbook.
  The specialist must improve the primary cousin-judgment macro-F1 by ≥5
  absolute points over arm 4 with bootstrap 95% CI above zero, and may not
  regress benign FPR, calibration, tool reliability, known-bad recall, or the
  mandatory security lanes by >2 points. A 30% replay mix of general
  security/benign/known-bad/tool-use examples is the default forgetting
  control. Intake floors (TPS, tool-call reliability) and the general
  security bench apply. Thresholds are frozen before the final held-out
  evaluation and may not be tuned on final results.
- Model tag `<base>-cousin<dataset-version>`; seeds/config/dataset hash
  recorded; prior GGUF retained; rollback = atomic alias re-point. Training
  runs operator-initiated, offline, under an exclusive resource lock, never
  concurrent with a live hunt, initially capped at a configured 9B-class
  ceiling unless capacity is reverified. Training dependencies are
  host-native tooling, isolated from runtime imports. A no-gain result is a
  documented non-serve — an honest success path, not a build failure.

## 25. Model lifecycle

Trained models enter exactly like any candidate (import-gguf → intake floors
→ candidate delta vs incumbent → operator verdict) plus the cousin-bench
delta and dataset-version provenance recorded in the verdict file. Serving a
specialist means pointing the relevant hunt role at it via config — never a
code change. Rollback = re-point the alias; the prior artifact remains.
Production chat serving remains Ollama; MLX is training/conversion
infrastructure only.

## 26. Playbook lifecycle (PLAY)

Learned per-scenario-class instruction sets (recall priorities, deciding
discriminators, common kills, budget shapes), drafted from successful hunt
trajectories; container/validation pattern from playbooks.py. Lifecycle:
`DRAFT → REPLAY_VALIDATED → CANARY → AWAITING_OPERATOR → ACTIVE → RETIRED`
with automatic pointer revert on canary failure. Activation is
operator-confirm-only. LOOP injects the active class playbook into the
investigation arm's context. Effectiveness (budget consumption,
time-to-conclusion) is tracked and fed to ROSTER/TRAIN. Absence of a
playbook for a class is neutral — hunts proceed unshaped, never fabricated.
The static red-side engagement playbooks (`playbooks/security/*.yaml`) are
untouched.

## 27. Roster governance (ROSTER)

Per seat, tracked in SUB from decision events: objection precision/recall
(objections that stood vs rebutted), cousin-call correctness (retrospective
grading vs eventual outcome), citation validity, abstention quality,
latency/cost, independence family. Updated **only from outcomes unavailable
to the reviewer at decision time**. Reliability drives eligibility,
probation, and additional-review requirements — it never weights promotion
truth and never suppresses an objection. A bounded advisory weight ([0.5,
2.0]) may order seat selection; the objection gate structurally ignores it —
the weakest seat's standing material objection blocks. Diversity is enforced
at roster load (≥2 independent model families; capped effective share per
family/correlation group). All changes are decision-logged, operator-visible,
and activation is confirm-only.

## 28. Operator controls

- **Separate authenticated commands** (identity, role, reason, exact
  versions, timestamp) for: hunt authorization; scope/mutation-class
  widening; resume after safety block; material-objection waiver; finding
  promotion; detection-proposal acceptance/deployment ownership; playbook
  activation/override; dataset release; model canary/promotion/rollback
  override; threshold-policy weakening; plateau override. One approval never
  implies another.
- **Promotion queue** (findings/detections/models/playbooks/roster):
  confirm or reject with rationale; rejections are indexed (negative
  learning). Machine-enforced confirm-only (`promote_policy: confirm` +
  actor checks).
- **Hunt config:** budgets (iteration, wall-clock, lab-action, mutation),
  thresholds (τ bands, plateau), cost/pricing, roster, triage SLA.
- **CLI surfaces:** `hunt run|resume|status|doctor`, queue review,
  scoreboard/cost/plateau readouts, organ inspection (read-only).
- **Notifications:** promotion-queue arrivals, honest-BLOCKED states,
  plateau stops, council escalations — via the existing notification
  dispatcher (loop.py pattern), fire-and-forget, non-fatal.
- **Emergency stop:** a config flag halts direction of new Red runs and
  revokes execution leases; in-flight iterations complete their recording
  and stop; evidence is never deleted.

## 29. Deterministic-vs-model responsibility

| Code (deterministic) | Models (reasoning) |
|---|---|
| authorization/scope enforcement; recall/index enforcement; signature construction; distance + grading + vetoes; thresholds; gate logic; state transitions; leases/idempotency; outbox; objection materiality classification; blocking on unrebutted objection; participation floors; budget enforcement; plateau statistics; cost accounting; posterior updates; corpus schema/splits; acceptance gating; alias promotion mechanics | hypotheses; mutation proposals (never raw shell); investigation reasoning; verdict content (grounded); objection + rebuttal content; SPL/Sigma prose drafting; playbook prose; explanation narratives |

A model never emits a state transition; code never invents content. Model
output is schema-validated, cites evidence, and is treated as untrusted.

## 30. Failure semantics

- Lab unreachable / Splunk down / telemetry unindexed: existing reason codes
  → Episode INDETERMINATE; iteration records honest-BLOCKED; never scored as
  a miss or a pass; infrastructure failures are excluded from discovery-yield
  denominators.
- Embedding/reranker down: recall cannot satisfy the mandatory receipt → the
  hunt blocks (no silent lexical grading). Reranker-only failure degrades
  presentation, grading unaffected.
- Candidate-source outage during grading: recorded degraded; classification
  proceeds only if policy-required sources/dimensions remain complete.
- Council seat failure: non-participation counts against the floor (BL);
  sub-floor → review invalid → operator escalation, never auto-pass.
- Model refusal/stall mid-investigation: existing chain semantics (stall
  caps, UNRESOLVED) → candidate stays a suspect, recorded.
- Gate infrastructure failure ≠ gate failure: G1a replay unavailable →
  BLOCKED (retryable), not DISPROVED.
- Index failure: idempotent retry; required dead letter blocks closure with
  operator remediation.
- Crash: lease expires; SUB resumes from the last committed event; no
  duplicate executions or promotions (idempotency keys).
- Train leg with too-small corpus: documented non-build of that leg.
- GGUF-convert tool unavailable at the TRAIN phase: TRAIN halts with an
  explicit blocker; all other feeds continue.
- Training interruption: checkpoint; active alias unchanged.

## 31. Provenance

Every SUB/ORG record carries: ids (hunt, episode, parent records), actor,
trust tier/authority class, model ids involved, distances/decompositions,
gate history, config/algorithm/telemetry/detection versions, timestamps,
content hashes, and supersession links. Council opinions/objections/
rebuttals/waivers persist in full. Promotions append to the existing wiki
provenance ledger (`provenance_ledger.append_entry`) as the operator-facing
audit trail. Detection lineage: every rule traces to the cousin(s) and
hunt(s) that produced it. Decision events are hash-chained.

## 32. Observability

Decision-event log (every gate, grade, block, confirm, kill with rationale);
scoreboard (catch/trust/discovery axes per hunt and cumulative);
plateau/cost readouts (compounding economics); organ stats (record counts by
kind/tier, recall utilization, outbox lag/dead letters); drift/lineage
events; council transcripts; stage latency, lease health, budget use,
resource peaks; feed activation/decision-delta records. Notifications reuse
the existing dispatcher. Structured logs redact secrets/payloads by policy.

## 33. Security boundaries

- Lab scope guard unchanged (`perception.assert_in_lab`, 10.10.11.0/24);
  MutationPlans resolve through the same guard.
- Label-blindness: production grading/grounding/verdicts never read answer
  keys (BM; corpus config contracts unchanged).
- The organ's hunt memory is local-only; no external egress. Retrieved
  knowledge is trust-tagged and cannot introduce tools, scope, or policy.
- Operator confirm required for: detection-library changes, model serving,
  playbook activation, roster activation, objection waivers, scope widening.
- The pipeline's existing guardrails for exec workspaces are unchanged. No
  new MCP tools are required for the core loop; the operator surface is the
  CLI and the promotion queue. MCP independence (Rule 3) respected.
- Secrets never enter prompts, evidence narratives, snapshots, or training
  sets.

## 34. Resource assumptions

- M4 Pro 64GB host; Ollama sole chat tier; council/hunt concurrency bounded
  by backend memory budgets in `config/backends.yaml`; per-turn timeouts;
  pipeline slot discipline. Council seats may serialize under memory
  pressure — correctness over latency.
- Embedding is CPU-pinned — batch upserts; reranker MLX — tolerate fallback.
- Live hunts require the lab (10.10.11.0/24), `SANDBOX_LAB_EXEC=true`, the
  attack image in DinD, and Splunk HEC — all existing operator config.
- Training: LoRA-scale, host-native, exclusive lock, off-hours, 9B-class
  ceiling; corpus sizes are hunt-scale (hundreds to low thousands of pairs).
- **Hunt/bench contention:** LOOP's admission control checks for active
  bench-supervisor/engagement lab locks before lab actions (the nightly
  bench cadence is a real co-tenant of the lab and backends).
- Spine: the new package lands under one new surface entry
  (`unit-surface-sec-bully`); at most one authored design unit per phase.

## 35. Configuration requirements

New `config/security/hunt.yaml` (operator-edited YAML config):

```yaml
organ: { table: hunt_memory, k: 25, trust_classes: [...] }
distance: { algorithm: cousin-v1,
            weights: {behavior: 0.30, telemetry: 0.25, semantic: 0.15,
                      attack: 0.15, context: 0.15},
            tau_same: 0.10, tau_similar: 0.35, tau_new: 0.60 }
mutation: { max_variants_per_neighborhood: 4, max_perturbation: 2 }
budgets: { max_iterations: 20, max_wall_clock_sec: 7200, max_lab_actions: 60 }
plateau: { min_valid_trials: 8, min_dimensions: 2, yield_upper_bound: 0.05 }
costs: { pricing_profile: pricing-v1, rates: {...} }
triage: { priority_threshold: P2, sla_minutes: 30 }
promote_policy: confirm        # machine-enforced
roster_ref: config/security/heart.yaml
```

New `config/security/heart.yaml`: seats (id, role, model alias, family),
participation floor, materiality criteria version. Model ids resolve via the
backends registry — never hardcoded. Effective non-secret config is
snapshotted per hunt. `config/portal.yaml` is not touched unless workspace
addressing proves necessary; derived files regenerate only via
`./launch.sh sync-config` in that case.

## 36. Migration assumptions

Summarized (full table in the MIGRATION doc): Red untouched; Episode contract
preserved; shadow-first roll-out with feature flags (off/shadow/
authoritative) and dual-run disagreement adjudication; section machinery
extracted from blue_orchestrate's bench shell; growth_loop retired after HND
is live; response_loop kept as sibling; continuous_eval retired after
SCORE/PLT readouts; council_agreement/multichain left alone on the legacy
lane; capability_graph gains a SUB-backed loader; the bench harness is
repositioned as the train gate. Every retirement lands only when its
replacement is live (bridge rule); honest-BLOCKED otherwise.

## 37. Final invariants

1. Same/similar/new × near-miss/missed is the product; known-bad catch is
   the floor.
2. `ANOMALOUS_UNCLASSIFIED` is first-class, valued by cousin distance; the
   scoreboard catch/trust semantics hold (BN).
3. Two cousin surfaces — spatial and temporal — both live.
4. Relationship and defense response are independent axes; no blind spot
   manufactures relatedness; no far anomaly is relabeled novelty by distance.
5. Red is directed, never modified.
6. The council falsifies; an unrebutted material objection blocks; votes
   never promote; waiver is a separate audited command.
7. Six feeds all live, each with a recorded later-decision effect (recall
   receipts + decision impacts).
8. Universal indexing (outbox-enforced); mandatory pre-hunt recall
   (receipt-enforced) — in code.
9. Static+dynamic pairing: a signature alone never promotes.
10. Consumer context: SOC visibility is measured in the real analyst path,
    not asserted from the harness.
11. Confirm-only on all consequential promotion — machine-enforced.
12. Code decides, model explains.
13. Honest-BLOCKED over faked-green.
14. Synthetic never passes a promotion gate; label-blind production paths
    (BM); BQ/AZ/BL/BN gates held green.
15. Truth is append-only; conclusions supersede, never rewrite.
16. Training serves only on measured gain over non-trained arms; rollback is
    atomic.
17. The spine gets lighter; runtime hunt state never enters the spine.
18. No unhealthy telemetry becomes a miss; no hunt closes with required
    indexing/cost/outcome missing; no derived projection outranks authority.

## 38. Complete success criteria

The system is complete when ALL hold, demonstrated on its own artifacts:

1. **Hunt loop + cousins:** a hunt consumes a Red Episode, grades cousins
   with the two-axis model and full decomposition, and a second hunt starts
   from the enriched neighborhood (a RecallReceipt + DecisionImpact prove the
   change); a NEW cousin the lexical scorer (U1) graded ~0/NONE is surfaced
   and graded correctly.
2. **Bin + heart:** a manufactured cousin is a suspect by default; passes
   G0 → G1a/G1b → G2 → council (a planted material objection blocks until
   rebutted on the same evidence version; an operator waiver is audited) →
   G3 (triage report within SLA under queue load) → operator confirm →
   PROMOTED; a planted nonsense candidate is DISPROVED with rationale and its
   kill is indexed and demonstrably recalled by a later hunt.
3. **Mutation + drift:** Red produces a budgeted near-neighbor the current
   detections miss and the system alarms; a detection whose firing shifts
   from baseline is flagged, correctly classified through the deterministic
   attribution order, and the attacker-evolution case routes into cousin
   grading.
4. **Selection + stopping:** a far NEW cousin out-values a known-bad catch on
   the discovery axis (trust ordinal untouched); TGT declines a known-benign
   cell with logged reasons; plateau stops a statistically exhausted
   neighborhood and a version change re-opens it; cost-per-promoted-cousin is
   computable per hunt and the series is reportable.
5. **Exit:** a promoted cousin yields a family-generalizing package whose
   three detection-proof legs execute for real, whose regression recipe
   replays green, whose detection change passes BQ/AZ, and whose coverage
   cell closes only after deployment + post-deploy replay.
6. **Flywheel:** the HARV corpus (four roles, adversarial + distance pairs,
   leakage-clean, label-blind boundary intact) versions; playbooks
   accumulate, canary, and measurably shape hunts; a LoRA adapter trains from
   the corpus, fuses → GGUF → `ollama create` → passes the frozen five-arm
   gate → serves on operator confirm (or is honestly declined on no gain);
   ROSTER reweights eligibility on retrospective correctness with the
   objection gate unaffected. **A later hunt uses the trained specialist and
   is measurably better at cousin judgment.**
7. **Compounding proof:** on a recorded hunt series, every feed shows its
   required instrument trend; the learning chain
   (observation→…→changed behavior) is traceable end-to-end for at least one
   decision per feed; the economic series (cost per promoted cousin) falls.

## 39. Architecture diagrams

Component planes: §6. Runtime iteration: §7. Data flow: §8. State machine:
§13. Council pattern: §14. Flywheel: §24. Implementation-level module map,
call paths, and boundary diagrams: `FINAL_ARCHITECTURE_DEFENSIVE_BULLY.md`.

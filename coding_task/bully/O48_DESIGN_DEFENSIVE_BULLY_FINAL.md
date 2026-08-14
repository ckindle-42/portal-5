# DESIGN_DEFENSIVE_BULLY_FINAL

**Authoritative definition of what the Defensive Bully is and what the future
coding-agent session will build.** This document is standalone: a fresh session
should not need the original conversation, the concept blog, or the prior build
program to understand the intended system. Where any document disagrees with
this one on *what* to build, this one wins; the implementation contracts
(`ARCHITECTURE`, `INTERFACES`, `DATA_MODEL`) win on *how*; `MIGRATION` wins on
*transition*; `VALIDATION` wins on *proof*.

Grounded against Portal 5 HEAD `47d3e884` (2026-08-13). Evidence for every
"already exists" claim is in `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md`.

---

## Thesis

Modern offense does not hunt signatures; it hunts the *shape* of a weakness and
chases everything structurally adjacent — found the TIFF-parser OOM, go break
the SFNT parser for the same bug class. Cousins. Same / similar / new /
different. **The Defensive Bully is the mirror: given everything we already
know and detect, surface the cousins we do not** — the near-neighbor attack one
mutation away from a covered one that our detection will miss — grade it by
distance from known, make the fleet try to disprove it before we believe it,
and exit as a fix that closes the whole family.

`ANOMALOUS_UNCLASSIFIED` — "a cousin of X, but not X, and nothing catches it" —
is the **primary product**, not an edge case. Known-bad detection is the floor;
unknown-cousin discovery is the product. The system **compounds**: it feeds,
learns, and trains on its own hunt history so the twentieth hunt beats the
first, including training its own cousin-specialist models on the local fleet.

Two facts about Portal make this buildable rather than speculative: Portal
already computes "red landed but detection missed" as a deterministic Episode
verdict (`FAILED`), and Portal already scores `ANOMALOUS_UNCLASSIFIED` as a
catch. The Defensive Bully **reorients existing correlation and scoring toward
cousin discovery and closes the compounding loop**; it does not invent the core
primitives from nothing.

---

## Goals

1. Consume a purple Episode and decide whether what red landed is SAME / SIMILAR
   / NEW / DIFFERENT / ANOMALOUS_UNCLASSIFIED relative to everything known,
   using a multi-axis, code-computed cousin distance.
2. Treat a landed cousin our detection misses as a **suspect finding** that must
   earn promotion through executable gates (has-evidence → replay-reproduces →
   not-benign → analyst-visible).
3. Make the fleet **adversarially try to disprove** each finding; block any
   promotion while an unrebutted material objection stands.
4. **Direct red** to manufacture structurally-valid cousins (perturbed
   params/timing/sub-technique/artifacts) without modifying red's execution.
5. Detect **temporal cousins**: a detection drifting from its own firing
   baseline (a technique that evolved into a cousin of itself).
6. Exit a promoted cousin as a **family-generalizing detection package**
   (generalized Sigma + correlation + log-source + ATT&CK/IR deltas), operator-
   confirmed into the live detection set.
7. **Compound through six feeds**: semantic hunt memory (ORG), known-
   benign/covered/dead-cell DB, ROI target intelligence, training-pair harvest,
   fleet-local fine-tune, and learned per-scenario playbooks.
8. **Train** cousin-specialist models on the harvested corpus, fuse → GGUF →
   `ollama create` → acceptance-gate → operator-confirm serve, and demonstrate a
   later hunt is measurably better because of it.
9. Prove, on the program's own artifacts, that hunt N+1 is smarter and the fleet
   sharper than hunt N — both technically (more/faster cousins) and economically
   (falling cost-per-cousin).

## Non-goals

- Not a rewrite of red. Red is the means and is left alone.
- Not a general SOC platform, not a replacement for Splunk/OWUI, not cloud
  inference, not an external agent framework (CLAUDE.md rules stand).
- Not a second knowledge store: the doc spine stays design-facts-only; the
  knowledge organ is the auto-fed hunt memory.
- Not a coverage-completeness scoreboard: first-in-class cousin discovery is the
  product, not "% of known TTPs detected."
- Not an always-on daemon in the initial build (the loop is *built to allow*
  one; the daemon is a listed extension).
- Not an MVP or a vertical slice: this is the complete design; phases are build
  order only.

---

## Core principles

- **Code decides, model explains.** Distance, gates, quorum, objection-material-
  ity, verdicts, and never-PROVEN are deterministic code. Models generate
  hypotheses, objections, rationales, and content. (Portal already enforces this
  in the council and the Episode.)
- **Suspect until proven.** Findings begin as suspects and earn promotion.
- **Storage is not learning.** A feed counts only if a later run *retrieves* it
  and *changes behavior* because of it; every feed must demonstrate that.
- **Prompting is not enforcement.** Mandatory pre-hunt recall, universal
  indexing, unresolved-objection blocking, analyst-visibility, and promotion
  gates are enforced in code/tools, not model instructions.
- **Structural validity, not randomness.** Mutation stays inside the attack
  grammar and perturbs the payload.
- **Negative results matter.** Benign, already-covered, and dead cells are
  recorded and multiplicatively steer future hunts away from waste.
- **Honest-BLOCKED over faked-green.** A killed cousin is a correct non-finding;
  a retired path with no replacement blocks honestly; a too-small corpus is a
  documented non-build, not a skipped feed.
- **Operator confirms consequential promotion.** `PROMOTE_POLICY=confirm` for
  findings, detections, trained models, roster changes, and playbook promotions.
- **The council is adversarial, not democratic.** Independent falsification, not
  majority vote.
- **Honor the seven memory kinds.** Especially: no agent long-term memory at
  inference; production cousin-grading stays label-blind.

---

## System boundaries

```
                 ┌─────────────────────────── OPERATOR ───────────────────────────┐
                 │        confirms: findings · detections · models · roster · playbooks
                 ▼
   ┌────────────────────────── DEFENSIVE BULLY (new brain/heart) ──────────────────────────┐
   │  TGT → LOOP → (MUT ⇄ RED) → EPISODE → BR-COUSIN / BR-DRIFT → BIN(G0–G3) → HEART        │
   │        ↘ SUB (persistent state)   ↘ ORG (semantic hunt memory)                          │
   │  promoted → HND (family-generalizing detection)                                         │
   │  every emission → HARV → CORPUS → TRAIN → FUSE → GGUF → ACCEPT → SERVE                   │
   │  PLAY (learned playbooks)   ROSTER (council learning)   PLT (plateau/cost)               │
   └──────────────┬──────────────────────────────────────────────────────────────┬──────────┘
                  │ directs which attack (scenario dicts)                          │ consumes
                  ▼                                                                │
   ┌────────── RED (means — LEFT ALONE) ──────────┐                                │
   │  SCENARIOS grammar · exec_chain executor ·    │  lands telemetry              │
   │  lab.py (Proxmox snapshot/restore/dispatch)   │ ─────────────────────────────►┘
   └───────────────────────────────────────────────┘
```

- **Red/Bully boundary:** the Bully supplies/perturbs **scenario definitions**
  (data); red's executor and lab lifecycle are never modified. The Episode is
  the one-way contract from red-side telemetry into the Bully.
- **Platform boundary:** the Bully lives under `portal/modules/security/` and
  reuses platform primitives (council, agent loop, ORG MCP, model CLI) through
  their existing contracts; it never imports OWUI internals and respects the
  MCP-isolation rule.
- **Operator boundary:** every consequential promotion halts for confirmation.

---

## Final architecture — component model

Existing abstractions are retained where they remain the best boundary; renamed
only where a better one emerged. Disposition tags per `MIGRATION`.

| Comp | Name | Role | Primary existing basis | Disposition |
|---|---|---|---|---|
| **SUB** | Persistent substrate | cross-hunt state: coverage cells, known-benign/covered/dead-cell DB, plateau state, cost ledger, decision log | `investigation` store, `capability_graph` entities | REUSE seed + EXTEND (persistence) |
| **ORG** | Cousin-space organ | semantic hunt memory; distance = cousin metric; mandatory pre-hunt recall + universal indexing | `research/tools/rag_mcp` (MLX+LanceDB+rerank) | RETROFIT (corpus + enforcement) |
| **BR-COUSIN** | Spatial cousin engine | SAME/SIMILAR/NEW/DIFFERENT by composite distance; feature-overlap explanation | `unknown_defense` grade space | RETROFIT onto ORG |
| **BR-DRIFT** | Temporal cousin engine | per-detection firing-baseline drift + 4-way signal disambiguation | `drift_gate` rolling-baseline engine + `model-canary` | RETROFIT (retarget series) |
| **LOOP** | Hunt loop | TGT→direct RED→consume Episode→BR grade→BIN→HEART→alarm/kill→write SUB/ORG→PLT | `loop.py` (+`loop_cli`) + `platform.agent` decide/rank | RETROFIT/COMPOSE |
| **BIN** | Alert bin | suspect-until-proven G0–G3 (real gates) | new (over `growth_loop` shape) | NEW gates |
| **HEART** | Self-bullying council | fleet tries to disprove; unrebutted material objection ⇒ BLOCK | `council.py` `aggregate_opinions` + `council_agreement` | REUSE + objection gate |
| **MUT** | Red cousin-generator | structurally-valid scenario perturbation + mutation budget | `SCENARIOS` grammar + `emergent_gaps` + `response_loop` reverse-gen | REUSE + NEW generator |
| **SCORE** | Distance-graded scoring | far NEW cousin ≥ known-bad; ANOMALOUS full catch | `notify_scoreboard` + `scoring.py` | REUSE + EXTEND (distance) |
| **TGT** | Target selection | risk-reduction/cost ranking; deprioritise known cells | new (over `capability_graph` gaps + SUB) | NEW |
| **PLT** | Plateau + cost meter | stop on flat useful-discovery rate; cost-per-cousin | `drift_gate` baseline engine (reused) | NEW (reuse engine) |
| **HND** | Detection-engineering exit | family-generalizing detection package | new sibling to `response_loop`; `growth_loop.prove_draft` = proof | NEW sibling |
| **HARV** | Training-pair harvest | role-tagged jsonl from hunts/council/cousin judgments; label-blind | new; `recall_attribution` = honest-miss labeler | NEW (reuse labeler) |
| **TRAIN** | Fleet-local fine-tune | LoRA→fuse→GGUF→accept→serve | `mlx_lm.lora`/`fuse` (present) + `models.import-gguf` + `candidate_eval` | RETROFIT + NEW (GGUF convert) |
| **PLAY** | Playbook memory | learned per-scenario-class instruction sets | `playbooks.py` (authored, wired) | RETROFIT (add learning) |
| **ROSTER** | Council learning | retrospective seat weighting; anti-correlation | `council` participation model | NEW (over council) |

## Component responsibilities (contract-level; full detail in INTERFACES)

- **SUB** owns all cross-hunt persistent state. Read before every hunt, written
  after. Append-only decision log; superseding (not deleting) records; honors
  the seven-memory-kinds taxonomy.
- **ORG** owns semantic hunt memory. Enforces, *in the tool*, that a hunt cannot
  start without a recall query and cannot finish without indexing every emission
  (positive and negative). Distance in ORG feeds BR-COUSIN.
- **BR-COUSIN** computes the composite distance and the SAME/SIMILAR/NEW/DIFF/
  ANOMALOUS band, and emits a human-readable explanation citing the axis and
  overlapping features that made the call.
- **BR-DRIFT** maintains a rolling firing-baseline per (technique, detection) and
  classifies drift as attacker-evolution / telemetry-failure / environmental /
  detection-degradation.
- **LOOP** orchestrates one hunt end-to-end within playbook scope, budget, stop
  conditions, and hard caps; checkpoint/resume; notify on escalate/stuck/
  complete with a resume command.
- **BIN** holds a finding as SUSPECT and runs G0–G3; only an all-gates-pass
  finding is promotable, and only then subject to HEART and operator confirm.
- **HEART** runs the isolated fleet council, applies the deterministic objection
  gate, preserves dissent and disagreement-as-novelty.
- **MUT** turns a chosen known reference into structurally-valid cousin scenario
  dicts within the operator's mutation budget.
- **SCORE** assigns distance-weighted value so novelty is rewarded without ever
  demoting ANOMALOUS below CONFIRMED.
- **TGT/PLT** choose where to hunt and when to stop, and meter cost.
- **HND** assembles the family-generalizing detection package and proves it.
- **HARV/TRAIN/PLAY/ROSTER** are the compounding organs (feeds 4–6 + council
  learning).

---

## Runtime execution flow

```
1. TGT reads SUB (coverage cells, known-benign/covered/dead, prior yield, cost)
   and ORG (neighborhood density) → ranks cousin-neighborhoods by
   risk-reduction/cost → picks the next neighborhood (declines known-benign).
2. LOOP loads the class PLAYbook (scope/budget/stop) and, via platform.agent,
   forms the hunt goal. Mandatory ORG recall runs here (tool-enforced).
3. MUT turns the chosen known reference into N structurally-valid cousin
   scenario dicts (within mutation budget).
4. LOOP directs RED to execute a cousin scenario (unmodified executor + lab).
   Red lands telemetry; the purple path builds the deterministic EPISODE.
5. BR-COUSIN grades the Episode's distance from the nearest known reference in
   ORG (SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS). BR-DRIFT updates the firing
   baseline and flags temporal drift.
6. If red landed and detection missed (Episode FAILED) or a NEW/ANOMALOUS cousin
   surfaced → a SUSPECT finding enters the BIN.
7. BIN runs G0 (has-evidence) → G1 (replay-reproduces in clean snapshot,
   static+dynamic) → G2 (not-benign) → G3 (analyst-visible in Splunk/console).
   Any gate fail → recorded honest non-finding (negative result → SUB feed 2).
8. HEART: the fleet council independently tries to disprove the promotable
   finding. Unrebutted material objection → BLOCK. Otherwise eligible.
9. SCORE assigns distance-weighted value; scoreboard records the catch.
10. Operator confirms. On confirm → HND assembles the family-generalizing
    detection package and proves it (fires-on-attack / quiet-on-benign /
    no-regression). Operator confirms deployment.
11. LOOP writes outcome + cost to SUB, indexes every emission into ORG (feed 1),
    updates known-cells (feed 2), and HARV extracts training pairs (feed 4).
12. PLT checks the neighborhood's useful-discovery rate; on plateau, records it
    and steers TGT away. Cost-per-cousin updated.
13. Offline: HARV corpus → TRAIN (LoRA) → FUSE → GGUF → ACCEPT (candidate_eval +
    canary) → operator-confirm SERVE (feed 5). PLAY refines the class playbook
    from outcomes (feed 6). ROSTER reweights seats on retrospective correctness.
14. A later hunt (step 1) now starts from richer ORG/SUB, a sharper playbook,
    and possibly a trained cousin-specialist seat — and is measurably better.
```

## Data flow

Red telemetry → **Episode** (deterministic correlation) → **BR** (distance) →
**BIN** (gated finding) → **HEART** (objection-gated) → **SCORE/scoreboard** →
operator → **HND** (detection package). In parallel every emission → **ORG**
(indexed) and **SUB** (state + decision log + cost), and → **HARV** (training
pairs). SUB/ORG/PLAY/trained-model close back onto TGT/LOOP for the next hunt.

## State model

Persistent (SUB, owns lifecycle): coverage cells, known-benign/covered/dead-cell
records, temporal firing-baselines, plateau records, cost-ledger entries,
decision-event log, target scores, promotions, supersessions. Semantic (ORG):
embedded hunt emissions (episodes, findings, verdicts, objections, cousin
judgments, plateaus). Transient (per hunt): EngagementState/checkpoint, council
opinions, candidate scenario dicts. Case-scoped (investigation store):
per-investigation notebook + immutable evidence. All records carry provenance;
none are deleted, only superseded.

---

## Cousin definition (the central computation)

A finding is compared to its nearest known reference across five weighted axes,
each contributing separable value (rationale in `REVIEW` §H):

1. **Behavioral-sequence distance** — ordered technique/tool sequence edit
   distance (from `red_order` + observed order in the Episode).
2. **ATT&CK-graph distance** — technique/sub-technique/tactic lattice distance
   (MITRE MCP :8929 + `capability_graph` tags). Sibling sub-techniques are near.
3. **Telemetry-shape distance** — over the `DetectionCorrelation` signature (log
   sources/event codes, row-count band, within-window, field-set overlap).
4. **Detection-response distance** — how the existing detection responded
   (fired-attributed / fired-unattributed / partial / silent). *The gap axis.*
5. **Semantic distance** — ORG embedding + rerank over the NL description.
   *Finds candidates; the structured axes grade them.*

Composite `D = Σ wᵢ·dᵢ`, weights in config. **Classification is code-
deterministic:**

- **SAME** — `D≈0` on behavioral+ATT&CK+telemetry; detection fires the same way.
- **SIMILAR** — near ATT&CK/behavioral, small telemetry delta, detection still
  fires (a *covered* cousin).
- **NEW** — near ATT&CK/behavioral **and** large detection-response distance
  (fires weaker/differently/silent) — *a cousin our detection misses.* **Product.**
- **DIFFERENT** — far on ATT&CK+behavioral+semantic (unrelated).
- **ANOMALOUS_UNCLASSIFIED** — landed signal resisting all-axis classification
  (I8 unease): full success, valued by distance, never dropped.

Meaningful novelty vs. arbitrary semantic distance is settled by the
**detection-response axis**: large semantic distance with no change in whether/
how we catch it is DIFFERENT, not NEW.

## Spatial-cousin design

BR-COUSIN: embed the finding's Episode+correlation into ORG, retrieve k nearest
known references, compute composite `D`, assign the band. `unknown_defense`'s
feature-overlap becomes the *explanation* (which features overlapped, which
known unit matched); the embedding+rerank does the *finding*; the structured
axes do the *grading*.

## Temporal-cousin design

BR-DRIFT: rolling baseline per (technique, detection) over firing signals
(confidence, latency, event-population, sequence length, partial-rule fraction,
telemetry-source presence), using the reused `drift_gate` statistical engine.
Classify: **attacker-evolution** (weaker/later/partial, sources intact, baseline
stable) = temporal cousin; **telemetry-failure** (source dropped to zero);
**environmental** (baseline shift across all detections); **detection-
degradation** (rule/version changed — a lineage event). `model-canary` holds the
model constant so a quant/template shift is not misread as attacker evolution.

## Alert / promotion design

Suspect-until-proven; four real gates:
- **G0 has-evidence** — real `evidence_refs`, `used_synthetic=False`, finding
  cites them.
- **G1 replay-reproduces** — re-run the cousin against a clean Proxmox snapshot;
  observe the *same* correlation shape (static signature match alone is only
  G0). Static+dynamic pairing.
- **G2 not-benign** — evaluated against the benign corpus (check BQ home).
- **G3 analyst-visible** — proven to surface as a Splunk notable in the real
  console under queue load, not the harness god-view.
Any fail → honest non-finding, recorded as a negative result (feed 2). Only
all-pass findings reach HEART and operator confirm.

## Self-bullying council (HEART)

Reuse `council.py`: isolated seats, roster-denominator quorum, ESCALATE/ABSTAIN
first-class, code-decides/model-explains. Seats are tasked to *break* the
finding. Add a deterministic **objection gate** beside `aggregate_opinions`: a
seat's `strongest_objection` is *material* if it names missing evidence or a
condition-to-change unmet by the finding's evidence (checked in code against
`evidence_refs`/correlation); **any unrebutted material objection ⇒ BLOCK**,
regardless of votes. Keep `council_agreement`'s detection↔review translation and
its disagreement→ANOMALOUS (novelty) mapping.

## Red interaction model

MUT produces scenario dicts (`red_order`/params/prompt/ground-truth); the
executor and lab are untouched. LOOP passes a scenario dict to the existing
runner (as `candidate_eval` already does). `emergent_gaps` continues to harvest
accidental off-script cousins; `response_loop`'s reverse generator seeds directed
mutations from an existing detection.

## Mutation model

Structural-validity fuzzing of the attack grammar. Dimensions: parameters,
timing, step ordering, command form, process/parent-child, identity/host,
protocol, artifact/encoding, and **adjacent sub-technique** (highest yield —
"same class, different parser"). Operator **mutation-budget** dial bounds how
many dimensions and how far red wanders.

## Knowledge organ (ORG)

`rag_mcp` retrofitted: MLX mxbai embed (:8917) → LanceDB vector + tantivy FTS →
Qwen3 reranker (:8925). Corpus = hunt emissions, not docs. Two invariants
enforced in the tool: **mandatory pre-hunt recall** and **universal indexing**
(every emission indexed, positive and negative). Retrieval feeds the hunt loop's
context only — never an implicit model long-term memory (seven-kinds rule #7).

## Persistent substrate (SUB)

One evolving store seeded from the investigation `EvidenceStore`/`CaseNotebook`
and `capability_graph` entities, extended to cross-hunt persistence: coverage
cells, known-benign/covered/dead-cell DB, temporal baselines, plateau state,
cost ledger, decision-event log. Provenance via `SourceAuthority` + supports/
contradicts; supersession via `supersede`. Read before every hunt, written after.

## Compounding model

`observation → capture → validation → persistence → retrieval → decision →
changed behavior → new observation` closed and *demonstrated*: a second hunt
must provably behave differently because of the first (neighborhood pick,
suppressed dead cell, or a trained seat). Both technical compounding (more/
faster/further cousins) and economic compounding (falling cost-per-cousin) are
success criteria, not assertions.

## Six feeds

1. Semantic hunt memory (ORG) — retrofit + enforce.
2. Known-benign/covered/dead-cell DB (SUB) — new; multiplicative steering.
3. ROI/target intelligence (TGT) — new.
4. Training-pair harvest (HARV) — new; reuse `recall_attribution`; label-blind.
5. Fleet-local fine-tune (TRAIN) — retrofit tooling + narrow new (GGUF convert).
6. Learned playbook memory (PLAY) — retrofit `playbooks.py` + learning leg.
Feeds 1–3 make the hunt smarter; 4–6 make the fleet sharper.

## Target selection / ROI / plateau / cost

- **TGT**: rank cousin-neighborhoods by risk-reduction-value / test-cost; inputs:
  asset criticality, ATT&CK relevance, uncovered risk, cousin novelty, prior
  miss-rate, detection confidence, and test cost; multiplicatively deprioritise
  known-benign/covered/dead cells.
- **PLT**: a neighborhood is exhausted when the rate of new gap-classification
  transitions per unit cost falls below a floor for a window (measured with the
  drift baseline engine) — not merely when embeddings stop clustering.
- **Cost**: SUB cost ledger (compute + lab-hours + analyst-effort per cousin
  found), shown falling over the program's own runs.

## Detection-engineering exit (HND)

A promoted cousin exits as a family-generalizing package: generalized Sigma,
SPL/correlation change, required log-source onboarding, ATT&CK mapping, evidence
+ reproduction, false-positive analysis (benign corpus), known limitations, IR
implications, a regression test, coverage-impact delta. Portal assembles it
automatically; `growth_loop.prove_draft`'s three legs (fires-on-attack / quiet-
on-benign / no-regression) prove the generalized rule; **operator confirms**
deployment. `response_loop` (response IR + reverse-gen + intake) is kept as a
sibling.

## Training flywheel / model lifecycle

`HARV corpus (role-tagged jsonl) → mlx_lm.lora (adapter) → mlx_lm.fuse (fused
HF) → llama.cpp convert_hf_to_gguf + quantize (the one new tool) → ollama create
(Modelfile) → candidate_eval delta-vs-incumbent + model-canary → operator-
confirm serve`. Compare specialist vs base / base+ORG / base+playbook /
base+ORG+playbook / trained — keep training only where it beats retrieval+
playbook measurably. Dataset + model versioned; rollback = re-point the fleet
config to the prior model; catastrophic-forgetting guarded by the acceptance
gate (a specialist that regresses general competence is declined).

## Playbook lifecycle

Authored YAML playbooks (scope/budget/stop/escalate) gain a learning leg:
outcomes per investigation class refine the instruction set (which mutations
yielded cousins, which cells were dead), versioned and operator-confirmed before
they shape a small trained model's runtime.

## Roster / council-learning

Retrospective weighting: seats whose objections *held* (correctly blocked a
finding that later proved wrong, or correctly cleared one that proved right)
gain weight; consistently-wrong seats lose it — floored so none reaches zero.
Correlated seats (shared base model) form a group capped at a configured share
of effective weight. Reweighting never overrides a correct minority dissent.

## Operator controls

Confirm gates on: finding promotion, detection deployment, trained-model serve,
roster changes, playbook promotion. Dials: mutation budget, ORG recall depth,
council roster + quorum, plateau floor, TGT weights, training cadence.

## Deterministic-vs-model responsibility

Deterministic (code): Episode correlation + verdict, cousin distance +
classification, BIN gates, objection materiality + quorum, SCORE value, TGT
ranking, PLT thresholds, cost accounting, never-PROVEN, label-blind boundary.
Model: red attack execution, blue analysis narrative, council objections +
rebuttals, cousin explanations, generalized-rule drafting, playbook prose.

## Failure semantics

Every stage fails **honest-BLOCKED**, never faked-green: no evidence → G0 fail
(non-finding); replay fails → G1 fail; council can't reach quorum → ESCALATE;
unrebutted objection → BLOCK; corpus too small → documented non-build; GGUF
convert unavailable → TRAIN halts with a clear blocker, feeds 1–4/6 continue;
lab/telemetry failure → INDETERMINATE (never PROVEN, never DISMISS). Notify
carries a resume command.

## Provenance / observability / security boundaries

Provenance: `SourceAuthority` + supports/contradicts on evidence; decision-event
log records every promotion/kill/supersession with its inputs. Observability:
scoreboard (catches by distance), cost ledger (cost-per-cousin), plateau
records, drift/lineage events, council transcripts. Security: red stays in the
isolated lab; MCP isolation preserved; no cloud egress; operator owns noise-
producing actions; ORG retrieval never becomes inference-time long-term memory.

## Resource considerations

Single 64 GB Mac Mini, Ollama sole chat backend (~15.5–20 GiB single-model cap).
Bound council roster and serialize reviewer calls under a memory cap; run
training offline/off-hours (never concurrent with a live hunt); ORG embed/rerank
on MLX (:8917/:8925) off the chat path.

## Configuration requirements

Under `config/` (via `config/portal.yaml` single source of truth where fleet/
workspace-scoped): cousin-axis weights + band thresholds, mutation budget, ORG
recall depth + index policy, council roster/quorum/objection policy, TGT weights,
plateau floor + window, cost model, training cadence + acceptance thresholds,
PROMOTE_POLICY=confirm. No hardcoded model names, ports, or counts.

## Migration assumptions

Red untouched; the bench path is repositioned as the model-acceptance harness
(not deleted); old B/P orchestration retires component-by-component behind a
replacement bridge (the Bully consumes the same Episode red produces). Details
in `MIGRATION_DEFENSIVE_BULLY.md`.

---

## Final invariants

- Same/similar/new is the product; known-bad catch is the floor.
- `ANOMALOUS_UNCLASSIFIED` is first-class, valued by distance; never demoted
  below CONFIRMED (check BN).
- Two cousin surfaces — spatial (BR-COUSIN) and temporal (BR-DRIFT) — both in
  scope.
- Red is the means and is left alone; directed via scenario data only.
- The council is adversarial: unrebutted material objection ⇒ BLOCK.
- Six feeds all built and demonstrated; storage that does not change behavior is
  not a feed.
- Pre-hunt recall + universal indexing enforced in the tool.
- Static+dynamic pairing for G1; analyst-visible G3 is a real gate.
- Synthetic never PROVEN; production cousin-grading label-blind (BM).
- Code decides; model explains. Operator confirms consequential promotion.
- Honor the seven memory kinds; hold BQ/AZ/BL/BM/BN/BR/AW green.

---

## Complete success criteria

The Defensive Bully is complete when, on the program's own artifacts:

1. A hunt consumes a purple Episode, BR-COUSIN grades cousin distance in ORG, a
   second hunt starts from the enriched neighborhood, and a NEW cousin surfaces
   that the old token-overlap matcher scored ≈0.
2. A manufactured cousin is suspect-by-default, gated G0–G3 (incl. static+dynamic
   and analyst-visible), and the fleet council kills or promotes it via
   (un)rebutted material objection.
3. Red produces a near-neighbor blue misses within budget and the system alarms;
   BR-DRIFT catches a detection firing differently from its baseline and
   correctly classifies it as attacker-evolution vs. the other three causes.
4. A far NEW cousin scores ≥ a known-bad catch; TGT declines a known-benign cell;
   cost-per-cousin is shown falling; PLT stops an exhausted neighborhood.
5. A promoted cousin exits as a family-generalizing detection that fires on the
   attack, stays quiet on benign, and breaks no existing detection.
6. The flywheel closes end-to-end: HARV builds a role-tagged corpus (incl.
   adversarial + distance pairs); a fleet-local LoRA trains from it, fuses →
   GGUF → `ollama create` → passes the acceptance+canary gate → serves on
   confirm; PLAY accumulates and shapes a small-model run; ROSTER reweights on
   retrospective correctness; and a **later hunt using the trained seat is
   measurably better at smelling cousins** than the same hunt without it.

Known-bad detection is the floor. Unknown-cousin discovery is the product.
Spatial and temporal cousins both matter. Structurally-valid mutation matters.
Consumer-context detection matters. Negative results matter. The council is
adversarial. Compounding must alter future behavior. Training must demonstrate
improvement. Models reason; code enforces; operators confirm.

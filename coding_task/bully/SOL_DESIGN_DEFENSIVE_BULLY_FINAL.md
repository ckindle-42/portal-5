# Defensive Bully — Final Authoritative Design

## Thesis

Defensive Bully is a persistent, bounded defensive-hunting system that discovers attacks structurally adjacent to known procedures but not adequately covered by current defenses. It executes only authorized mutations through Portal Red, captures real evidence through Purple, tries to disprove its own findings, promotes only evidence-backed discoveries with operator confirmation, and turns every result into measurable changes to future recall, targeting, playbooks, detection engineering, evaluation, and specialist models.

Known-bad detection is the floor. Unknown-cousin discovery is the product.

## Goals

1. Discover spatial and temporal cousins that are `NEAR_MISS` or `MISSED` by the current defense stack.
2. Establish structural relationship and causal defense response with reproducible evidence.
3. Reject benign, different-family, telemetry-broken, environment-changed, and irreproducible hypotheses early.
4. Create family-generalizing detection proposals, not one-sample signatures.
5. Make positive and negative outcomes alter later decisions through six closed feeds.
6. Improve a specialist reasoning role only when controlled evaluation proves gain over retrieval and playbook alternatives.
7. Preserve Portal’s security, evidence-truth, resource, model-serving, and operator-approval boundaries.

## Non-goals

- Autonomous exploitation of targets outside an approved lab scope.
- Automatic production deployment of detections, playbooks, or models.
- Replacing Portal Red, the inference router, generic research RAG, conversation memory, Splunk, or detection-engineering ownership.
- Treating embedding similarity, ATT&CK labels, model votes, or generated prose as proof.
- Training during a live hunt or serving MLX-trained weights directly as a production chat backend.
- Claiming every anomaly is a cousin.

## Core principles

- Models propose, interpret, challenge, and explain. Deterministic code validates scope, computes state, applies thresholds, and authorizes transitions.
- Evidence is immutable; conclusions are superseded, never rewritten.
- Every claim cites versioned inputs and algorithm/config versions.
- A semantic neighbor is a candidate, not a cousin.
- Relationship and defense response are independent axes.
- Synthetic evidence can develop and test plumbing but can never prove a real miss.
- Material objections veto promotion until resolved or explicitly waived by an authorized operator.
- Every consequential boundary is operator-confirmed.
- Compounding means later behavior changed and the causal record proves why.
- Fail closed on ambiguity involving scope, evidence integrity, persistence, telemetry health, or authority.

## System boundaries

Defensive Bully is a security-core subsystem. Its authoritative state is local structured storage; its evidence references Portal capture artifacts. It calls existing Red/Purple APIs, platform agent-loop primitives, configured inference roles, embedding/reranking services, Splunk/analyst delivery adapters, and model lifecycle commands. Thin security CLI and MCP surfaces expose operator actions. No business state lives in the inference pipeline, MCP process memory, generic RAG, or model context.

## Final architecture

```text
Operator / Scheduler
        |
        v
Security Bully Orchestrator -----> Authoritative SQLite WAL
        |                              | decision events + outbox
        | recall                       v
        +----------------------> LanceDB semantic projection
        |
        +--> Target/ROI --> MutationPlan validator
        |                         |
        |                         v
        |                    Existing Red executor
        |                         |
        |                         v
        +<---- Purple Episode + capture/telemetry evidence
        |
        +--> Signature/Cousin + Temporal engines
        +--> Promotion bin --> Adversarial council
        +--> SOC visibility adapter --> Operator confirmation
        |
        +--> Detection proposal / Harvest / Playbook proposal
                                  |
                                  v
                       Offline training and acceptance
                                  |
                                  v
                     GGUF -> Ollama role deployment
```

## Component model

The component names remain stable so implementation and validation can refer to one shared vocabulary.

## Component responsibilities

| Component | Responsibility |
|---|---|
| **SUB — orchestrator** | Own recovery-safe hunt lifecycle, budgets, locks, stage transitions, retries, and cancellation. |
| **ORG — knowledge organ** | Emit typed knowledge, index through outbox, recall before selection, record influence, handle contradiction/supersession. |
| **BR-COUSIN** | Build versioned behavior signatures, generate candidates, compute distance, classify relationship and defense response. |
| **BR-DRIFT** | Maintain matched temporal baselines, detect change, and assign deterministic cause categories. |
| **LOOP** | Execute bounded grounded inner actions using platform agent contracts; never own business truth. |
| **BIN** | Enforce promotion states and gate evidence. |
| **HEART** | Run independent adversarial reviewers and manage durable objections/rebuttals. |
| **MUT** | Propose, validate, and compile typed structural mutations to Red orders. |
| **SCORE** | Compute calibrated target value, uncertainty, measured cost, and outcome value. |
| **TGT** | Filter eligible coverage cells and rank neighborhoods. |
| **PLT** | Stop/reset exhausted neighborhoods using statistical rules. |
| **HND** | Produce evidence-linked detection-engineering proposals and ingest disposition/deployment results. |
| **HARV** | Derive provenance-locked examples from completed cases without evaluation leakage. |
| **PLAY** | Propose, canary, version, promote, and roll back hunt playbooks. |
| **TRAIN** | Version datasets, run isolated training/evaluation, export accepted artifacts, and integrate model lifecycle. |
| **ROSTER** | Govern configured role eligibility, diversity, health, reliability, and reviewer expansion—not outcome votes. |

## Runtime execution flow

1. An operator or approved scheduler creates a hunt with target scope, budgets, role/config versions, and authorization.
2. SUB acquires a hunt lock, verifies durable storage and evidence roots, and writes `HUNT_CREATED` atomically with outbox entries.
3. ORG completes mandatory recall for the intended coverage neighborhood and stores a `RecallReceipt` before TGT may rank targets.
4. TGT applies hard eligibility (scope, readiness, telemetry, resource lock) and SCORE ranks eligible cells using priors, uncertainty, value, and cost. A `TargetDecision` records candidates, exclusions, recall influence, and selected target.
5. MUT creates a typed mutation proposal. Deterministic validation checks authorization, invariants, allowed tools, topology, cleanup, expected observables, control plan, and replay policy. An operator confirms any new or widened mutation class.
6. LOOP compiles the approved plan to the existing Red boundary and enforces lab-action, inference, wall-time, storage, and retry budgets.
7. Purple captures a fresh Episode, telemetry, tool arguments, observations, environment snapshot, and evidence hashes. Synthetic fixtures remain explicitly synthetic.
8. BR-COUSIN creates a behavior signature, retrieves candidates, computes deterministic distances, and emits a relationship plus independent defense response. BR-DRIFT compares matched history when temporal evidence is sufficient.
9. BIN advances only when each gate’s structured evidence passes. It schedules clean replay and matched controls as required.
10. HEART supplies reviewers the same immutable evidence version. Material objections block. Rebuttal causes a new review of the cited evidence version; it does not silently close an objection.
11. The Bully finding is delivered through the configured analyst-facing path and measured for visibility/latency. This validates the Bully delivery, not the missed original detector.
12. An authorized operator promotes, rejects, blocks, or supersedes the finding. Promotion can create proposals for HND, PLAY, and TRAIN; none deploy automatically.
13. ORG emits the outcome and all derived records. Outbox completion and a final decision-impact record are required before `HUNT_CLOSED`.
14. Costs, target posteriors, plateau state, known outcomes, examples, playbook candidates, and model evaluation inputs update for later hunts.

## Data flow

Raw execution artifacts are written once to the existing capture/evidence root and addressed by hash. Typed metadata and truth transitions are transactional SQL records. Each knowledge-bearing event creates an outbox item in the same transaction. The index worker embeds/reranks and writes a derived LanceDB row keyed by source record/version. Recall results cite those row keys and source hashes. If the projection is lost, it is rebuilt from SQL and evidence; if SQL is unavailable, hunts block.

## State model

Hunt stages are:

```text
DRAFT -> AUTHORIZED -> RECALL_READY -> TARGETED -> MUTATION_READY
      -> EXECUTING -> ANALYZING -> PROMOTING -> COMPOUNDING -> CLOSED
```

`BLOCKED`, `CANCELLED`, and `FAILED` preserve stage and reason; only a new append-only event can resume. A lease permits crash recovery; idempotency keys prevent duplicate Red executions and duplicate promotions. Closing requires no unresolved required outbox entries, no active execution, a complete cost record, and a final outcome.

Promotion states are independent:

```text
CREATED -> EVIDENCE_READY -> REPRODUCED -> CAUSALLY_VALIDATED
        -> SOC_VISIBLE -> ADVERSARIAL_CLEAR -> AWAITING_OPERATOR -> PROMOTED
```

`DISPROVED`, `BENIGN`, `BLOCKED`, and `SUPERSEDED` are explicit outcomes. State never moves backward; corrections supersede.

## Cousin definition

A cousin is an authorized observed procedure whose behavior has a defensible family relation to a reference procedure and a security-relevant structural delta. It is not defined by prose similarity or mere novelty.

`BehaviorSignature v1` contains:

- ordered action/event sequence with typed verbs and objects;
- entity/event relationship graph;
- parameter families and normalized numeric/categorical ranges;
- identities, privilege transitions, hosts/assets, topology, protocols, and timing;
- created/modified artifacts and expected cleanup;
- ATT&CK mappings with mapping source/version;
- telemetry event distribution and completeness;
- evaluated detector predicate outcomes, alert latency, and analyst visibility;
- evidence manifest and completeness score.

Candidate retrieval uses the union of semantic top 50, ATT&CK distance at most two edges, shared event-graph motifs, and configured scenario-family membership. Candidate absence never establishes novelty.

For each candidate, normalized distance is:

```text
D = .30 behavior_sequence
  + .25 event_telemetry_graph
  + .15 semantic
  + .15 attack_graph
  + .15 context_topology
```

Each structural component and aggregate is stored. Detection-response divergence is stored as a separate vector and response label; it does not contribute to `D`. Missing required dimensions lower confidence or yield `UNCLASSIFIED`; weights are never renormalized around missing data. Threshold/config and algorithm versions are part of the result. At least two non-semantic channels must establish a family relation.

## Same/similar/new/different semantics

Default calibrated thresholds for algorithm `cousin-v1` are:

- `SAME`: identical canonical fingerprint, or `D <= .10` with no hard-feature mismatch.
- `SIMILAR`: `D <= .35`, a relation on at least two non-semantic channels, and a meaningful delta within the same behavioral objective/causal shape.
- `NEW`: `.35 < D <= .60`, a relation on at least two non-semantic channels, and at least one security-relevant delta that changes defense response or coverage.
- `DIFFERENT`: `D > .60` or no defensible family relation.
- `ANOMALOUS_UNCLASSIFIED`: credible anomaly with incomplete/conflicting evidence or no stable family placement. It is not a cousin until later evidence places it.

Thresholds are configuration with a calibration artifact; changing them creates a new classification version and never rewrites old decisions.

Defense response is separately one of `COVERED`, `NEAR_MISS`, `MISSED`, or `INDETERMINATE`, derived from versioned detector predicates, telemetry health, alert delivery, and expected observables. The principal product is `SIMILAR|NEW × NEAR_MISS|MISSED` after promotion gates. `SAME × MISSED` is a regression and high-priority finding, but not a new cousin.

## Spatial-cousin design

Spatial hunts alter one or more typed mutation dimensions while holding declared invariants. The signature engine compares behavior, event graph, ATT&CK neighborhood, context/topology, and defense response. A paired baseline run is required whenever environment or telemetry equivalence is not already proven. Multi-dimension mutations are allowed only after constituent dimensions have adequate controls, so causal attribution remains possible.

## Temporal-cousin design

A `TemporalBaseline` is keyed by procedure family, detection ID/version, environment fingerprint, telemetry schema/version, and time policy. It stores robust distributions for action-sequence distance, event-frequency Jensen-Shannon divergence, detector predicate satisfaction, alert latency, and telemetry completeness.

The engine uses rolling median/MAD bands plus EWMA for scalar signals and a two-window distribution test for event vectors. A default alert needs three consecutive breaches; a configured safety-critical bound can alert immediately. Attribution order is deterministic:

1. failing sensor/control health → `TELEMETRY_DEGRADATION`;
2. environment fingerprint change → `ENVIRONMENT_CHANGE`;
3. changed attack signature with healthy matched controls → `ATTACKER_EVOLUTION`;
4. stable attack signature but degraded detector response → `DETECTION_DEGRADATION`;
5. otherwise → `UNCLASSIFIED`.

Models may summarize evidence and propose investigation, not choose the cause. Baselines reset through explicit supersession when relevant versions change.

## Alert/promotion design

Gates are code-owned:

- **G-1 Authorization:** approved target, mutation plan, tool allowlist, cleanup, and budgets; required before alert creation.
- **G0 Evidence integrity:** real Episode, complete manifest, hashes, environment/config/model versions, healthy telemetry. Synthetic evidence cannot pass.
- **G1 Reproduction:** a fresh execution plus a clean-snapshot replay, or an approved nondeterministic policy of two successes in three trials; both behavioral and expected telemetry artifacts must reproduce.
- **G2 Causality/alternatives:** attack-to-event causality is supported; matched benign, telemetry, and environment controls do not sustain the alternative explanation.
- **G3 SOC visibility:** the Bully finding reaches the configured analyst-facing index/notable/dashboard under replayed queue load within the configured SLO, with content intact.
- **G4 Adversarial clearance:** every material objection is resolved or operator-waived with reason and evidence version.
- **G5 Operator promotion:** an authorized human confirms classification, impact, handoff, and permitted feed outputs.

Any gate may end in `DISPROVED`, `BENIGN`, or `BLOCKED`. Retrying creates attempts under the same alert; changed evidence creates a new alert version.

## Self-bullying council

Required seats are evidence integrity, causal/benign alternative, detection engineering, SOC consumer, and safety/scope. Configured models may occupy multiple eligible roles only when diversity minimums are still met; at least two independent model families or one model family plus a human review are required for promotion. Each opinion includes disposition, findings, evidence citations, missing evidence, strongest objection, materiality, and conditions to change.

Materiality is code-validated against enumerated categories: scope/safety, evidence integrity, reproducibility, causal alternative, telemetry health, relationship classification, defense response, analyst visibility, or regression risk. The ROSTER reliability record determines eligibility, probation, and whether an additional reviewer is required. It cannot convert a material objection into a vote weight.

## Red interaction model

Red remains an evidence-producing executor. Bully supplies a compiled, scoped `RedOrderRequest` containing the existing scenario/reference, ordered allowed actions, target handle, budget, correlation ID, and expected evidence. Red returns its existing result plus a stable execution reference. The adapter records tool-call arguments, observations, readiness, substitutions, and synthetic status. Bully never changes Red’s truth semantics and never treats Red model confidence as outcome proof.

## Mutation model

Typed operators cover action ordering, technique substitution, protocol/transport, identity/privilege, host/topology, timing, artifact form, and observable behavior. A `MutationPlan` states reference signature, operators and parameters, invariants, expected delta, expected observables, matched controls, replay policy, allowed targets/tools, cleanup, risks, and approval.

The validator rejects unknown operators, invariant conflicts, unauthorized targets, unbounded parameters, unsupported tools, absent readiness, missing controls, or expected evidence that Purple cannot collect. The compiler is deterministic. Models cannot emit raw shell commands as a mutation contract.

## Knowledge organ

ORG owns typed emission, trust/version policy, indexing, retrieval, contradiction, supersession, recall receipts, and later decision-impact records. It never grants execution authority from retrieved content.

## Persistent substrate

The authoritative store is one migration-managed SQLite database in WAL mode at `${PORTAL_DATA_DIR}/security/defensive_bully/bully.sqlite3`. It owns typed lifecycle state, references, algorithms/config versions, costs, decisions, objections, examples, and promotions. Evidence bytes remain in Portal’s capture/evidence store and are content-addressed. The semantic projection is LanceDB at `${PORTAL5_LANCE_DIR}/defensive_bully`.

Every durable mutation is transactional and appends a `DecisionEvent`. Knowledge-bearing records also append `IndexOutbox` entries. The indexer is idempotent by `(record_type, record_id, version, projection_version)`. Dead letters block hunt closure when the record is required. Projection deletion is recoverable by replay; authority-store loss is not.

Memories have trust tiers: `VALIDATED`, `OPERATOR_CONFIRMED`, `SUSPECT`, `IMPORTED_UNVERIFIED`, and `SUPERSEDED`. Only validated or operator-confirmed memories may change high-consequence promotion priors. Contradictions link both records and force review; they are never averaged away. Derived confidence expires according to versioned policy, while raw provenance is retained.

## Compounding model

Compounding is proved by a chain:

```text
source outcome -> typed feed record -> indexed/activated version
              -> later recall/decision -> recorded decision delta
```

## Six feeds

1. **ORG:** all completed outcomes and objections are searchable. A mandatory pre-target recall records query, result versions, exclusions, and which results changed selection.
2. **Known defense/benign/covered:** validated outcomes update versioned priors and exclusions. Expiry, environment, and detection version prevent stale certainty.
3. **ROI:** target/yield/cost observations update neighborhood Beta posteriors and conservative discovery bounds.
4. **HARV:** promoted findings, valid negatives, rejected hypotheses, objections, and rebuttals become schema-validated example candidates with immutable provenance and leakage tags.
5. **TRAIN:** only an accepted model version changes configured specialist-role eligibility. Evaluation results and rollback are knowledge records.
6. **PLAY:** repeated evidence proposes a playbook version; offline replay and canary prove it, an operator promotes it, and later hunts record whether it changed actions/outcomes.

## Target selection

Hard eligibility precedes ranking: authorization, target health/readiness, telemetry controls, resource availability, no active conflicting lease, and playbook compatibility.

## ROI model

For eligible target `t`, configuration `roi-v1` records independent terms:

```text
value(t) = criticality * technique_relevance * lower_bound(uncovered_yield)
         * novelty_confidence * remediation_leverage * realism
priority(t) = value(t) / (estimated_cost_units + epsilon)
```

Known-covered/benign evidence adjusts the uncovered posterior rather than becoming another multiplier. Correlated features are calibrated jointly or only one is used. `estimated_cost_units` comes from a versioned pricing profile over lab minutes, inference tokens/time, analyst minutes, replay, storage, and training allocation. Missing material cost blocks ROI ranking.

TGT records the full candidate set, exclusions, raw features, posterior, score, selected target, and tie-break. Tie-break is deterministic: higher uncertainty reduction, then lower cost, then stable target ID.

## Plateau model

PLT evaluates a neighborhood after at least eight valid trials spanning at least two mutation dimensions. Plateau requires: no promoted discovery in the window; marginal unique defense-response gain below one; and the upper 95% bound of discovery yield below 5% by default. Infrastructure/blocked attempts do not count. A detection, telemetry, environment, ATT&CK, cousin-algorithm, or material evidence version change resets through an explicit event. Plateau stops a neighborhood, never the entire system.

## Cost model

Every estimate and actual outcome retains separate lab, inference, analyst, replay, storage, and allocated training quantities before conversion through the pricing profile. Missing material measurement blocks ROI claims rather than becoming zero.

## Detection-engineering exit

HND creates a versioned proposal containing behavior/delta summary, evidence and replay bundle, affected detections/coverage cells, family-generalizing logic, candidate query/rule, positive/negative tests, predicted noise, telemetry assumptions, rollout, rollback, owner, and expiry. It never edits a production detector. Detection engineering records accept/reject/revise/deploy decisions and deployed detector version. Post-deploy Purple replay is required before the state becomes `KNOWN_COVERED`.

## Training flywheel

HARV produces examples only from durable records. Each carries source hashes, relationship/response labels, objections, trust tier, family/campaign/time groups, consent/licensing classification, and exclusion flags. Dataset assembly deduplicates by behavior/evidence fingerprint, prevents a family/campaign from crossing train/test, freezes the test set before the harvest period, and excludes suspect or evaluation-derived oracle labels.

Every training acceptance compares five arms on the same frozen suite:

1. base only;
2. base + retrieval;
3. base + promoted playbook;
4. base + retrieval + playbook (incumbent baseline);
5. specialist + retrieval + playbook.

The specialist must improve primary cousin macro-F1 by at least five absolute percentage points over arm 4 with a bootstrap 95% confidence interval above zero, and may not regress benign false-positive rate, calibration error, tool reliability, known-bad recall, or current security regression lanes by more than two absolute points. Configuration may tighten but not weaken these defaults without operator approval and a new acceptance-policy version. A 30% replay mix of general security, benign, known-bad, and tool-use examples is the default forgetting control.

## Model lifecycle

Training runs host-native in an isolated locked environment, initially capped at a configured 9B-class Qwen-compatible model after revalidation. It records base hash, dataset hash, code/toolchain/config, seeds, adapter/checkpoints, evaluations, merge/export, GGUF hash, and Ollama tag. Accepted artifacts are imported through Portal’s existing model lifecycle, canaried as a role alias, operator-promoted, and rollbackable to the prior alias atomically. MLX is training/conversion infrastructure; production chat serving remains Ollama.

## Playbook lifecycle

`DRAFT -> REPLAY_VALIDATED -> CANARY -> AWAITING_OPERATOR -> ACTIVE -> RETIRED`.

Playbooks contain applicable neighborhoods, prerequisites, allowed actions, budgets, recall requirements, stop rules, expected evidence, controls, and fallback. Revisions never overwrite active versions. Canary compares action quality, cost, safety, and yield; operator activation changes the role/config pointer. Failure automatically reverts the pointer and records the cause.

## Roster/council-learning model

ROSTER records model/human role capability, evaluation suite/version, calibration, citation validity, objection precision/recall, abstention quality, latency/cost, independence family, health, eligibility, and probation. It is updated only from outcomes unavailable to the reviewer at decision time. Reliability affects seat assignment, additional-review requirements, and retirement; it never weights promotion truth or suppresses an objection.

## Operator controls

Operator confirmation is mandatory for hunt authorization, widened mutation classes/scope, material-objection waivers, finding promotion, detection handoff acceptance, playbook activation, dataset release, model promotion/rollback override, and any threshold-policy weakening. Emergency cancel and kill switches halt scheduling and revoke execution leases without deleting evidence. Every action requires authenticated identity, role, reason, timestamp, and affected version.

## Deterministic-versus-model responsibility

Models may propose hypotheses/mutations, summarize evidence, map ATT&CK, draft detection logic, challenge causality, write objections/rebuttals, and generate example/playbook candidates. Code owns authorization, hashes, schemas, budgets, target allowlists, tool execution, distance calculation, confidence/threshold policy, detector predicate evaluation, temporal tests/cause ordering, state transitions, objection closure rules, outbox completion, splits, acceptance thresholds, deployment pointers, and audit events.

## Failure semantics

- Storage, migration, evidence-hash, scope, or authorization failure: fail closed and `BLOCKED`.
- Embedding/reranker unavailable: recall cannot satisfy the mandatory receipt; hunt blocks, never silently semantic-skips.
- One candidate source unavailable: record degraded retrieval; classification may proceed only if policy-required sources and dimensions remain complete.
- Telemetry unhealthy: defense response and causal promotion are `INDETERMINATE`/`BLOCKED`.
- Model/reviewer timeout: retry within budget, substitute only an eligible configured seat, otherwise block.
- Red target/lab failure: record infrastructure failure; exclude from yield/plateau denominators.
- Index failure: retry idempotently; required dead letter blocks closure.
- Crash: lease expires and SUB resumes from the last committed event; never repeats execution without checking the idempotency record.
- Training interruption: checkpoint and leave model in `TRAINING_FAILED`; active alias is unchanged.

## Provenance

Every record carries actor, source, timestamps, correlation/hunt/episode IDs, parent IDs, content hashes, config/model/environment/telemetry/detection/algorithm versions, synthetic flag, and supersession links as applicable. Generated narrative always cites evidence IDs.

## Observability

Required metrics include stage latency, queue/lease health, budget use, evidence completeness, outbox lag/dead letters, recall hit/influence, candidate-source coverage, classification confidence/disagreement, gate pass/fail reason, reproduction rate, objection age/materiality, SOC visibility latency/content integrity, target posterior/yield/cost, plateau/reset, feed activation/decision delta, playbook effect, dataset leakage/deduplication, training arm metrics, deployment/rollback, and resource peaks. Logs are structured and redact secrets/payloads by policy.

## Security boundaries

Only configured lab targets and tools are executable. Mutation inputs are typed, bounded, and validated. Evidence is hashed and access-controlled. Model text is untrusted. Retrieved knowledge is tagged by trust tier and protected against prompt injection; it cannot introduce tools, scope, or policy. SQL is parameterized; projection documents never carry executable authority. Secrets never enter prompts, evidence narratives, or training sets. Operator APIs enforce least privilege and audit. Production detections/models remain outside automatic write authority.

## Resource considerations

Each hunt has hard limits for lab actions, inference calls/tokens, elapsed time, retries, evidence bytes, and estimated analyst work. Scheduler admission accounts for Ollama residency, embed/rerank health, lab exclusivity, and disk. Training uses an exclusive system lock, memory/disk preflight, resumable checkpoints, and no concurrent live lab work. Projection rebuild and backfill are rate-limited and resumable.

## Configuration requirements

A versioned `config/security/defensive_bully.yaml` owns cousin algorithms/thresholds, role requirements/aliases, council seats, gates/replay policy, budget defaults/maxima, target and mutation policies, ROI/cost/plateau policies, temporal tests, storage roots, index schema, SOC delivery/SLO, playbook/training acceptance, locks, and retention. `config/portal.yaml` remains the workspace/MCP fleet source of truth; `config/backends.yaml` remains backend/model catalog authority. Secrets remain environment-managed. Every hunt snapshots effective non-secret configuration.

## Migration assumptions

Red continuity is mandatory. Purple Episodes are first adapted/dual-written in shadow mode. Legacy benchmark outputs remain stable until explicit cutover. Existing records are backfilled only with verifiable hashes/provenance and marked imported. New classifications dual-run against legacy unknown/Blue results. Each feed is enabled only after its shadow evidence proves decision impact. Legacy modules retire only when callers are migrated and their valuable regression suites have successor coverage.

## Final invariants

1. No out-of-scope Red execution.
2. No synthetic finding becomes proven or promoted.
3. No cousin is established by semantics alone.
4. No anomaly is mislabeled as novelty solely by distance.
5. No unhealthy telemetry becomes a miss.
6. No material objection is cleared by vote count or reviewer weight.
7. No consequential artifact deploys without authorized operator confirmation.
8. No hunt closes with missing required indexing, costs, or outcome.
9. No derived projection outranks authoritative state/evidence.
10. No feed is called compounding without a later recorded decision effect.
11. No specialist is promoted without beating retrieval+playbook controls and preserving regressions.
12. No old conclusion is mutated; it is superseded.

## Complete success criteria

The system is complete when a clean authorized lab run can: recall prior outcomes; select a target for recorded reasons; validate and execute a structural mutation through unchanged Red; capture a real Purple Episode; compute and explain spatial/temporal relationship and response; reproduce and causally validate a genuine miss; deliver it to the SOC-facing path; survive adversarial veto review; obtain operator promotion; generate a family-level detection proposal; persist and index all outcomes; measurably alter a later hunt through all applicable feeds; build a leakage-safe dataset; prove or reject specialist improvement against controlled arms; canary and roll back a model/playbook; recover correctly from injected failures; and keep all existing security regression lanes operational.

The accepted target is the full system, not a prototype. The other package documents define implementation contracts, transition, and proof.

## Architecture diagrams

The authoritative system-flow diagram appears under **Final architecture**. The hunt and promotion state diagrams appear under **State model** and **Alert/promotion design**. The complete training and dependency flows are further specified in `ARCHITECTURE_DEFENSIVE_BULLY.md`; all depict the same authority and operator boundaries.

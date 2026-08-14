# Portal 5 Defensive Bully — Comprehensive Review and Implementation-Ready Design

You are operating as a principal software architect, AI systems architect, senior security engineering architect, and critical design reviewer **inside the existing Portal 5 repository checkout**:

`https://github.com/ckindle-42/portal-5`

This is a large, deliberate architecture and design task.

Your objective is to determine and document the **complete final design of the Portal 5 Defensive Bully** in a form that a fresh coding-agent session can subsequently use to implement the entire system.

## This session owns the design.

## A later coding-agent session owns the implementation.

Do not write production code during this task.

Do not produce executable implementation task files yet.

But also do not produce a conceptual or high-level design that leaves the next coding agent to invent major architecture.

The final design package must be sufficiently precise that the next coding agent can:

1. read the accepted design,
2. re-verify referenced implementation surfaces against its current HEAD,
3. decompose the design into implementation tasks,
4. implement the complete system,
5. integrate it,
6. troubleshoot it,
7. correct implementation issues,
8. and prove the finished system against the design's success criteria.

The coding agent should be making **implementation decisions**, not reconstructing the architecture from scratch.

---

# Primary Objective

Deeply review and reconcile:

1. the original Bully concept,
2. the existing Defensive Bully design,
3. the reasoning captured in the handoff,
4. Portal 5's current source code,
5. current architecture and runtime wiring,
6. current tests and validation system,
7. current configuration,
8. relevant recent git history,
9. existing reusable capabilities,
10. and any architectural opportunities the previous design did not know about.

Then determine:

> If we deeply understood the original Bully system, deeply understood Portal 5 as it exists today, and designed the strongest possible defensive equivalent natively for Portal, what exactly should we build?

The answer may confirm the current design.

It may refine it.

It may materially redesign it.

It may replace significant portions of it.

Follow the evidence.

Do not preserve prior design decisions merely because substantial effort went into them.

At the same time, do not casually discard hard-won decisions without evidence.

---

# Intended Next Step

The artifacts produced by this task are intended to become the **authoritative design input to a future autonomous coding-agent implementation session**.

Therefore the design must include enough precision to define:

- component boundaries,
- responsibilities,
- interfaces,
- data contracts,
- persistence ownership,
- lifecycle behavior,
- state transitions,
- deterministic versus model responsibilities,
- failure semantics,
- operator-confirmation boundaries,
- dependencies,
- migration behavior,
- retirement conditions,
- integration requirements,
- resource assumptions,
- validation requirements,
- and end-state success criteria.

However, this task must **not yet**:

- create `TASK_*.md` execution files,
- perform implementation,
- modify production code,
- install new toolchains,
- train models,
- alter production configuration,
- perform destructive migrations,
- or commit/push implementation changes.

The detailed task decomposition comes **after human review and acceptance of this design package**.

---

# Core Working Philosophy

## 1. Required reading means required reading

The source documents listed below must be read **completely**.

Do not skim them.

Do not keyword-search them and infer the rest.

Do not read only headings.

Do not summarize from prior memory.

Large context is expected.

Do not optimize this task for token economy at the expense of understanding.

---

## 2. Grep is navigation, not architectural evidence

Commands such as:

```bash
grep
rg
find
git grep
```

are useful for locating implementation.

They are **not sufficient evidence of behavior**.

Finding a symbol does not establish:

- whether it is called,
- where it is called,
- whether it is reachable from a production entry point,
- whether it is bench-only,
- whether it is test-only,
- what state enters it,
- what state leaves it,
- whether its output changes future behavior,
- whether configuration enables it,
- whether another layer discards its result,
- or whether the comments around it remain accurate.

For significant architectural claims:

1. locate the code,
2. open and read it,
3. trace its callers,
4. trace its important callees,
5. inspect configuration,
6. inspect relevant tests,
7. determine runtime role,
8. then form a conclusion.

### Prohibited shortcut

Do not perform a repository-wide `rg`, collect filenames and matching lines, and construct an architecture from those matches.

That is not sufficient for this review.

---

## 3. Presence is not implementation

A similarly named class or function does not mean the capability exists.

A placeholder such as:

```python
return True
```

is not a real gate.

A library never reached by runtime orchestration is not an operational capability.

A test fixture is not production wiring.

A prompt instruction is not system enforcement.

---

## 4. Storage is not learning

Persisting information is not compounding unless a later run retrieves that information and changes behavior because of it.

A learning loop must be traceable:

```text
observation
    ↓
capture
    ↓
validation
    ↓
persistence
    ↓
retrieval
    ↓
decision
    ↓
changed behavior
    ↓
new observation
```

If that chain is broken, document where.

---

## 5. Prompting is not enforcement

System invariants should be enforced by code wherever practical.

Examples:

- mandatory pre-hunt recall,
- universal indexing,
- unresolved-objection blocking,
- operator-confirmation boundaries,
- label-blind production behavior,
- model-promotion gates.

Models reason and explain.

Code governs state transitions and mandatory control flow.

---

## 6. Do not optimize the future system for minimum effort

Do not recommend:

- an MVP,
- a thin proof-of-concept,
- a deliberately reduced implementation,
- a minimal vertical slice as the target architecture,
- or "only enough to prove the idea."

That is not the development philosophy of this project.

The eventual implementation is expected to build the **complete accepted design**.

Intermediate validation during the build is required, but it validates progress toward the complete system.

It does not redefine the product as something smaller.

Integration itself is part of discovery.

Building the full coherent system may reveal:

- useful interactions not visible in isolation,
- missing architecture,
- redundant architecture,
- better abstractions,
- or a final product somewhat different from the initial concept.

That is valuable information, not wasted effort.

Recommend removing a capability because it is **architecturally unnecessary or incorrect**, not merely because it is expensive.

---

# Primary Source Material

Completely read:

1. `BUILD_PROGRAM_DEFENSIVE_BULLY.md`
2. `HANDOFF_DEFENSIVE_BULLY_CONTEXT.md`
3. `BULLY_CONCEPT_SOURCE.md`

Treat them differently.

## `BULLY_CONCEPT_SOURCE.md`

The conceptual inspiration.

Determine **why the system works**, not only what features it has.

## `BUILD_PROGRAM_DEFENSIVE_BULLY.md`

The current intended design.

Treat its architecture and implementation assertions as hypotheses to verify.

## `HANDOFF_DEFENSIVE_BULLY_CONTEXT.md`

Historical reasoning, prior code observations, hard-won decisions, and known traps.

Respect the reasoning.

Re-verify the implementation claims.

Current HEAD wins.

---

# Required Repository Reading

Discover current documentation rather than relying only on known filenames.

Read completely where present and relevant:

- root `CLAUDE.md`
- scoped/nested `CLAUDE.md`
- `AGENTS.md`
- root and subsystem `README*`
- architecture documentation
- security architecture documentation
- inference/router documentation
- MCP documentation
- RAG/knowledge documentation
- model lifecycle documentation
- relevant current `DESIGN_*.md`
- relevant current `BUILD_*.md`
- relevant current `HANDOFF_*.md`
- relevant current `TASK_*.md`
- relevant operator/runbook documentation
- validation documentation
- configuration documentation
- `config/spine_surfaces.yaml`
- relevant configuration under `config/`

Historical task/design files should be read where needed to understand why a current subsystem exists or what contract it was intended to fulfill.

Do not drown the review in unrelated historical documentation.

But do not skip relevant design history merely because the files are large.

---

# Mandatory Multi-Pass Review Method

## Pass 1 — Repository orientation

Understand:

- top-level structure,
- subsystem boundaries,
- execution surfaces,
- configuration,
- tests,
- validation,
- documentation,
- tooling.

Do not settle on an architecture verdict yet.

---

## Pass 2 — Required source documents

Read the three primary source files completely.

Extract:

- thesis,
- assumptions,
- invariants,
- proposed components,
- code claims,
- known traps,
- conceptual principles.

---

## Pass 3 — Current Portal architecture

Read and trace the implementation behind relevant production paths.

For important subsystems establish:

```text
entry point
    ↓
orchestrator
    ↓
business logic
    ↓
state transition
    ↓
external dependency
    ↓
output
    ↓
downstream consumer
```

---

## Pass 4 — Cross-check

Compare:

```text
original concept
       vs
existing defensive design
       vs
handoff claims
       vs
current code
       vs
tests
       vs
configuration
       vs
runtime contracts
```

---

## Pass 5 — Relevant history

Use git history to understand:

- recent architectural evolution,
- why important code exists,
- whether assumptions changed,
- whether better primitives were introduced after the historical design reference.

Do not rely on commit messages without examining the resulting code where material.

---

## Pass 6 — Re-derive the design

Only after the previous passes should you determine what the final Defensive Bully architecture should be.

---

# Source-of-Truth Hierarchy

When implementation sources disagree:

1. live code and observed behavior at current HEAD
2. tests and executable validation
3. current configuration
4. current runtime contracts
5. recent git history
6. current repository documentation
7. existing Defensive Bully design
8. handoff historical claims
9. older project documentation

`BULLY_CONCEPT_SOURCE.md` is different.

It is not authoritative for Portal implementation.

It **is** authoritative for understanding the mechanism being translated.

---

# A — Establish Current Ground Truth

Record at minimum:

```bash
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git log --oneline -10
git remote -v
```

Determine whether the checkout is:

- clean/dirty,
- ahead,
- behind,
- diverged,
- or current

relative to the intended remote branch.

Do not:

- reset,
- clean,
- rebase,
- overwrite,
- blindly pull,
- or otherwise destroy local work.

Record the exact HEAD used for the review.

The historical reference commit in the existing design is context only.

---

# B — Reconstruct Portal 5 as a Whole System

Understand and map at minimum:

- API/request ingress
- pipeline
- orchestration
- routing
- workspaces/personas
- Ollama inference
- MLX services
- embeddings
- reranking
- MCP ecosystem
- RAG/knowledge systems
- persistent state
- investigations
- security module
- Red
- Blue
- Purple
- Episode lifecycle
- evidence lifecycle
- council
- evaluation/bench systems
- model lifecycle
- redeployment
- training-related infrastructure
- configuration
- validation
- observability
- operator-confirmation boundaries

Build the architecture from actual code.

Do not infer it from directory names.

---

# C — Trace Runtime Wiring

For important components determine:

> Who calls this?

> What calls that caller?

> What does this call next?

> What consumes its output?

> Does the output change later behavior?

Classify important surfaces as:

- `PRODUCTION_WIRED`
- `INDIRECTLY_WIRED`
- `CONFIG_GATED`
- `BENCH_ONLY`
- `TEST_ONLY`
- `LIBRARY_ONLY`
- `PARTIALLY_WIRED`
- `LEGACY`
- `DEAD`
- `UNRESOLVED`

Support classifications with evidence.

---

# D — Re-Derive Red

Determine:

- Red entry points,
- target/order creation,
- `red_order`,
- execution path,
- lab execution,
- telemetry landing,
- Episode production,
- evidence references,
- Red→B/P contract,
- configuration,
- failure behavior.

Evaluate whether the existing design boundary remains correct:

> Red is the means; the Bully can direct what Red runs but should not rewrite Red execution.

Do not modify Red during this review.

---

# E — Re-Derive Blue/Purple

Trace the actual Blue/Purple system end-to-end.

Determine:

- entry points,
- orchestration,
- evidence ingestion,
- analysis,
- scoring,
- detection evaluation,
- council interaction,
- verdict generation,
- notification,
- response,
- persistent state,
- prior-run memory,
- cross-run behavior,
- scheduling,
- continuous behavior,
- training-data extraction,
- feedback into future execution.

Re-evaluate the historical conclusion that current B/P is largely a benchmark/evaluation architecture.

Do not repeat historical line counts without recomputing current reality.

---

# F — Understand the Original Bully Mechanically

For the source concept analyze:

- hallucination bin
- suspect-until-proven promotion
- clean reproduction
- dynamic confirmation
- low-privilege validation
- structurally valid grammar fuzzing
- campaign orchestration
- semantic memory
- mandatory prior-hunt recall
- automatic post-hunt indexing
- negative-result learning
- known-defense suppression
- variant analysis
- ROI target selection
- plateau detection
- cost-per-finding
- persistent tooling
- thin MCP / thick business logic
- per-campaign learned operating instructions
- local-model offloading
- specialized training
- self-adversarial reasoning
- human-confirmed consequential actions

For each determine:

1. What happens?
2. Why does it work?
3. What general principle is underneath it?
4. What is the correct defensive analogue?
5. Does the current Defensive Bully design preserve that principle?

---

# G — Validate All 15 Offense→Defense Translations

Review every translation row from the current build program.

Use:

| Offensive Primitive | Underlying Principle | Existing Translation | Portal Capability | Evidence | Fidelity | Final Recommended Translation |
|---|---|---|---|---|---|---|

Fidelity:

- `STRONG`
- `STRONG_WITH_REFINEMENT`
- `PARTIAL`
- `SURFACE_ONLY`
- `MIS-TRANSLATED`
- `MISSING`
- `SUPERSEDED_BY_BETTER_PORTAL_CAPABILITY`

Do not preserve terminology if a better architecture emerges.

---

# H — Define "Cousin" Rigorously

This is one of the central design questions.

Define operationally and computationally:

- SAME
- SIMILAR
- NEW
- DIFFERENT
- ANOMALOUS_UNCLASSIFIED

Do not assume embedding similarity alone is sufficient.

Evaluate dimensions including:

- semantic similarity
- ATT&CK relationships
- tactic/technique/sub-technique
- behavioral sequence
- telemetry shape
- event relationships
- parameters
- execution ordering
- timing
- artifacts
- identity context
- host context
- topology
- protocol
- detection response
- confidence
- evidence completeness
- baseline deviation
- temporal evolution

Evaluate whether cousin distance should be multi-dimensional, for example:

```text
semantic distance
+ behavioral distance
+ telemetry distance
+ ATT&CK/graph distance
+ temporal distance
+ detection-response distance
```

Do not add dimensions because they sound sophisticated.

Each must contribute measurable value.

Answer clearly:

> What exactly makes attack B a cousin of attack A?

> How should Portal calculate that?

> How should it explain the result to a human?

> How do we distinguish meaningful novelty from arbitrary semantic distance?

---

# I — Spatial and Temporal Cousins

Treat both as required design surfaces unless the review finds a superior equivalent.

## Spatial cousin

Near-neighbor attack behavior that is structurally related to known behavior but escapes existing defensive coverage.

## Temporal cousin

A technique/detection relationship that changes over time and becomes a cousin of its prior state.

Determine the correct representation and measurement for each.

For temporal behavior evaluate signals including:

- confidence degradation,
- detection latency,
- event population changes,
- sequence changes,
- partial rule satisfaction,
- telemetry loss,
- feature drift,
- baseline distribution change.

Separate:

- environmental change,
- telemetry failure,
- detection degradation,
- attacker evolution.

---

# J — Review Every Proposed Component

Review:

- SUB
- ORG
- BR-COUSIN
- BR-DRIFT
- LOOP
- BIN
- HEART
- MUT
- SCORE
- TGT
- PLT
- HND
- HARV
- PLAY
- TRAIN
- ROSTER

For each document:

## Purpose

## Existing Portal primitives

Exact files/symbols.

## Current wiring

## Correct disposition

Choose:

- `LEAVE_ALONE`
- `REUSE`
- `RETROFIT`
- `EXTRACT`
- `REPOSITION`
- `MERGE`
- `SPLIT`
- `REPLACE`
- `RETIRE`
- `NEW`

## Required runtime behavior

## Inputs

## Outputs

## State ownership

## Interfaces

## Dependencies

## Failure semantics

## Operator-confirmation requirements

## Observability

## Validation requirements

## Implementation considerations for the future coding agent

The last section should identify constraints and important implementation facts without writing code or individual tasks.

---

# K — Search for Hidden Assets

Do not limit investigation to modules already named in the design.

Use search to locate candidates for concepts such as:

```text
similarity
embedding
rerank
vector
distance
nearest
cluster
novelty
episode
evidence
case
journal
memory
history
state
baseline
drift
anomaly
mutation
variant
ATT&CK
sigma
telemetry
coverage
graph
campaign
scheduler
continuous
feedback
dataset
jsonl
adapter
LoRA
finetune
council
objection
dissent
consensus
quorum
promotion
score
cost
ROI
plateau
supersede
replay
snapshot
analyst
notable
Splunk
lineage
provenance
counterfactual
```

Search finds candidates.

Reading determines relevance.

---

# L — Review All Six Compounding Feeds

Review:

1. semantic hunt memory
2. known-defense / known-benign / known-covered state
3. ROI / target intelligence
4. training-pair harvest
5. fleet-local fine-tuning
6. scenario-specific playbook memory

For each define the complete loop:

```text
source
   ↓
capture
   ↓
validation
   ↓
persistence
   ↓
retrieval
   ↓
decision impact
   ↓
measurable changed behavior
```

Also address:

- provenance,
- negative observations,
- contradiction handling,
- supersession,
- aging/decay,
- bad-memory contamination,
- knowledge poisoning,
- retrieval evaluation,
- deterministic enforcement.

The design must make it possible to demonstrate that later hunts actually benefit.

---

# M — Review the Training Flywheel

Evaluate the full intended lifecycle:

```text
HUNT
 ↓
HARVEST
 ↓
CORPUS
 ↓
TRAIN
 ↓
FUSE
 ↓
GGUF
 ↓
OLLAMA CREATE
 ↓
BENCH
 ↓
OPERATOR CONFIRM
 ↓
SERVE
 ↓
LATER HUNT
```

Re-verify every existing leg.

Design:

- corpus schema,
- role tagging,
- positive examples,
- negative examples,
- adversarial council examples,
- cousin judgments,
- provenance,
- label-blind boundaries,
- train/validation/test separation,
- model versioning,
- dataset versioning,
- reproducibility,
- rollback,
- promotion criteria,
- catastrophic-forgetting controls.

Compare training against:

- base model,
- retrieval-enhanced base model,
- playbook-enhanced base model,
- retrieval + playbook,
- trained specialist.

The architecture should use training where it provides measurable gain.

Difficulty is not a reason to remove it.

Lack of measurable gain is.

---

# N — Re-Derive the Self-Bullying Council

Read the actual council implementation.

Determine what happens to:

- strongest objections,
- missing evidence,
- conditions to change,
- dissent,
- abstention,
- model failure,
- quorum,
- confidence,
- aggregation.

The intended Defensive Bully pattern is:

```text
candidate
    ↓
independent attempts to falsify
    ↓
objections
    ↓
evidence/rebuttal
    ↓
unresolved material objection?
    ├── YES → BLOCK
    └── NO  → eligible for next gate
```

not simply:

```text
candidate
    ↓
vote
    ↓
majority wins
```

Design HEART accordingly.

Also critically assess ROSTER.

Prevent:

- model monoculture,
- correlated-seat dominance,
- popularity weighting,
- reinforcement of incorrect consensus,
- loss of minority dissent.

---

# O — Re-Derive the Alert Bin

Evaluate whether the proposed gates remain correct:

- G0 — evidence exists
- G1 — replay/reproduction
- G2 — not benign
- G3 — analyst-visible

Determine whether any need to be:

- revised,
- split,
- merged,
- supplemented.

Preserve the principle:

> findings begin as suspects and earn promotion.

### Static + dynamic

A signature hit alone does not prove behavioral reproduction.

### Consumer context

A finding visible only to an evaluation harness is not necessarily a useful detection.

Determine how actual SOC analyst visibility can be measured through Portal/Splunk rather than merely asserted.

---

# P — Re-Derive Atomic Mutation

The original key insight is:

> structurally valid input + adversarial variation

not randomness.

Determine the correct defensive implementation.

Candidate mutation dimensions include:

- parameters
- timing
- sequence
- ordering
- command forms
- process relationships
- parent/child relationships
- identities
- hosts
- protocol use
- artifacts
- encodings
- sub-techniques
- execution context
- environmental conditions

Determine how the new system can direct Red toward such variants while preserving the appropriate Red boundary.

---

# Q — Review Target Selection, ROI, Plateau, and Cost

Define operationally meaningful targeting.

Possible inputs:

- asset criticality,
- ATT&CK relevance,
- uncovered risk,
- cousin novelty,
- prior miss rate,
- realism,
- detection confidence,
- compute cost,
- lab execution time,
- analyst effort,
- known defenses,
- historical yield.

Define plateau rigorously.

A neighborhood is not exhausted merely because embeddings stop producing new clusters.

Determine what change rate actually represents diminishing useful discovery.

Define cost accounting sufficiently to show whether the system compounds economically as well as technically.

---

# R — Review the Detection-Engineering Exit

A successful cousin should produce family-generalizing remediation.

Define the final handoff package.

Potential outputs:

- generalized detection logic,
- Sigma,
- SPL/correlation logic,
- required telemetry,
- ATT&CK mapping,
- evidence package,
- reproduction instructions,
- false-positive analysis,
- known limitations,
- IR implications,
- regression test,
- coverage impact.

Determine what Portal should produce automatically and what requires operator confirmation.

---

# S — Review Recent Development Since the Historical Design Point

Study relevant changes affecting:

- inference
- fleet composition
- model roles
- routing
- workspace/persona architecture
- security
- evaluation
- MCP
- RAG
- knowledge
- persistence
- configuration
- spine
- validation
- model lifecycle
- deployment

Classify meaningful developments:

- `SUPPORTS_DESIGN`
- `CHANGES_ASSUMPTION`
- `PROVIDES_BETTER_PRIMITIVE`
- `CONFLICTS_WITH_DESIGN`
- `UNRELATED`

Do not use commit-message analysis as a substitute for current-code inspection.

---

# T — Re-Evaluate the Replacement Strategy

Do not treat current B/P as one disposable block.

For each affected component determine:

| Existing Component | Current Role | Valuable Primitive | Problem | Disposition | Future Role/Home | Migration Requirement |
|---|---|---|---|---|---|---|

Distinguish:

- behavior worth keeping,
- primitives worth extracting,
- orchestration that should disappear,
- compatibility paths,
- callers,
- tests,
- validation dependencies,
- retirement conditions.

The goal is not minimal churn.

The goal is the cleanest final architecture.

---

# U — Identify Missing Frontier-Level Capabilities

Only after understanding the project deeply, ask what is still missing.

Consider where justified:

- behavioral embeddings
- graph representations
- causal/event graphs
- counterfactual testing
- active learning
- uncertainty calibration
- novelty detection
- cluster discovery
- hypothesis generation
- disagreement as signal
- evidence provenance
- decision provenance
- model provenance
- knowledge decay
- poisoning resistance
- semantic-collapse protection
- automatic deduplication
- detection lineage
- replay
- shadow detections
- canary deployment
- adversarial evaluation
- experiment reproducibility
- decision observability
- compute scheduling
- memory pressure
- Ollama concurrency
- MLX constraints
- MCP execution constraints

Do not add technology for its own sake.

Every recommendation must strengthen the core product.

---

# V — Identify What Should Not Be Built

Completeness is not feature count.

Identify anything that should be removed because it is:

- duplicate,
- conceptually incorrect,
- superseded,
- needless indirection,
- deterministic work delegated to an LLM,
- redundant storage,
- evaluation theater,
- incapable of changing system behavior,
- legacy scaffolding,
- or an abstraction with no operational value.

Removing incorrect architecture is not scope reduction.

It is better design.

---

# W — Re-Derive the Final Architecture from First Principles

Do not merely rearrange the current component names.

Begin from:

```text
What must the completed system do?

What must it know?

What state must persist?

What must be deterministic?

Where are models useful?

Where are models dangerous?

What evidence is required?

What feedback loops must close?

What must block on failure?

What does the operator control?

What crosses the Red/B/P boundary?

What makes hunt N+1 better than hunt N?
```

Then derive the architecture.

If existing names such as SUB, ORG, BR, BIN, HEART, etc. remain the best abstractions, retain them.

If better boundaries emerge, change them.

The design itself is the deliverable.

---

# X — Design for Full Future Implementation

The resulting architecture must be designed with implementation feasibility in mind.

For each major component specify enough detail that the later coding agent can determine:

- where it belongs,
- what existing code it interacts with,
- what it consumes,
- what it produces,
- what state it owns,
- what service boundaries exist,
- what deterministic algorithms are required,
- what model roles exist,
- what configuration is needed,
- what resources it consumes,
- what failure looks like,
- what validation proves success,
- what existing component it replaces or modifies.

Do not defer major architectural decisions to the coding agent with phrases such as:

- "implementation may choose,"
- "could use X or Y,"
- "details TBD,"
- "some persistent store,"
- "some semantic algorithm,"
- "use an appropriate model."

If alternatives genuinely remain, select the recommended design and document why.

Leave flexibility only where the implementation choice does not change architecture.

---

# Y — Define the Future Complete Build Order

The design package should include the **dependency and implementation ordering constraints** needed by a later coding agent.

Do not create the actual executable task decomposition.

Do not create `TASK_*.md` files.

Instead define:

- prerequisite relationships,
- mandatory ordering,
- replacement ordering,
- migration ordering,
- integration gates,
- components that can proceed independently,
- points where the repository must remain operational,
- operator-confirmation boundaries,
- final retirement conditions.

The next session will convert this into the full build program.

The target remains the entire accepted system.

---

# No Production Changes During This Task

Do not:

- implement SUB/ORG/etc.,
- refactor B/P,
- change Red,
- install the training toolchain,
- train models,
- pull large model artifacts,
- alter production config,
- perform migrations,
- delete legacy modules,
- repin the spine,
- commit,
- push.

Safe inspection and non-destructive existing validation are allowed where needed to determine behavior.

The deliverables are design artifacts only.

---

# Required Deliverables

Produce a cohesive **implementation-ready design package**.

---

## 1. `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md`

This records the evidence and reasoning behind the final design.

Include at minimum:

### Executive verdict

### Current HEAD / repository state

### Required reading completed

### Major source areas read

### Current Portal architecture

### Current Red architecture

### Current Blue/Purple architecture

### Runtime wiring and call paths

### Original Bully principles

### 15-point translation review

### Current reusable asset inventory

### Cousin-model analysis

### Spatial-cousin analysis

### Temporal-cousin analysis

### Alert-bin analysis

### Council analysis

### Knowledge/compounding analysis

### Six-feed analysis

### Training-flywheel analysis

### Mutation analysis

### Targeting/ROI analysis

### Plateau/cost analysis

### Detection-handoff analysis

### Recent architectural drift

### Replacement/migration analysis

### Missing capabilities

### Unnecessary complexity

### Resource/operational constraints

### Required design changes

### Final recommendation

Conclude with one:

- `DESIGN VALID`
- `DESIGN REQUIRES REFINEMENT`
- `DESIGN REQUIRES MATERIAL REDESIGN`
- `DESIGN SHOULD BE REPLACED`

---

## 2. `DESIGN_DEFENSIVE_BULLY_FINAL.md`

This is the **authoritative description of what the future coding agent is expected to build**.

It must be complete and standalone.

Include:

### Thesis

### Goals

### Non-goals

### Core principles

### System boundaries

### Final architecture

### Component model

### Component responsibilities

### Runtime execution flow

### Data flow

### State model

### Cousin definition

### Same/similar/new/different semantics

### Spatial-cousin design

### Temporal-cousin design

### Alert/promotion design

### Self-bullying council

### Red interaction model

### Mutation model

### Knowledge organ

### Persistent substrate

### Compounding model

### Six feeds

### Target selection

### ROI model

### Plateau model

### Cost model

### Detection-engineering exit

### Training flywheel

### Model lifecycle

### Playbook lifecycle

### Roster/council-learning model

### Operator controls

### Deterministic-vs-model responsibility

### Failure semantics

### Provenance

### Observability

### Security boundaries

### Resource considerations

### Configuration requirements

### Migration assumptions

### Final invariants

### Complete success criteria

### Architecture diagrams

The future coding agent should not need the original conversation to understand the intended system.

---

## 3. `ARCHITECTURE_DEFENSIVE_BULLY.md`

Provide implementation-level architecture.

Include:

- component map,
- module/service boundaries,
- expected locations in the current repository,
- call-path expectations,
- data flows,
- state boundaries,
- service boundaries,
- model boundaries,
- MCP boundaries,
- Red/B/P boundary,
- inference interactions,
- embedding/reranking interactions,
- knowledge flow,
- training flow,
- promotion flow,
- failure flow,
- operator-confirmation flow.

Use diagrams where helpful.

---

## 4. `INTERFACES_DEFENSIVE_BULLY.md`

Define the important contracts the coding agent will need.

For each significant interface specify:

```text
PRODUCER
CONSUMER
PURPOSE
INPUT
OUTPUT
STATE EFFECT
ERROR/FAILURE SEMANTICS
PROVENANCE REQUIREMENTS
IDEMPOTENCY/RETRY BEHAVIOR
OPERATOR BOUNDARY
```

Cover interfaces among, as applicable:

- Red
- Episode
- hunt loop
- knowledge organ
- persistent substrate
- cousin engine
- alert bin
- council
- mutation director
- drift engine
- scorer
- target selector
- plateau logic
- handoff
- harvest
- playbooks
- training
- model deployment
- bench acceptance

---

## 5. `DATA_MODEL_DEFENSIVE_BULLY.md`

Define persistent and important transient data structures.

Cover as applicable:

- hunt
- Episode reference
- evidence
- cousin representation
- known defense
- known benign
- known covered
- detection state
- temporal baseline
- decision event
- council opinion
- objection
- rebuttal
- plateau
- cost record
- target score
- playbook
- training example
- dataset version
- trained model
- model provenance
- promotion
- supersession
- validation result

For each define:

- ownership,
- required fields,
- identity,
- lifecycle,
- provenance,
- retention,
- mutation rules,
- supersession behavior.

---

## 6. `MIGRATION_DEFENSIVE_BULLY.md`

Define how current Portal becomes the final system.

For each affected existing component document:

```text
CURRENT ROLE
CURRENT CALLERS
VALUABLE PRIMITIVES
FUTURE ROLE
DISPOSITION
NEW HOME
MIGRATION DEPENDENCIES
COMPATIBILITY REQUIREMENTS
RETIREMENT CONDITION
VALIDATION REQUIRED
```

Ensure no current path is silently orphaned.

Preserve Red continuity unless evidence justifies a different boundary.

---

## 7. `VALIDATION_DEFENSIVE_BULLY.md`

Define how the **full implemented system** will later be proven.

Separate:

- component validation
- integration validation
- behavioral validation
- cousin-discovery validation
- alert-bin validation
- adversarial-council validation
- temporal-drift validation
- mutation validation
- compounding validation
- training improvement validation
- SOC-context validation
- performance/resource validation
- regression validation
- final end-to-end proof

For each significant capability use:

```text
CLAIM
TEST METHOD
INPUT
EXPECTED BEHAVIOR
REQUIRED EVIDENCE
FAILURE MEANING
```

Define success semantically.

Do not let the future coding agent satisfy success merely by proving a symbol or file exists.

---

## 8. `IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY.md`

This bridges the design to the **next coding-agent session**.

It is not a task list.

It defines what the future implementation effort must satisfy.

Include:

### Authoritative source documents

### Target architecture summary

### Required components

### Required integrations

### Existing primitives to reuse

### Components to retrofit

### Components to replace

### Components to retire

### Components to create

### Required data contracts

### Required persistence

### Required configuration

### Required model/runtime dependencies

### Required training dependencies

### Resource constraints

### Dependency graph

### Mandatory implementation ordering constraints

### Migration constraints

### Validation gates

### Operator-confirmation points

### Failure/blocking semantics

### Compatibility requirements

### Repository-operability requirements

### Definition of complete implementation

### Final proof requirements

### What the coding agent must re-verify at its own HEAD

This document should make the next transition straightforward:

> accepted design → coding-agent build-program/task decomposition → complete implementation.

Do not put detailed `TASK_*.md` instructions here.

---

## 9. `HANDOFF_DEFENSIVE_BULLY_FINAL.md`

Write this specifically for a fresh future session.

Include:

- what was reviewed,
- HEAD used,
- resulting design verdict,
- major changes from the previous design,
- reasons for those changes,
- architecture summary,
- hard decisions,
- important implementation discoveries,
- existing assets,
- invariants,
- known traps,
- assumptions,
- unresolved issues if any,
- what must be re-verified against future HEAD,
- authority order among documents,
- intended next step.

The intended next step must be explicitly stated:

> A fresh coding-agent planning session should read this design package completely, re-verify the referenced Portal implementation surfaces against current HEAD, then produce the complete build program and execution task files for implementing the entire accepted design.

---

# Document Authority

The final package should use this hierarchy:

```text
DESIGN_DEFENSIVE_BULLY_FINAL.md
        ↓
authoritative definition of WHAT is being built

ARCHITECTURE_DEFENSIVE_BULLY.md
INTERFACES_DEFENSIVE_BULLY.md
DATA_MODEL_DEFENSIVE_BULLY.md
        ↓
authoritative implementation contracts

MIGRATION_DEFENSIVE_BULLY.md
        ↓
authoritative current→future transition requirements

VALIDATION_DEFENSIVE_BULLY.md
        ↓
authoritative proof requirements

IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY.md
        ↓
constraints for future build-program generation

HANDOFF_DEFENSIVE_BULLY_FINAL.md
        ↓
fresh-session orientation

REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md
        ↓
evidence/rationale supporting the decisions
```

Do not allow contradictory architectural requirements between documents.

---

# Evidence Standard

For significant implementation claims cite repository evidence.

Prefer:

```text
path/to/file.py::symbol
```

and where useful:

```text
path/to/file.py:Lx-Ly
```

Configuration:

```text
config/file.yaml::key.path
```

Tests:

```text
tests/path/test_file.py::test_name
```

History:

```text
commit <sha>
```

Explicitly distinguish:

- `VERIFIED FACT`
- `INFERENCE`
- `DESIGN DECISION`

Do not represent inference as current behavior.

---

# Anti-Shallow-Review Acceptance Criteria

The task is incomplete if any of these occur.

## Grep architecture

Search matches are treated as sufficient architectural understanding.

## Filename architecture

Behavior is inferred from module names.

## Documentation-only analysis

The code is not traced.

## Code-only analysis

The original concept is ignored.

## Handoff parroting

Historical claims are repeated without verification.

## Old-HEAD reasoning

Historical code state is treated as current.

## Feature-presence review

A similarly named function is treated as capability completion.

## Test-only assumption

Unit-test presence is treated as production wiring.

## Prompt-as-control assumption

Model instructions are treated as enforced invariants.

## Storage-as-learning assumption

Persisted data is treated as compounding without tracing future decision impact.

## Context avoidance

Important files are skipped primarily because they are long.

## Premature design confirmation

The current architecture is accepted before re-derivation.

## Minimalism bias

A reduced future product is recommended primarily to reduce work.

## Effort avoidance

Hard functionality is deferred primarily because it is difficult.

## Speculative complexity

New infrastructure is introduced without demonstrated architectural value.

## Coding-agent ambiguity

The final design leaves major architectural decisions for the implementation agent to invent.

---

# Required Completion Checklist

Before completing the task confirm:

- [ ] All three primary source documents were read completely.
- [ ] Current HEAD was recorded.
- [ ] Relevant recent history was inspected.
- [ ] Current Portal architecture was reconstructed.
- [ ] Red was traced end-to-end.
- [ ] Blue/Purple was traced end-to-end.
- [ ] Episode lifecycle was traced.
- [ ] Evidence lifecycle was traced.
- [ ] Council implementation was read and traced.
- [ ] RAG/knowledge implementation was read and traced.
- [ ] Persistence mechanisms were reviewed.
- [ ] Relevant bench/evaluation infrastructure was reviewed.
- [ ] Relevant validation scripts were reviewed.
- [ ] Model redeployment lifecycle was reviewed.
- [ ] Training capability/absence was re-verified.
- [ ] All 15 offense→defense translations were reviewed.
- [ ] Every proposed Defensive Bully component was reviewed.
- [ ] All six feeds were reviewed.
- [ ] Spatial cousins were fully designed.
- [ ] Temporal cousins were fully designed.
- [ ] Structural mutation was fully designed.
- [ ] Analyst-context validation was fully designed.
- [ ] Adversarial promotion was fully designed.
- [ ] Training flywheel was fully designed.
- [ ] Migration was designed.
- [ ] Interfaces were defined.
- [ ] Data ownership was defined.
- [ ] Validation requirements were defined.
- [ ] Implementation requirements were defined.
- [ ] Final standalone design was produced.
- [ ] Future coding-agent handoff was produced.
- [ ] No production code was changed.
- [ ] No `TASK_*.md` implementation files were created.

Do not mark an item complete unless it was actually performed.

---

# Final Standard

The final output must leave us able to say:

> We have finished designing the Defensive Bully.

Not:

> We have some recommendations.

Not:

> We have a prototype plan.

Not:

> The coding agent can figure out the details later.

The design should be complete enough that the next phase is unambiguously:

> **build this system.**

The future coding agent will still re-verify HEAD, inspect the affected implementation surfaces, and make ordinary implementation decisions.

But it should not need to decide what the Defensive Bully fundamentally is.

That is the responsibility of this task.

The central ambition remains:

> Build a defensive hunting system that discovers structurally adjacent attacks our existing knowledge and detections do not cover; adversarially attempts to disprove its own findings; promotes only evidence-backed discoveries; turns validated cousins into family-generalizing defensive improvements; learns from positive and negative outcomes; and compounds its hunt intelligence and model capability through continued operation.

Known-bad detection is the floor.

Unknown-cousin discovery is the product.

Spatial and temporal cousins both matter.

Structurally valid mutation matters.

Consumer-context detection matters.

Negative results matter.

The council is adversarial, not democratic.

Compounding must alter future behavior.

Training must demonstrate improvement.

Models reason.

Code enforces.

Operators confirm consequential promotion.

And once this design is accepted, the next coding-agent session should be able to turn it directly into a complete implementation program and build the whole system.
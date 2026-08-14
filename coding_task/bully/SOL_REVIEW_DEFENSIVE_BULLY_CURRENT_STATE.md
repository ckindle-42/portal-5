# Defensive Bully Current-State Review

## Executive verdict

**DESIGN DECISION — `DESIGN REQUIRES MATERIAL REDESIGN`.** The product thesis is sound: known-bad detection is the floor and discovery of structurally adjacent, uncovered attacks is the product. Portal already has credible Red execution, Purple evidence capture, bounded agent-loop primitives, council execution, evaluation lanes, and embedding/reranking services. It does not yet have the durable state, causal cousin model, promotion state machine, adversarial veto semantics, closed compounding loops, or training/deployment system required by the proposed design.

The final design therefore preserves Red, the six compounding feeds, spatial and temporal hunting, structural mutation, adversarial review, operator confirmation, and the training ambition. It replaces semantic-distance-as-cousin, generic RAG as authoritative state, democratic council aggregation, prompt-enforced gates, and placeholder growth/training claims with deterministic contracts and proof requirements.

## Current HEAD / repository state

- **VERIFIED FACT:** review HEAD was `47d3e884c8f0415ed26dbf77f5e817a22ce613ac` on branch `main`.
- **VERIFIED FACT:** local `HEAD` and the local `origin/main` ref were aligned (`0 0` from `git rev-list --left-right --count HEAD...origin/main`). No network refresh was required or performed.
- **VERIFIED FACT:** the worktree already contained unrelated modified and untracked files, including `tests/benchmarks/bench_capability.py`, `.serena/*`, Antares probe artifacts, and benchmark results. This review did not modify, stage, commit, or clean them.
- **VERIFIED FACT:** the historical design reference was `ee9272e`. Commits through current HEAD mainly changed model/evaluation catalog and closeout surfaces; they did not implement Defensive Bully.

## Required reading completed

The following source documents were read completely:

- `coding_task/v8/BUILD_PROGRAM_DEFENSIVE_BULLY.md`
- `coding_task/v8/HANDOFF_DEFENSIVE_BULLY_CONTEXT.md`
- `coding_task/v8/BULLY_CONCEPT_SOURCE.md`
- `coding_task/v8/design_review.md`

The root `CLAUDE.md`, root `README.md`, relevant canonical Wiki units, security execution documentation, current implementation, validation scripts, configuration, tests, and recent local Git history were also inspected. Claims below distinguish current behavior from design conclusions.

## Major source areas read

Repository evidence included:

- Red/Purple: `portal/modules/security/core/exec_chain.py::_run_chain_test`, `::_prepare_scenario`; `portal/modules/security/core/blue.py::run_purple_tests`, `::_score_purple`; `portal/modules/security/core/episode.py::Episode`, `::derive_verdict`.
- Blue/council: `portal/modules/security/core/blue_orchestrate.py`; `portal/modules/security/core/multichain.py`; `portal/modules/security/core/council_agreement.py`; `portal/platform/inference/router/council.py::run_council`, `::aggregate_opinions`.
- Unknowns/growth: `portal/modules/security/core/unknown_defense.py`; `growth_loop.py`; `capability_graph.py`; `response_loop.py`; `continuous_eval.py`; `emergent_gaps.py`; `recall_attribution.py`.
- Agent loop: `portal/platform/agent/loop.py::run_loop`; `decision.py::decide_next_action`; `goal.py::Goal`; `objective_entry.py`.
- Evidence/storage: `evidence.py::EvidenceStore`; `case_notebook.py::CaseNotebook`; `field_journal.py`; `portal/platform/memory/memory_mcp.py`; `portal/modules/research/tools/rag_mcp.py`.
- Runtime/configuration: `portal/modules/security/core/cli.py`; `portal/modules/security/cli/__init__.py`; `portal/modules/security/tools/security_mcp.py`; `config/portal.yaml`; `config/backends.yaml`; `config/lab_targets.yaml`; `config/spine_surfaces.yaml`.
- Model lifecycle: `portal/platform/inference/cli/models.py::cmd_models_import_gguf` and current backend catalog.
- Validation: `scripts/validation/security_bench.py`; `scripts/validation/blue_orchestration.py`; relevant security and platform tests.

## Current Portal architecture

**VERIFIED FACT:** the Open WebUI path reaches a stateless inference pipeline and routes chat inference to configured backends. Ollama is the production chat inference tier; embedding and reranking remain separate MLX-backed services. MCP servers are independently deployed services and must not become inference internals (`CLAUDE.md`; `config/portal.yaml::mcp_servers`; `config/backends.yaml`).

**VERIFIED FACT:** security is primarily a CLI/benchmark module. Orchestrated and council modes are documented as CLI-only rather than Open WebUI variants (`portal_wiki/canonical/unit-module-security.md`; `unit-fact-security-variants.md`). The security MCP is a thin adapter for vulnerability classification and lab perception, not an orchestration service (`portal/modules/security/tools/security_mcp.py`).

**DESIGN DECISION:** Defensive Bully belongs in a security-owned core package. It may expose thin CLI/MCP operator surfaces and call platform inference, embed, and rerank services, but it must not place hunt business state in the inference router or generic RAG service.

## Current Red architecture

**VERIFIED FACT:** `exec_chain.py::_run_chain_test` asks a Red model to produce tool calls, dispatches allowed lab tools or synthetic fixtures, records tool arguments and observations, and scores order, coverage, reliability, and success. `_prepare_scenario` handles target readiness, healing, and substitution. Static scenarios supply ordered Red actions.

**VERIFIED FACT:** Purple execution in `blue.py::run_purple_tests` creates an isolated episode per Red case, starts capture, executes Red, ships telemetry, stores captures, invokes Blue, and records provenance. Replay can use captured Red evidence. This is the strongest existing end-to-end bridge.

**DESIGN DECISION:** preserve Red’s execution contract and scenario library. Structural mutation must generate a validated `MutationPlan` and translate it to the existing Red order boundary. It must never permit a model to directly widen target scope or invoke an unapproved tool.

## Current Blue/Purple architecture

**VERIFIED FACT:** `_score_purple` derives capability truth through `Episode` and `derive_verdict`, then applies unknown-defense heuristics. Synthetic success can never become `PROVEN`; telemetry failure is indeterminate (`episode.py`).

**VERIFIED FACT:** current Blue paths include standalone orchestration, council scoring, unknown-defense classification, capability graph updates, and benchmark metrics. These are mostly benchmark-oriented and do not form one persistent production hunt lifecycle.

**VERIFIED FACT:** `unknown_defense.py` uses token overlap and simple baseline/anomaly heuristics. Its fallback can resolve an unplaced technique as benign. That is inadequate for unknown-cousin promotion.

## Runtime wiring and call paths

Current principal path:

```text
security CLI
  -> BenchRun/run_bench or a standalone Blue mode
  -> exec_chain Red execution
  -> Purple capture/telemetry/Episode
  -> Blue scoring/orchestration
  -> benchmark JSON + Wiki/provenance outputs
```

**VERIFIED FACT:** `growth_loop.py::run_growth_loop`, capability graph growth, response drafting, continuous evaluation, and corpus closing exist as libraries/tests but are not one live loop called by the Purple path. `portal/modules/security/cli/__init__.py` explicitly keeps growth-loop behavior out of the pass-through CLI.

**VERIFIED FACT:** `portal/platform/agent/loop.py::run_loop` is a deterministic bounded decide/execute/fold primitive with grounded candidate selection and honest blocking. It is used by a flag-gated security objective entry point. Its present implementation does not enforce every security-specific budget (notably `max_lab_actions`) and has no Bully lifecycle.

**DESIGN DECISION:** use the platform loop as the bounded inner action executor after adding enforceable budget hooks; a security-owned orchestrator must own hunt stages, transactions, gates, and recovery.

## Original Bully principles

The review preserves these principles from the concept and build program:

1. Find attack cousins that known technique matching misses.
2. Treat uncovered unknown cousins as the primary product.
3. Keep Red as an evidence-producing executor.
4. Use both spatial and temporal adjacency.
5. Mutate attack structure, not only strings.
6. Attempt to disprove every promotable finding.
7. Learn from positive, negative, blocked, and superseded outcomes.
8. Change future targeting, recall, playbooks, and models through operation.
9. Keep consequential promotion operator-confirmed.
10. Let models reason while code enforces safety and truth transitions.

## 15-point translation review

| Offensive source idea | Defensive translation | Review result |
|---|---|---|
| Target binary | Coverage cell keyed by procedure, detection, environment, and telemetry version | Keep; make identity/version explicit. |
| Proof of concept | Reproducible near-miss or miss | Keep; require real evidence and controls. |
| Hallucination bin | Promotion state machine | Redesign; four prompt gates are insufficient. |
| Known exploit database | Known-defense/benign/covered registry | Keep; distinguish categories and supersession. |
| Exploit ROI | Expected defensive value per measured cost | Keep; use calibrated posteriors, not one opaque score. |
| Low privilege | Consumer/SOC context | Keep; define actual analyst-visible delivery. |
| Exploit report | Detection-engineering handoff | Keep; proposal only, no automatic deployment. |
| Grammar fuzzing | Typed structural mutation | Keep; validate invariants before execution. |
| FAISS/RAG memory | Security knowledge organ | Redesign; authoritative SQL plus derived vector index. |
| Self-bullying | Adversarial council | Keep; material objections veto. |
| Fine-tune exploit model | Offline specialist training | Keep; require leakage-resistant comparison and lifecycle. |
| Spatial/temporal variants | Cousin and drift engines | Keep; separate attacker, detector, telemetry, environment causes. |
| Recall/index every artifact | Transactional outbox and recall receipt | Keep; make closure-blocking and observable. |
| Plateau | Neighborhood stop/reset rule | Keep; define sample floor and statistical threshold. |
| Campaign instructions | Versioned playbooks | Keep; canary and operator promotion required. |

## Current reusable asset inventory

| Asset | Reuse disposition |
|---|---|
| `exec_chain` scenarios, lab tool dispatch, readiness | Reuse unchanged behind typed adapter. |
| Purple capture, telemetry, replay, `Episode` | Retrofit additively; retain legacy result compatibility. |
| `EvidenceRecord` schema | Reuse concepts; replace in-memory store with persistent append-only metadata. |
| platform agent loop/provider/executor contracts | Retrofit as bounded inner executor. |
| platform council reviewer execution/parser | Reuse independent-opinion primitive; replace aggregation for Bully. |
| embed `:8917`, rerank `:8925`, LanceDB pattern | Reuse as derived candidate/retrieval plane. |
| generic research RAG and conversation memory | Integrate only as service precedent; do not use as authority. |
| `CaseNotebook` SQLite/supersession idiom | Reuse lessons, not schema as-is. |
| capability graph, growth, response, continuous eval | Adapt algorithms/contracts; currently incomplete or in-memory. |
| security validation lanes | Preserve as regression lanes and extend semantically. |
| GGUF import/Ollama creation | Reuse deployment leg after an offline training/export pipeline exists. |

## Cousin-model analysis

**INFERENCE:** text embeddings can retrieve semantically adjacent procedures but cannot establish attack-family structure, causality, topology, detection response, or evidence quality. Calling semantic distance “the cousin metric” would conflate candidate generation with adjudication.

**DESIGN DECISION:** build a versioned `BehaviorSignature`. Candidate generation is the union of semantic top-K, ATT&CK-neighborhood, shared event-graph motifs, and scenario-family matches. Structural classification uses five normalized dimensions: behavior/sequence `.30`, event/telemetry graph `.25`, semantic `.15`, ATT&CK graph `.15`, and context/topology `.15`. Detection response is computed separately so a miss cannot make an unrelated attack look like a cousin. Evidence completeness is confidence, not distance. At least two non-semantic relationship channels are required before `SIMILAR` or `NEW` can be called a cousin.

## Spatial-cousin analysis

The relationship axis is independent from defense response. The product condition is a credible `SIMILAR` or `NEW` relation combined with `NEAR_MISS` or `MISSED`. “Far away” is not “new cousin”; without a structural family relation it is `DIFFERENT` or `ANOMALOUS_UNCLASSIFIED`.

## Temporal-cousin analysis

**VERIFIED FACT:** existing `drift_gate.py` measures benchmark/model-result drift, not temporal attack/detection cousins.

**DESIGN DECISION:** maintain matched baselines keyed by procedure family, detection/version, environment, and telemetry schema. Compare action sequence, event distribution, predicate satisfaction, latency, and telemetry completeness. Deterministic attribution distinguishes `ATTACKER_EVOLUTION`, `DETECTION_DEGRADATION`, `TELEMETRY_DEGRADATION`, `ENVIRONMENT_CHANGE`, and `UNCLASSIFIED`. Changes require consecutive breaches or an explicitly configured critical breach and matched controls; a model may explain evidence but cannot select the cause code.

## Alert-bin analysis

The original four gates did not prove scope integrity, clean replay, causal alternatives, analyst-facing visibility, objection closure, or promotion authority.

**DESIGN DECISION:** use append-only transitions:

```text
CREATED -> EVIDENCE_READY -> REPRODUCED -> CAUSALLY_VALIDATED
        -> SOC_VISIBLE -> ADVERSARIAL_CLEAR -> AWAITING_OPERATOR -> PROMOTED
```

Terminal/side states are `DISPROVED`, `BENIGN`, `BLOCKED`, and `SUPERSEDED`. Authorization and mutation scope precede creation. SOC visibility means the Bully-generated finding reached the configured analyst-facing Splunk/notable workflow within its SLO; it does not mean the underlying missed detector fired.

## Council analysis

**VERIFIED FACT:** platform `CouncilOpinion` already carries findings, missing evidence, strongest objection, and conditions to change. Reviewers execute independently. `aggregate_opinions` and the security adapter reduce decisions to participation/quorum/vote counts; objections are explanatory rather than blocking. Current no-concluder behavior escalates, so the historical claim “clear by default” is stale, but the democratic structure remains unsuitable.

**DESIGN DECISION:** the Bully council reuses independent reviewer execution and JSON parsing, not majority aggregation. Every material objection becomes a durable object. A finding cannot advance until each material objection is rebutted with cited evidence, withdrawn by its reviewer under the same evidence version, or explicitly waived by an authorized operator with a reason. Reliability selects eligible/diverse seats and triggers extra review; it never outweighs a veto.

## Knowledge/compounding analysis

**VERIFIED FACT:** research RAG is a generic document index with fixed vectors, source-directory ingestion, hybrid search, and restore/version operations. Memory MCP is conversation memory. Neither has hunt transactions, typed outcomes, causal provenance, or guaranteed indexing. `EvidenceStore`, capability graph, regression corpus, and feedback stores are primarily in memory. Field journal recall affects one engagement playbook path, not future Purple selection.

**DESIGN DECISION:** SQLite WAL is authoritative structured state; raw evidence is content-addressed and referenced by hash; LanceDB is a rebuildable semantic projection. An outbox transaction couples every knowledge-bearing state event to indexing. A hunt cannot close while required outbox records are pending or dead-lettered. Each hunt stores a pre-targeting recall receipt and a decision-impact record.

## Six-feed analysis

The six feeds must demonstrably affect future behavior:

1. **ORG recall:** validated/suspect memories are indexed by policy and produce ranked recall plus a selection-impact receipt.
2. **Known outcomes:** defense, benign, covered, disproved, blocked, and contradiction records modify priors with expiry and supersession.
3. **ROI:** measured yield and cost update neighborhood target posteriors.
4. **HARV:** promoted, rejected, and objection cases create provenance-locked training candidates.
5. **TRAIN:** accepted specialist versions enter a controlled role catalog only after comparative validation.
6. **PLAY:** recurring decisions propose playbook revisions, which require canary proof and operator promotion.

Storage alone does not satisfy a feed. Validation must show a later target, review, or action changed for the recorded reason.

## Proposed-component review

| Component | Current evidence and final disposition |
|---|---|
| SUB | No persistent security hunt owner exists; create the recovery-safe Bully orchestrator. |
| ORG | Generic RAG/memory and journals are not authority; create SQL/outbox/recall-impact knowledge organ. |
| BR-COUSIN | Token/semantic similarity is inadequate; create signature/candidate/deterministic two-axis engine. |
| BR-DRIFT | Current drift gate is bench drift; create matched temporal cause engine. |
| LOOP | Platform bounded loop exists; retrofit/reuse as inner executor and enforce all security budgets. |
| BIN | No complete gate lifecycle exists; create code-owned G0–G5 state machine. |
| HEART | Independent reviewer primitive exists; reuse execution, replace vote aggregation with objections/veto. |
| MUT | Red orders exist but no typed structural plan; create validator/compiler at the Red boundary. |
| SCORE | Bench score/notify metrics exist; create calibrated target value/cost/outcome scoring. |
| TGT | No persistent coverage-cell selector exists; create hard eligibility plus auditable ranking. |
| PLT | No neighborhood statistical stop/reset exists; create it from valid measured trials. |
| HND | Response drafts exist without deployment lifecycle; create proposal/disposition/replay closure. |
| HARV | In-memory corpora/feedback exist; create durable provenance/leakage-governed examples. |
| PLAY | Engagement playbook/journal patterns exist; create versioned replay/canary/activation lifecycle. |
| TRAIN | GGUF import exists but training/evaluation does not; create isolated five-arm lifecycle. |
| ROSTER | Current roster/votes track participation; redesign for role eligibility/diversity/reliability only. |

## Training-flywheel analysis

**VERIFIED FACT:** Portal can import a GGUF and create an Ollama model (`portal/platform/inference/cli/models.py::cmd_models_import_gguf`). It has no wired security LoRA/fine-tuning dataset, trainer, evaluation comparison, promotion, or rollback pipeline. A Qwen-compatible 9B MLX conversion exists in the current evaluation catalog, but its presence does not prove it remains the correct future base.

**DESIGN DECISION:** training is isolated and offline. Split data by cousin family, campaign, and time; freeze test data before the harvest window. Compare base, retrieval, playbook, retrieval+playbook, and specialist+both arms. Promotion requires a meaningful gain over the retrieval+playbook incumbent, confidence-bounded improvement, no material benign false-positive/calibration/tool regressions, provenance for every example, and operator approval. Production serving remains Ollama after adapter merge/export/GGUF import. The future coding session must reverify the current checkpoint and training toolchain.

## Mutation analysis

String mutation alone cannot produce family-generalizing evidence. The final design uses typed operators over action order, technique substitution, protocol/transport, identity/privilege, host/topology, timing, artifact, and telemetry-observable properties. Every `MutationPlan` declares invariants, expected deltas, scope, readiness, determinism, controls, and rollback. Code validates and translates the plan into Red orders; the model proposes but cannot execute or expand scope.

## Targeting/ROI analysis

Target selection must combine asset criticality, technique relevance, posterior uncovered probability, novelty confidence, remediation leverage, realism, readiness, and measured cost. Correlated signals remain separately recorded and must not be multiplied twice. The ranker uses a conservative posterior bound for low-sample neighborhoods. Authorization, target readiness, and resource lock are hard eligibility gates rather than score features.

## Plateau/cost analysis

Plateau applies per cousin neighborhood after at least eight valid trials spanning two mutation dimensions. It is reached when there are no promotions, less than one unique defense-response state of marginal gain, and the upper 95% discovery-yield bound is below the configured default of 5%. Blocked/infrastructure-failed trials do not count. Detection, telemetry schema, environment, ATT&CK, or evidence-version changes reset the neighborhood.

Cost records separately measure lab minutes, inference tokens/time, analyst minutes, replay work, storage, and training resources. A versioned pricing profile converts them to comparable units. Missing cost data blocks ROI claims; it does not become zero.

## Detection-handoff analysis

`response_loop.py` provides useful draft shapes but no deployed handoff lifecycle. Final handoff output is an evidence-linked detection proposal, coverage map, replay bundle, tests, predicted noise, rollout/rollback plan, owner, and expiration. Defensive Bully never auto-deploys a rule. Detection engineering and an authorized operator accept, reject, or request revision, and deployment results feed back as versioned defense state.

## Recent architectural drift

Between `ee9272e` and `47d3e884`, the repository changed model catalog/bench lanes and closeout documentation, including roster pruning and promotion/evaluation work. No commit supplied the missing persistent Bully lifecycle. **DESIGN DECISION:** model roles are configured aliases with capability requirements, never hard-coded model identifiers. Future implementation must rebenchmark the then-current candidates.

## Replacement/migration analysis

- Preserve Red and Purple output compatibility during shadow operation.
- Add persistent Bully state and adapters before changing any legacy scorer.
- Dual-write/observe Purple episodes into the new system without affecting benchmark verdicts.
- Backfill only evidence whose hash and provenance can be verified; label the rest imported/untrusted.
- Run old and new classifications in parallel; disagreements become migration evidence.
- Cut over targeting, promotion, handoff, playbook, and training independently only after their validation gates pass.
- Retire legacy unknown/growth behavior only after all callers are mapped and regression lanes remain green.

## Missing capabilities

Current Portal lacks: a durable hunt state machine; versioned behavior signatures; causal multi-dimensional cousin classification; temporal cause attribution; transactionally complete indexing; persistent council objections/rebuttals; an enforceable promotion gate; evidence-linked ROI and plateau; production-wired negative learning; a detection handoff lifecycle; training dataset/version/provenance; comparative training acceptance; controlled model rollback; and a single recovery-safe orchestration path.

## Unnecessary complexity removed

The redesign does not add another generic agent framework, replace the proven Red executor, run a separate database per component, make RAG authoritative, create a new inference service, or use a model to enforce transitions. One security-owned SQLite database, one derived LanceDB projection, existing capture storage, existing platform inference/agent primitives, and thin CLI/MCP adapters are sufficient.

## Resource/operational constraints

The reference machine is a 64 GB Apple Silicon host. Hunts require bounded inference, lab-action, wall-time, storage, and analyst budgets. Training obtains an exclusive resource lock, preflights memory/disk, pauses conflicting lab/model activity, checkpoints resumably, and begins with a configured 9B-class ceiling unless reverified capacity permits more. Production chats continue on Ollama; embedding/reranking use their existing services. All services must fail closed on unavailable authority, evidence, or scope.

## Required design changes

1. Separate semantic retrieval from cousin adjudication.
2. Separate relationship class from defense response.
3. Introduce authoritative SQL, content-addressed evidence, outbox indexing, and recall/impact receipts.
4. Introduce an explicit security-owned hunt/promotion state machine.
5. Replace vote aggregation with material-objection veto semantics.
6. Define typed structural mutations and enforce scope in code.
7. Attribute temporal change with matched controls.
8. Prove SOC visibility in the consumer’s actual path.
9. Make each of six feeds alter future decisions and test that effect.
10. Build an offline, leakage-resistant, reversible model lifecycle.
11. Migrate componentwise with shadow and dual-run proof.

## Final recommendation

Build the standalone design in the remaining documents. It preserves the ambition and current valuable primitives while replacing assumptions that current code cannot enforce.

**Final verdict: `DESIGN REQUIRES MATERIAL REDESIGN`.**

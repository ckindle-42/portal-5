# Defensive Bully Final Design Handoff

## What was reviewed

This session read the original concept, historical handoff, previous build program, and design-review mandate completely, then reconstructed the current Portal implementation rather than relying on filenames or prior claims. Review covered root architecture/configuration, Red execution, Purple capture/replay/Episode truth, Blue/unknown/council paths, platform agent loop, evidence/persistence, research RAG and memory, growth/graph/response/evaluation modules, targeting/score/drift validation, security CLI/MCP, model catalog/import lifecycle, canonical documentation, tests/validation scripts, and recent local Git history.

Primary inputs:

- `BULLY_CONCEPT_SOURCE.md`
- `HANDOFF_DEFENSIVE_BULLY_CONTEXT.md`
- `BUILD_PROGRAM_DEFENSIVE_BULLY.md`
- `design_review.md`

## HEAD and repository state

Review HEAD: `47d3e884c8f0415ed26dbf77f5e817a22ce613ac`, branch `main`. It matched the local `origin/main` ref at review time. Historical design reference: `ee9272e`.

The worktree already had unrelated modified/untracked files owned by the user/another agent. This design session did not modify, stage, commit, clean, or otherwise manipulate Git/project files. Its only outputs are the nine untracked documents in `coding_task/v8/`.

## Resulting design verdict

**`DESIGN REQUIRES MATERIAL REDESIGN`.**

The thesis and full ambition are accepted. The prior architecture could not be implemented as authoritative truth because it equated semantic distance with cousinhood, treated generic RAG/storage as compounding, used vote/weight council semantics, left promotion gates partially prompt-defined, and described training/growth capabilities that are not production-wired. The final package resolves those defects without shrinking the product.

## Major changes and reasons

1. **Semantic retrieval is not cousin adjudication.** Embeddings retrieve candidates; a versioned multi-dimensional behavior signature and deterministic distance establish relationship. At least two non-semantic channels are required.
2. **Relationship and coverage are two axes.** `SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS_UNCLASSIFIED` is separate from `COVERED/NEAR_MISS/MISSED/INDETERMINATE`. Far-away does not mean new cousin.
3. **Security owns authority.** SQLite WAL plus content-addressed evidence is authoritative; LanceDB is a derived projection with transactional outbox. Generic research RAG and conversation memory remain independent.
4. **One security lifecycle owns truth.** SUB is recovery-safe and uses the platform agent loop only as a bounded inner executor.
5. **Promotion is a real state machine.** It proves evidence, clean reproduction, causality/alternatives, actual analyst visibility, adversarial clearance, and operator promotion.
6. **Council is adversarial, not democratic.** A material objection vetoes. Roster reliability controls eligibility/diversity/additional review, never outcome weighting.
7. **Temporal cause is explicit.** Matched baselines distinguish attacker evolution, detection degradation, telemetry degradation, environment change, and ambiguity.
8. **Mutation is typed and compiled.** Models propose structural operators; code validates scope/invariants/controls and compiles to existing Red orders.
9. **Feeds must prove later influence.** Every recall/known-state/ROI/harvest/training/playbook feed has an activation and `DecisionImpact` chain.
10. **Training must beat context controls.** Five arms isolate retrieval/playbook value; group/time splits prevent leakage; production remains Ollama; activation and rollback are operator-controlled.

## Reasons for those changes

The current code proves that Red/Purple evidence production is valuable, but current “unknown,” council, memory, growth, and training-shaped modules do not jointly enforce the claimed product. The redesign assigns each truth transition to deterministic code, each consequential action to explicit authority, each learned outcome to a durable causal trail, and each model claim to comparative evaluation. This is necessary to make the full ambition testable rather than merely described.

## Architecture summary

The new `portal/modules/security/core/bully/` application package owns contracts, store/events/outbox, evidence adapters, orchestration, signatures/cousins/temporal logic, targeting/cost/plateau, mutation/Red adapter, promotion/SOC/council, handoff/harvest/playbooks/training/roster, and observability. Thin security CLI/MCP adapters call it. Existing Red/Purple supplies authorized execution, capture, telemetry, replay, and Episode evidence. Existing embed/rerank endpoints support a separate Bully LanceDB projection. Existing platform inference/council/agent primitives are reused behind strict boundaries. An isolated host-native trainer exports an accepted GGUF to the existing Ollama import path.

## Hard decisions

- SQLite is authority; LanceDB is rebuildable search only.
- No direct dependency on generic RAG or memory for hunt truth.
- No new generic orchestration framework.
- Red continuity is mandatory.
- Cousin-v1 structural weights are behavior `.30`, event/telemetry graph `.25`, semantic `.15`, ATT&CK `.15`, and context/topology `.15`; detector response and confidence are separate.
- Default relation thresholds: SAME `<=.10`/fingerprint; SIMILAR `<=.35`; NEW `.35–.60` with family relation and coverage-relevant delta; otherwise DIFFERENT/UNCLASSIFIED. Threshold versions require calibration.
- Promotion gates G0–G5 cannot be waived wholesale; material objection waiver is its own audited operator command.
- SOC visibility proves delivery of the Bully finding to the analyst path, not firing of the missed underlying detector.
- Plateau is neighborhood-local after at least eight valid trials/two mutation dimensions and a sub-5% upper discovery-yield bound.
- Training acceptance is specialist+retrieval+playbook versus base+retrieval+playbook, default +5 macro-F1 points with CI above zero and no >2-point mandatory regression.
- Production chat inference remains Ollama.

## Important implementation discoveries

- `exec_chain.py::_run_chain_test` and `_prepare_scenario` already provide useful Red execution, readiness, tool, argument, and observation evidence.
- `blue.py::run_purple_tests` is the best current end-to-end evidence bridge: isolated cases, capture, telemetry, replay, Episode, provenance.
- `episode.py::derive_verdict` correctly prevents synthetic `PROVEN` and handles telemetry indeterminacy; preserve this truth boundary.
- Current growth/capability graph/continuous eval/evidence stores are largely in-memory or test/library shapes; `growth_loop.prove_draft` includes placeholder proof booleans.
- Current unknown-defense relationship is token-overlap/simple anomaly; it is not a structural cousin metric.
- Platform council opinions are rich, but `aggregate_opinions` and security adapters use vote/quorum semantics and discard blocking objection behavior. Historical “clear by default” is stale because no-concluder now escalates; the underlying democratic mismatch remains.
- Platform `run_loop` is valuable but does not currently enforce every security goal budget, notably `max_lab_actions`.
- Research RAG is a generic document KB with hybrid retrieval; memory MCP is conversation memory. Neither supports hunt transactions/provenance/outbox.
- `EvidenceStore`, graph, feedback, and regression corpus are not durable authority. `CaseNotebook` offers a SQLite/supersession idiom but is not a sufficient schema.
- Field-journal recall affects an engagement path, not future Purple selection, and simple persistence is not compounding.
- `drift_gate.py` is model/benchmark metric drift, not temporal security drift.
- Portal can import GGUF/create an Ollama model, but there is no complete security training/evaluation/promotion pipeline.
- A current 9B Qwen-compatible MLX artifact exists in the catalog, but recent history changed the roster. Future roles must be configured and rebenchmarked, not hard-coded.
- The current root security core code-surface glob may not recursively cover a new `core/bully/` package; add deliberate manifest coverage.

## Existing assets to preserve/reuse

Red scenarios/execution/readiness/tool traces; Purple capture/telemetry/replay; Episode truth; platform agent provider/executor interfaces; independent council execution/parser; embed/rerank services; LanceDB operational precedent; model GGUF import/Ollama serving; current security CLI/MCP transports; security/council/telemetry/anomaly/benign-noise/model evaluation lanes; useful DTO ideas from evidence, graph/growth, response, and continuous evaluation.

## Invariants

- no out-of-scope execution;
- no synthetic promotion;
- no semantic-only cousin;
- no far anomaly relabeled as novelty;
- no unhealthy telemetry relabeled as a miss;
- no vote clears a material objection;
- no consequential auto-deployment;
- no hunt closes with required outbox/cost/outcome missing;
- no projection outranks authority/evidence;
- no claimed compounding without a later decision effect;
- no specialist promotion without controlled improvement and rollback;
- no truth mutation—only supersession.

## Known traps

- Treating a similarly named current module as complete production wiring.
- Retrofitting research RAG or Wiki result files into authoritative state.
- Letting model-generated JSON, confidence, or prompt gates control transitions.
- Merging relationship and response into one “unknown” label.
- Calling semantic distance novelty or ATT&CK proximity a causal relation.
- Counting infrastructure failures as negative trials or zero-cost work.
- Letting target substitution reuse an unmatched baseline.
- Treating producer acknowledgment as analyst visibility.
- Closing objections by majority, weighted roster, synthesis prose, or rebuttal submission without re-review.
- Random example splitting, test-label reuse, duplicate evidence across splits, or comparing specialist only to base-without-context.
- Importing training libraries into service startup or serving the MLX artifact as the production chat tier.
- Assuming the current nonrecursive code-surface glob covers the nested package.
- Running artifact-writing security tests in a dirty worktree without inventory/containment.

## Assumptions

- Existing Red/Purple public behavior remains the correct execution boundary at future HEAD.
- Portal retains SQLite/LanceDB/Ollama/embed/rerank capabilities and a 64 GB Apple-Silicon reference host.
- A real authorized lab, telemetry, detection, and analyst-facing SOC test path can be made available for final proof.
- Detection engineers and authorized operators remain external owners of production deployment decisions.
- Security/domain configuration can be added beneath `config/security/` without displacing `portal.yaml`/`backends.yaml` authority.

## Unresolved issues requiring re-verification, not architectural invention

No fundamental product decision is intentionally left open. The future session must empirically select/calibrate:

- exact current reviewer/proposer/specialist role models and the trainable base checkpoint/license;
- exact supported Apple-Silicon training/merge/GGUF toolchain versions;
- calibrated cousin thresholds and temporal false-alert bands using a frozen corpus (the specified defaults are starting acceptance policy);
- current SOC destination/query/SLO and operator identity/authorization integration;
- exact data retention/backups/root paths within then-current Portal deployment;
- availability/count of blinded real cousin families sufficient for statistical final proof.

If any cannot be satisfied, record a blocker or propose a design amendment; do not silently weaken the requirement.

## What must be re-verified against future HEAD

Read repository instructions and dirty worktree first. Compare future HEAD to `47d3e884c8f0415ed26dbf77f5e817a22ce613ac`. Re-trace callers/signatures for `exec_chain`, Purple/Blue/Episode, security CLI/MCP, platform agent/council, evidence/storage/RAG/embed/rerank, config/backends/spine, validations, and GGUF import. Re-inventory current model catalog, lab tools/targets, SOC path, test artifact behavior, dependencies, and other-agent changes. Confirm that the package locations and migration assumptions still fit; adapt ordinary details without changing design authority.

## Document authority

```text
DESIGN_DEFENSIVE_BULLY_FINAL.md
        |
        v
ARCHITECTURE_DEFENSIVE_BULLY.md
INTERFACES_DEFENSIVE_BULLY.md
DATA_MODEL_DEFENSIVE_BULLY.md
        |
        v
MIGRATION_DEFENSIVE_BULLY.md
        |
        v
VALIDATION_DEFENSIVE_BULLY.md
        |
        v
IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY.md
        |
        v
HANDOFF_DEFENSIVE_BULLY_FINAL.md
        |
        v
REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md
```

The review is rationale, not a competing specification. The historical concept/handoff/build program are superseded where this package differs.

## Completion status of this design review

All three primary source documents and the review mandate were read completely. Current HEAD/state/history were recorded. Current Portal, Red, Blue/Purple, runtime call paths, Episode/evidence/council/RAG/persistence/bench/validation/model deployment/training absence were traced. All 15 translations, every named component, six feeds, spatial/temporal cousin models, mutation, analyst visibility, adversarial promotion, training, migration, contracts, ownership, validation, implementation ordering, and final standalone design were completed. No production code or Git state was changed, and no `TASK_*.md` file was created.

## Intended next step

> A fresh coding-agent planning session should read this design package completely, re-verify the referenced Portal implementation surfaces against current HEAD, then produce the complete build program and execution task files for implementing the entire accepted design.

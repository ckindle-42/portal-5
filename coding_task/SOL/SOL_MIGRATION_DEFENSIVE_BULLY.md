# Defensive Bully Migration Design

## Migration strategy

Migration is additive, shadow-first, componentwise, and reversible. Red continuity and existing security bench outputs are non-negotiable. No current path is removed merely because a similarly named Bully component exists. A component retires only after caller inventory, dual-run evidence, semantic validation, rollback proof, documentation/spine updates, and explicit cutover approval.

Phases are ordered:

1. contracts/config/store/evidence foundation;
2. passive Purple Episode ingestion and projection;
3. signature/cousin/temporal shadow classification;
4. bounded orchestration and mutation through unchanged Red;
5. promotion/SOC/council and operator surfaces;
6. six-feed shadow then active cutovers;
7. detection/playbook/training lifecycle;
8. legacy retirement and final end-to-end proof.

The repository remains operable after every phase. Feature flags default off and distinguish shadow write, shadow compare, and authoritative mode. Rollback changes pointers/flags; it never drops new data.

## Component transitions

### `exec_chain.py` and current Red scenarios

**CURRENT ROLE:** model-guided authorized lab-chain execution, target readiness/substitution, tool dispatch, observations, and benchmark scoring.  
**CURRENT CALLERS:** security CLI/bench and Purple execution.  
**VALUABLE PRIMITIVES:** scenarios/orders, `_prepare_scenario`, `_run_chain_test`, tool argument/observation capture.  
**FUTURE ROLE:** unchanged Red evidence executor behind `RedPurpleAdapter`.  
**DISPOSITION:** reuse; no redesign of Red truth or tool semantics.  
**NEW HOME:** remains current; adapter lives in `core/bully/executor.py`.  
**MIGRATION DEPENDENCIES:** immutable `RedOrderRequest`, idempotency receipt, evidence adapter.  
**COMPATIBILITY REQUIREMENTS:** existing scenario names/results/bench callers stay valid; synthetic flag and substitution preserved.  
**RETIREMENT CONDITION:** none; it is a retained dependency.  
**VALIDATION REQUIRED:** golden current bench output, scope/tool denial, idempotent/replay distinction, cleanup/infrastructure classification.

### `blue.py::run_purple_tests`, `_score_purple`, and `episode.py`

**CURRENT ROLE:** isolate Red cases, capture/ship telemetry, create Episode, run Blue, derive Purple capability truth and unknown flags.  
**CURRENT CALLERS:** security bench/CLI.  
**VALUABLE PRIMITIVES:** real capture/replay bridge; Episode synthetic/proven truth semantics.  
**FUTURE ROLE:** evidence/episode producer and compatibility scorer; Bully ingests additively.  
**DISPOSITION:** retrofit with an optional observation hook/adapter, not a breaking return-schema change.  
**NEW HOME:** capture remains current; Bully normalization in `bully/evidence.py`/`executor.py`.  
**MIGRATION DEPENDENCIES:** store/evidence schemas, feature flag, hashable result references.  
**COMPATIBILITY REQUIREMENTS:** legacy Purple results and Wiki provenance remain byte/semantically compatible absent flag.  
**RETIREMENT CONDITION:** `_score_purple` is not retired until every legacy caller and metric has a mapped successor; capture path remains.  
**VALIDATION REQUIRED:** shadow ingestion equals source statuses/evidence, synthetic never passes G0, telemetry failure remains indeterminate.

### `unknown_defense.py` and notification scoring

**CURRENT ROLE:** token-overlap known/similar/none, simple baseline anomaly/investigation, benchmark notification outcomes.  
**CURRENT CALLERS:** Purple scoring and validation/tests.  
**VALUABLE PRIMITIVES:** explicit unknown/anomaly outcome vocabulary, benign-alert-fatigue evaluation, investigation envelope.  
**FUTURE ROLE:** legacy benchmark comparator only; selected cases become calibration/regression fixtures.  
**DISPOSITION:** replace for authoritative cousin/response decisions; retain shim during migration.  
**NEW HOME:** `bully/signatures.py`, `cousins.py`, `temporal.py`; evaluation mapping in tests.  
**MIGRATION DEPENDENCIES:** behavior signatures, candidate union, detector predicates, matched controls.  
**COMPATIBILITY REQUIREMENTS:** dual-run writes both classifications with explicit mapping/disagreement; no new result silently reuses old `NONE -> benign`.  
**RETIREMENT CONDITION:** no production caller, all old tests assigned to successor or intentional legacy lane, disagreement corpus adjudicated.  
**VALIDATION REQUIRED:** semantic-only false cousin, far-anomaly distinction, known-bad recall, benign FPR, telemetry-indeterminate cases.

### `blue_orchestrate.py`, `multichain.py`, `council_agreement.py`, platform council

**CURRENT ROLE:** multi-section Blue analysis, chain consolidation, and full-roster quorum/vote aggregation.  
**CURRENT CALLERS:** standalone Blue CLI, security variants, benches/tests.  
**VALUABLE PRIMITIVES:** independent async reviewer execution, JSON parsing, rich platform `CouncilOpinion`, multi-view analysis.  
**FUTURE ROLE:** platform reviewer runner reused by HEART; old aggregation remains only for legacy Blue modes.  
**DISPOSITION:** retrofit a non-aggregating runner/API; create Bully objection logic; do not change legacy council behavior in place during initial migration.  
**NEW HOME:** `bully/adversary.py` and `roster.py`; generic execution stays platform.  
**MIGRATION DEPENDENCIES:** persistent packets/opinions/objections, evidence freeze, role config.  
**COMPATIBILITY REQUIREMENTS:** current Blue/council CLI outputs continue; Bully never imports/uses majority aggregate to clear G4.  
**RETIREMENT CONDITION:** no retirement required for legacy modes; security adapter may retire only if callers migrate.  
**VALIDATION REQUIRED:** one material veto blocks despite all other supports, no-concluder/seat timeout blocks, rebuttal re-review, waiver audit.

### Platform agent loop and `objective_entry.py`

**CURRENT ROLE:** bounded decide/execute/fold over grounded capability candidates; flag-gated security consumer.  
**CURRENT CALLERS:** platform/security objective paths and tests.  
**VALUABLE PRIMITIVES:** provider/executor contracts, deterministic fallback, confidence/budget/no-progress patterns.  
**FUTURE ROLE:** bounded inner action engine; SUB owns security lifecycle and separately enforces all budgets.  
**DISPOSITION:** retrofit generic hooks/counters only where necessary; do not fork another generic loop.  
**NEW HOME:** generic code remains; adapter in `bully/executor.py`.  
**MIGRATION DEPENDENCIES:** immutable action candidates and receipts; enforce/verify `max_lab_actions`.  
**COMPATIBILITY REQUIREMENTS:** existing objective behavior unchanged; Bully actions cannot escape provider candidates.  
**RETIREMENT CONDITION:** none.  
**VALIDATION REQUIRED:** lab/inference/wall budgets, no-progress halt, crash between intent/result, ungrounded model action denial.

### `evidence.py::EvidenceStore` and `case_notebook.py`

**CURRENT ROLE:** in-memory evidence records; SQLite notebook entries/supersession, often in-memory by default.  
**CURRENT CALLERS:** security libraries/tests.  
**VALUABLE PRIMITIVES:** evidence schema and notebook/supersession idiom.  
**FUTURE ROLE:** compatibility adapters or test helpers; authoritative data uses Bully store/evidence manifest.  
**DISPOSITION:** replace as authority, do not silently redirect old callers until mapped.  
**NEW HOME:** `bully/store.py`, `evidence.py`, migrations.  
**MIGRATION DEPENDENCIES:** storage backup/migration, content hashes, retention/access policy.  
**COMPATIBILITY REQUIREMENTS:** old tests can use their stores; imported records get `IMPORTED_UNVERIFIED` unless hashes/provenance verify.  
**RETIREMENT CONDITION:** caller inventory is empty or compatibility wrapper is explicit.  
**VALIDATION REQUIRED:** restart persistence, corruption/hash detection, supersession, concurrent writer/lease, migration rollback/preflight.

### Generic research RAG and memory MCP

**CURRENT ROLE:** document KB hybrid search and cross-conversation memory.  
**CURRENT CALLERS:** research workspace and memory consumers.  
**VALUABLE PRIMITIVES:** embed/rerank endpoint contracts, LanceDB lifecycle/index patterns.  
**FUTURE ROLE:** unchanged independent services; Bully shares infrastructure endpoints, not tables/state.  
**DISPOSITION:** reuse service capabilities; no retrofit into hunt authority.  
**NEW HOME:** Bully projection/recall is security-owned.  
**MIGRATION DEPENDENCIES:** configured endpoint health/version and separate index path.  
**COMPATIBILITY REQUIREMENTS:** zero change to research/memory table schemas or callers.  
**RETIREMENT CONDITION:** none.  
**VALIDATION REQUIRED:** index rebuild, stale dereference rejection, endpoint outage fail-closed, no cross-workspace leakage.

### `capability_graph.py`, `growth_loop.py`, `response_loop.py`

**CURRENT ROLE:** in-memory graph/gap drafts, placeholder proof fields, detection/response draft shapes; primarily library/test surfaces.  
**CURRENT CALLERS:** validators/tests/reporting and limited objective entry.  
**VALUABLE PRIMITIVES:** procedure/detection/gap vocabulary and draft/handoff fields.  
**FUTURE ROLE:** source compatibility/calibration fixtures; selected pure transforms can be adapted to coverage cells and HND.  
**DISPOSITION:** replace authoritative growth; retain until callers mapped. Placeholder `prove_draft` must never satisfy Bully gates.  
**NEW HOME:** `bully/targeting.py`, `promotion.py`, `handoff.py`.  
**MIGRATION DEPENDENCIES:** persistent outcomes, real replay/controls, proposal lifecycle.  
**COMPATIBILITY REQUIREMENTS:** legacy reports continue during shadow; explicit mapping from graph gaps to coverage cells.  
**RETIREMENT CONDITION:** no runtime caller and successor coverage/report tests pass.  
**VALIDATION REQUIRED:** prove no placeholder booleans can promote; detection proposal remains non-deploying.

### `field_journal.py`

**CURRENT ROLE:** JSON engagement journal and simple keyword recall that can influence one playbook path.  
**CURRENT CALLERS:** engagement loop/bench path.  
**VALUABLE PRIMITIVES:** pre-action recall and post-engagement write pattern.  
**FUTURE ROLE:** legacy journal/export view; ORG is authoritative.  
**DISPOSITION:** dual-write/export during transition, then remove from Bully decision inputs.  
**NEW HOME:** `bully/recall.py` plus optional journal exporter.  
**MIGRATION DEPENDENCIES:** outbox/index and recall impact receipts.  
**COMPATIBILITY REQUIREMENTS:** old engagement callers retain expected journal behavior until migrated.  
**RETIREMENT CONDITION:** all authoritative consumers use ORG and historical journal import policy is complete.  
**VALIDATION REQUIRED:** later decision changes from ORG evidence; duplicate dual-write does not double-learn.

### `continuous_eval.py`, `emergent_gaps.py`, `recall_attribution.py`

**CURRENT ROLE:** in-memory regression/feedback, gap transforms, and label-blind evaluation attribution.  
**CURRENT CALLERS:** mainly tests/validation.  
**VALUABLE PRIMITIVES:** corpus closure shapes, negative cases, label-blind oracle boundary.  
**FUTURE ROLE:** adapt into persistent HARV/bench acceptance; attribution remains evaluation-only.  
**DISPOSITION:** retrofit concepts, replace storage; prohibit production import of evaluation oracle labels.  
**NEW HOME:** `bully/harvest.py`, `training.py`, validation suite.  
**MIGRATION DEPENDENCIES:** source provenance, split/leakage policy, dataset release.  
**COMPATIBILITY REQUIREMENTS:** existing evaluation lanes stay; production package has an import-boundary test.  
**RETIREMENT CONDITION:** no runtime dependency and successor corpus APIs cover callers.  
**VALIDATION REQUIRED:** negative examples influence training, no oracle leakage, restart persistence/deduplication.

### `drift_gate.py`

**CURRENT ROLE:** benchmark/model metric drift across result series.  
**CURRENT CALLERS:** bench/validation.  
**VALUABLE PRIMITIVES:** metric regression lane.  
**FUTURE ROLE:** remain model/evaluation drift; explicitly distinct from BR-DRIFT temporal security cause engine.  
**DISPOSITION:** retain and rename only in documentation/API labels if needed to prevent confusion.  
**NEW HOME:** current location; security temporal engine in `bully/temporal.py`.  
**MIGRATION DEPENDENCIES:** none beyond naming clarity.  
**COMPATIBILITY REQUIREMENTS:** current validation semantics unchanged.  
**RETIREMENT CONDITION:** none.  
**VALIDATION REQUIRED:** tests prove the two drift types cannot be substituted.

### Security MCP/CLI and configuration

**CURRENT ROLE:** benchmark/pass-through commands, vulnerability/lab perception MCP, workspace/model/MCP configuration.  
**CURRENT CALLERS:** operators, scripts, Open WebUI/workspace infrastructure.  
**VALUABLE PRIMITIVES:** transport/startup, role/backend catalogs, lab target definitions.  
**FUTURE ROLE:** thin Bully command/query transport and configured dependencies.  
**DISPOSITION:** additive commands/methods and domain config; no orchestration in adapters.  
**NEW HOME:** `core/commands/bully.py`, existing `security_mcp.py`, `config/security/defensive_bully.yaml`.  
**MIGRATION DEPENDENCIES:** application API/auth roles, config schema/validation.  
**COMPATIBILITY REQUIREMENTS:** existing commands, ports, workspace variants, and `portal.yaml` source-of-truth rules remain.  
**RETIREMENT CONDITION:** none.  
**VALIDATION REQUIRED:** import/startup, auth denial, idempotent commands, config snapshot, no training dependency import.

### Model catalog, GGUF import, and Ollama deployment

**CURRENT ROLE:** configured model aliases/backends and GGUF-to-Ollama import.  
**CURRENT CALLERS:** inference/model CLI and benches.  
**VALUABLE PRIMITIVES:** immutable import inputs and Ollama serving leg.  
**FUTURE ROLE:** resolve Bully roles and deploy accepted specialist artifacts.  
**DISPOSITION:** reuse/retrofit alias promotion and rollback receipts; build missing offline trainer/evaluator.  
**NEW HOME:** training core plus thin script; serving stays existing.  
**MIGRATION DEPENDENCIES:** dataset/model provenance, exclusive lock, acceptance/canary, role-based config.  
**COMPATIBILITY REQUIREMENTS:** production chat remains Ollama; no hard-coded current 9B model; active alias unchanged on failure.  
**RETIREMENT CONDITION:** none.  
**VALIDATION REQUIRED:** five-arm evaluation, export/import hash continuity, atomic canary/promotion/rollback, resource ceilings.

### Validation scripts and existing security tests

**CURRENT ROLE:** RBP grounding, telemetry, graph, council, anomaly, benign-noise, drift, and model-eval proof.  
**CURRENT CALLERS:** development/release workflows.  
**VALUABLE PRIMITIVES:** semantic assertions including synthetic-never-proven and label-blind attribution.  
**FUTURE ROLE:** preserved regression lanes plus new Bully claim suites.  
**DISPOSITION:** extend; do not replace with file/symbol checks.  
**NEW HOME:** existing lanes plus `tests/security/bully/` and a bounded end-to-end validation entry.  
**MIGRATION DEPENDENCIES:** stable fixtures and real-lab test policy.  
**COMPATIBILITY REQUIREMENTS:** current mandatory lanes remain green; known artifact-writing tests are isolated/cleanly accounted for.  
**RETIREMENT CONDITION:** only redundant cases with explicit successor mapping.  
**VALIDATION REQUIRED:** `VALIDATION_DEFENSIVE_BULLY.md` in full.

## Data backfill policy

1. Inventory candidate legacy Episodes, captures, journals, graphs, corpora, and results without mutation.
2. Import only by an idempotent manifest recording source path/ID, content hash, importer/version, inferred fields, and omissions.
3. Preserve existing synthetic and truth labels. Never upgrade a legacy claim based on filename or old model prose.
4. Records with verified source hashes and complete context may be `VALIDATED` only after the corresponding new validator runs; otherwise use `IMPORTED_UNVERIFIED` or `SUSPECT`.
5. Imported examples are excluded from training test sets until leakage/group provenance is established.
6. A rollback disables consumption but keeps imports and audit receipts.

## Cutover and retirement gates

Each component cutover requires: current caller inventory; compatibility adapter; shadow data over the configured minimum window; disagreement analysis; fault/restart/idempotency proof; resource proof; operator approval; rollback drill; and documentation/config/spine validation. Authoritative promotion and feed activation require real evidence, not synthetic-only shadow proof.

Final retirement requires no unresolved callers, no dependency from supported commands, retained access to historical results, successor semantic coverage, all regression/e2e gates passing, and an approved retirement record. No legacy file is deleted merely to complete the initial implementation.

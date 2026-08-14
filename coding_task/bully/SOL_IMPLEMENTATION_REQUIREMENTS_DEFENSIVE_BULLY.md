# Defensive Bully Implementation Requirements

This document constrains the future build-program generation. It is not a task decomposition and does not authorize implementation against the review HEAD.

## Authoritative source documents

Authority order is:

1. `DESIGN_DEFENSIVE_BULLY_FINAL.md` — what must exist and how it behaves.
2. `ARCHITECTURE_DEFENSIVE_BULLY.md`, `INTERFACES_DEFENSIVE_BULLY.md`, `DATA_MODEL_DEFENSIVE_BULLY.md` — implementation contracts.
3. `MIGRATION_DEFENSIVE_BULLY.md` — transition/compatibility/retirement.
4. `VALIDATION_DEFENSIVE_BULLY.md` — semantic proof.
5. this document — implementation-program constraints.
6. `HANDOFF_DEFENSIVE_BULLY_FINAL.md` — orientation.
7. `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` — evidence/rationale.

If a lower document appears to conflict with a higher one, follow the higher and record the conflict before building. The original three source documents remain concept/history evidence, not authority over this final package.

## Target architecture summary

Implement one security-owned, recovery-safe Bully application package. Use SQLite WAL for authoritative structured state, existing capture storage for content-addressed evidence, and a rebuildable Bully LanceDB projection. SUB owns the lifecycle and invokes a retrofitted platform agent loop only for bounded inner actions. Existing Red/Purple is preserved behind typed adapters. Deterministic cousin/temporal/targeting/gate services consume real versioned evidence. HEART uses independent platform council execution but persistent material-objection veto semantics. Thin CLI/MCP adapters expose the application. HND/PLAY/TRAIN create separately approved lifecycle artifacts. Production model serving remains Ollama.

## Required components

The complete implementation includes SUB, ORG, BR-COUSIN, BR-DRIFT, LOOP integration, BIN, HEART, MUT, SCORE, TGT, PLT, HND, HARV, PLAY, TRAIN, and ROSTER with the responsibilities and state machines in the authoritative design. It also includes evidence manifests, authority store/migrations/events/outbox, SOC delivery, operator authorization/audit, configuration, observability, recovery, and compatibility adapters.

No named component is satisfied by an empty facade, prompt, static fixture, in-memory-only repository, or disconnected test implementation.

## Required integrations

- current Red scenario/readiness/tool execution and Purple capture/replay/Episode path;
- platform provider/executor agent contracts with explicit lab-action enforcement;
- platform council independent reviewer runner without Bully use of vote aggregation;
- configured Ollama inference roles and exact invocation provenance;
- configured embed/rerank services and separate Bully LanceDB projection;
- actual analyst-facing Splunk/SOC delivery/query path;
- lab-target/config/authorization controls;
- detection-engineer disposition/deployment receipt and post-deployment Purple replay;
- existing GGUF import/Ollama creation, extended with role alias canary/promotion/rollback;
- canonical docs, code-surface/spine, config validation, security regression lanes.

## Existing primitives to reuse

Reuse rather than clone:

- `portal/modules/security/core/exec_chain.py` Red execution/scenarios/readiness/tool traces;
- `blue.py::run_purple_tests` capture/replay/telemetry bridge and `episode.py` evidence-truth semantics;
- platform `agent` interfaces/bounded decision loop after missing security budget hooks are enforced;
- platform council’s independent invocation/schema parsing and rich opinion fields;
- embed/rerank endpoints and LanceDB operating pattern;
- existing model GGUF import/Ollama serve leg;
- useful data shapes/tests from evidence, response, continuous evaluation, graph/growth, and unknown-defense modules;
- current security/Blue/Purple/telemetry/council/evaluation validation lanes.

Reuse does not authorize importing generic research RAG or conversation memory as authority.

## Components to retrofit

- Purple/Episode: optional shadow/authoritative ingestion hook and stable references, with legacy return compatibility.
- platform agent loop: enforceable/exposed lab-action and action receipt hooks; existing callers preserved.
- platform council runner: an API returning independent opinions without aggregate dependence; legacy aggregate preserved.
- security CLI/MCP: thin Bully commands/queries and authentication roles.
- model lifecycle: immutable import receipt, role alias canary/atomic promotion/rollback.
- validation/config/doc surfaces: new semantic lanes and recursive Bully code-surface coverage.

## Components to replace

Replace only for authoritative Bully behavior, initially through parallel paths:

- token-overlap/semantic-only unknown classification with behavior-signature cousin engine;
- current benchmark anomaly baseline with matched temporal-cause engine;
- vote/quorum council decision with material-objection lifecycle;
- in-memory evidence/graph/corpus/feedback stores with durable typed records;
- placeholder growth proof with real promotion gates and replay/controls;
- keyword journal as a decision memory with ORG recall/impact receipts;
- static draft response as complete handoff lifecycle.

## Components to retire

No current Red or Purple capture component is retired. Legacy unknown/growth/security council adapters, journal decision inputs, or in-memory authorities retire only under `MIGRATION_DEFENSIVE_BULLY.md` conditions: no unsupported callers, successor proof, historical access, rollback, and explicit approval. Generic RAG/memory and benchmark drift remain in their current roles.

## Components to create

Create the `portal/modules/security/core/bully/` package and its modules as specified in the architecture document; SQL migrations; domain config; thin CLI command module and training script; Bully-specific projection; tests/validation; and deliberate repository doc/spine/code-surface entries. Exact internal helper decomposition may change, but responsibility, dependency direction, state ownership, and public contracts may not.

## Required data contracts

Implement all DTOs/interfaces in `INTERFACES_DEFENSIVE_BULLY.md` and durable structures in `DATA_MODEL_DEFENSIVE_BULLY.md`. Contracts are immutable/versioned at boundaries, reject unknown enums, use canonical hashes, cite exact input versions, and carry synthetic/trust/provenance. Relationship and defense response remain distinct. Error and idempotency semantics are part of the API, not optional documentation.

## Required persistence

- one migration-managed SQLite WAL authority at the configured Portal data root;
- foreign keys/checks/unique idempotency and aggregate-version constraints;
- append-only decision/audit/supersession records and durable leases;
- content-addressed external evidence with verification/retention metadata;
- transactional indexing outbox with dead-letter/remediation and closure blocking;
- separate rebuildable LanceDB projection with source dereference/hash validation;
- backup/preflight/forward-schema refusal and crash/idempotency recovery;
- no consequential state that exists only in model context, process memory, Wiki, result JSON, or vector storage.

## Required configuration

Add schema-validated, versioned `config/security/defensive_bully.yaml` covering algorithms/calibration, roles/roster, gate/replay/council policies, budgets, scope/mutation, ROI/cost/plateau, temporal policy, storage/projection, SOC destination/SLO, playbook/training acceptance, locks, and retention. Domain config must not duplicate workspace/MCP/backend authority from `portal.yaml`/`backends.yaml`. Model references are roles/aliases with capability requirements, never Python literals. Effective non-secret config is snapshotted per hunt. Secrets use current environment mechanisms and never enter snapshots/training.

## Required model/runtime dependencies

Normal runtime uses existing Portal/Ollama inference abstraction, embed and rerank clients, SQLite standard/runtime support, and the project’s supported LanceDB client. New heavyweight runtime frameworks require an architectural amendment. Model responses are schema-validated, cite evidence, and are untrusted. Reviewer independence and role resolution are recorded. Exact model candidates must be rebenchmarked at implementation HEAD.

## Required training dependencies

Training dependencies are host-native, isolated, optional, locked, and absent from normal service imports. Select and pin one Apple-Silicon-compatible Qwen adapter/fine-tune stack, adapter merge/export path, GGUF conversion, and evaluation/bootstrap tooling after a small reproducibility spike. Record toolchain versions/hashes. Do not install or fetch large artifacts until the build program reaches the approved training dependency phase. MLX may train/convert; the accepted production artifact is imported into Ollama.

## Resource constraints

Target the 64 GB M4 Pro reference host. Every hunt enforces lab-action, inference-call/token, elapsed-time, retry, evidence-byte, and analyst-cost limits. Admission control accounts for model residency, lab locks, dependency health, and disk watermarks. Training has an exclusive lock, preflight, resumable checkpoints, initially configured 9B-class ceiling, and no concurrent live lab. Index rebuild/backfill is resumable/rate-limited. Resource failure blocks safely; it does not justify removing a required product component.

## Dependency graph

```text
contracts + config schema
        |
        v
SQLite migrations/store/events/authority ---- evidence manifest/hash adapter
        |                                      |
        +------------> Purple shadow ingestion-+
        |
        +--> outbox/index/rebuild/recall
        |             |
        |             +--> target/impact receipts
        |
        +--> signatures/candidate union/cousins
        +--> temporal baselines/attribution
        +--> cost/target/plateau
        |
mutation validator/compiler -> bounded LOOP -> Red/Purple adapter
        |                                      |
        +---------------- evidence/assessments-+
                                               v
                          BIN -> SOC -> HEART -> operator promotion
                                               |
                         +---------------------+-------------------+
                         v                     v                   v
                     HND/coverage        PLAY lifecycle      HARV/dataset
                                                                     |
                                                                     v
                                                      TRAIN/eval/deploy/rollback
```

## Mandatory implementation ordering constraints

1. Freeze public DTO/config/schema semantics before dependent modules.
2. Implement and fault-test authority/evidence/idempotency/outbox before any autonomous scheduling.
3. Add passive Purple ingestion and prove feature-off/shadow compatibility before Bully initiates Red.
4. Build projection/mandatory recall before targeting claims compounding.
5. Build deterministic signature/cousin/temporal/calibration before promotion or target learning.
6. Build typed mutation validation/compiler before enabling LOOP/Red initiation.
7. Build metering/eligibility/ROI/plateau before scheduler admission.
8. Build BIN and SOC receipts before HEART/G4; build persistent objections before any promotion.
9. Prove full G0–G5 and operator authorization before enabling HND/PLAY/HARV consequential outputs.
10. Enable each of the six feeds first in shadow, then prove paired later-decision impact before authoritative activation.
11. Build detection proposal/deployment/replay before allowing `KNOWN_COVERED` updates.
12. Build dataset safety and frozen five-arm evaluation before training; build rollback before model promotion.
13. Cut over callers one component at a time; retire only after full end-to-end and regression proof.

Store/evidence, Red/Purple adapter, projection, and deterministic engines can be developed in parallel only after shared contracts are fixed. UI/transport, observability, and validation fixtures may proceed alongside core work but cannot define alternative truth.

## Migration constraints

Follow every per-component disposition in `MIGRATION_DEFENSIVE_BULLY.md`. Feature flags distinguish off/shadow/authoritative. Backfill is idempotent and trust-conservative. Dual-run disagreements are persisted/adjudicated, not normalized away. Rollback disables consumption/pointers without deleting new records. No current public path is silently orphaned. Red continuity is mandatory.

## Validation gates

The implementation program must map every requirement to the claim IDs in `VALIDATION_DEFENSIVE_BULLY.md`. Foundation requires C1–C4. Red initiation requires I1–I3 and M1–M2. Promotion requires B1–B3, A1–A3, H1–H2, and T1–T2. Feed activation requires R1–R2 and F1–F2. Coverage cutover requires D1. Training/model activation requires L1–L3. Release requires P1, G1, and E2E in addition to all earlier gates. A required skip is a failure.

## Operator-confirmation points

Implement separate authenticated commands/permissions for:

- initial hunt authorization and scope/budget;
- new/widened mutation operator/scope/risk;
- resume after a safety/integrity block;
- material-objection waiver;
- finding promotion and feed-output permission;
- detection proposal acceptance/deployment ownership;
- playbook activation/override/rollback exception;
- dataset release;
- specialist canary/promotion and rollback override;
- policy weakening or exceptional plateau override.

One approval must not imply another. All carry identity, role, reason, exact versions, and time.

## Failure/blocking semantics

Fail closed on storage/schema, evidence hash/completeness, authorization/scope, telemetry health, mandatory recall/index, required reviewer seat/material objection, SOC proof, or promotion authority. Classify lab/readiness/tool/cleanup failures as infrastructure/safety, not negative discovery. Retry only within budget with stable idempotency. Record unknown external outcome and reconcile before resubmission. Training failure leaves active alias unchanged. Cancellation/rollback preserves evidence/audit.

## Compatibility requirements

- existing Red/Purple commands/results and current security variants work with Bully off;
- generic research RAG, conversation memory, inference router, MCP fleet ports, and production Ollama behavior are not repurposed;
- existing Blue/council modes may retain legacy aggregation without being used by Bully G4;
- existing validation lanes and historical result readability remain;
- synthetic-never-proven and telemetry-indeterminate semantics remain;
- public import/startup does not require training extras;
- future schema/code reads older supported records or performs explicit migrations; never silent reinterpretation.

## Repository-operability requirements

Respect root repository instructions at implementation HEAD. Update canonical docs, config examples/schemas, service/CLI help, tests, and code-surface/spine manifests in the same implementation increments. The nested Bully package requires explicit recursive coverage. Use bounded/non-destructive tests; account for security tests that write artifacts. No committed model weights, datasets, live secrets, or host-specific absolute paths. Provide backup/rebuild/health/doctor/operator procedures and observable failure messages.

## Definition of complete implementation

Complete means all named components are production-wired into one recovery-safe lifecycle; all required contracts/state/gates/operator boundaries exist; all six feeds demonstrate future decision effects; detection handoff closes via deployed replay; the offline training/model lifecycle can accept or reject and roll back a real candidate; migration cutovers are explicit; and every required validation claim including real-lab E2E passes. A prototype, disconnected library, mock-only path, symbol-presence test, or deferred training/feed/promotion component is incomplete.

## Final proof requirements

Deliver an evidence index mapping design requirements and validation claim IDs to implementation symbols, tests, commands, and immutable run artifacts. Preserve raw outputs, versions, statistical intervals, resource traces, recovery/fault injection, rollback drills, and migration disagreement decisions. The final proof must show one linked real-lab lifecycle and one later changed decision, not only aggregated benchmark scores.

## What the coding agent must re-verify at its own HEAD

- branch/HEAD/worktree ownership and repository instructions;
- current callers and signatures for Red, Purple, Episode, security CLI/MCP, platform loop/council, RAG/embed/rerank, storage, validations, and model import;
- changes since review HEAD `47d3e884c8f0415ed26dbf77f5e817a22ce613ac`, including conflicts with another agent’s work;
- current model/backends/role candidates, exact Qwen-compatible base, licenses, and empirical capability;
- current Ollama/MLX/GGUF toolchain and Apple-Silicon support;
- current config/spine/doc requirements and nested glob behavior;
- actual SOC analyst-facing destination/query/SLO and authorization mechanism;
- lab targets/tools/cleanup/snapshot capabilities and real-evidence test availability;
- retention/data-root/backups/secrets requirements;
- threshold calibration corpus and sufficient real blinded families;
- any current untracked artifacts before writing or testing.

Ordinary implementation details may adapt to verified HEAD, but any change to product semantics, truth authority, component responsibility, gate, operator boundary, or validation threshold requires a documented design amendment rather than silent invention.

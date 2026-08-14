# Defensive Bully Implementation Architecture

This document is authoritative for module, service, call-path, and state boundaries. `DESIGN_DEFENSIVE_BULLY_FINAL.md` remains authoritative for product behavior.

## Component map and expected locations

Create a cohesive package at `portal/modules/security/core/bully/`:

```text
bully/
  __init__.py             public application API only
  contracts.py            enums and immutable boundary DTOs
  orchestrator.py         SUB lifecycle/recovery
  store.py                SQLite transactions/repositories/migrations
  events.py               decision-event and outbox emission
  evidence.py             evidence manifests/hash verification/adapters
  recall.py               ORG indexing, retrieval, recall/impact receipts
  signatures.py           BehaviorSignature construction
  cousins.py              candidate union, distance, relationship/response
  temporal.py             baselines, signal tests, deterministic attribution
  targeting.py            eligibility, posterior, ROI, selection receipts
  mutation.py             typed plans, validation, Red compilation
  executor.py             platform agent-loop and Red/Purple adapters
  promotion.py            BIN states and gate validators
  adversary.py            HEART opinions, objections, rebuttals
  roster.py               reviewer/model eligibility and reliability
  plateau.py              neighborhood windows, stop/reset
  handoff.py              detection proposal lifecycle
  harvest.py              example candidate lifecycle
  playbooks.py            playbook lifecycle/effect records
  training.py             dataset, train/eval/export/promotion orchestration
  soc.py                  analyst-facing delivery/visibility receipts
  observability.py        metrics/audit event adapters
```

Additional integration locations:

- `portal/modules/security/core/commands/bully.py`: thin CLI command handlers.
- `portal/modules/security/tools/security_mcp.py`: thin read/operator MCP methods; no orchestration state in process memory.
- `scripts/defensive_bully_train.py`: thin host-native training entry point calling `bully.training`.
- `config/security/defensive_bully.yaml`: versioned domain configuration.
- SQL migrations within `portal/modules/security/core/bully/migrations/` as ordered package resources.
- new tests under `tests/security/bully/` plus end-to-end/validation integration.
- an explicit recursive security-Bully code surface in `config/spine_surfaces.yaml`; the current `portal/modules/security/core/*.py` pattern must not be assumed to cover a nested package.

No Bully business module belongs in `portal/platform/inference`, `portal/platform/memory`, or `portal/modules/research`.

## Service boundaries

| Boundary | Ownership and rule |
|---|---|
| Bully application | In-process security core; sole owner of hunt truth/transitions. |
| SQLite authority | Local durable state, one writer transaction at a time, WAL readers; migration-managed. |
| Evidence/capture store | Existing Purple/capture ownership; Bully records immutable content hashes and references. |
| LanceDB projection | Bully-specific derived search index; disposable/rebuildable. |
| Ollama inference | Existing configured inference backend; models receive immutable context and return untrusted proposals. |
| Embed/rerank | Existing endpoints at configured services; candidate/recall assistance only. |
| Red/Purple | Existing security core execution and capture path behind an adapter; no direct mutation of Bully truth. |
| Splunk/SOC | External consumer boundary; adapter writes/queries delivery receipt without declaring underlying detection success. |
| MCP/CLI | Authenticated thin transports; call application commands/queries. |
| Trainer | Host-native, exclusive, offline subprocess boundary; never imported into normal runtime startup. |

## State boundaries

SQLite is authoritative for hunts, attempts, signatures, classifications, gates, objections, decisions, costs, feeds, datasets, models, and projections’ source metadata. Raw PCAP/log/model-output bytes remain outside the database with hashes. LanceDB contains text/vector/search fields plus authoritative record references; its rows are not legal inputs to a truth transition until dereferenced and validated against SQL.

Every state-changing application command follows:

```text
validate command + authority
  -> BEGIN IMMEDIATE
  -> check expected version/idempotency key
  -> append domain record(s)
  -> append DecisionEvent
  -> append required IndexOutbox item(s)
  -> COMMIT
  -> publish metrics/continue orchestration
```

No model callback holds a database transaction. The orchestrator persists intent, calls an external operation, then persists the returned result with the same idempotency key.

## Primary call path

```text
CLI/MCP/Scheduler
  -> BullyApplication.create_or_resume_hunt
  -> Orchestrator tick
     -> Store/lease
     -> RecallService.recall_for_targeting
        -> embed/rerank -> LanceDB -> authoritative dereference
     -> TargetSelector.select
     -> MutationDirector.validate_and_compile
     -> BullyExecutor
        -> platform.agent.run_loop (bounded inner decisions where needed)
        -> existing exec_chain/Purple execution
     -> EpisodeAdapter + EvidenceManifest
     -> SignatureBuilder
     -> CousinEngine + TemporalEngine
     -> PromotionService gates
        -> clean replay/controls via BullyExecutor
        -> SOC adapter
        -> AdversarialCouncil
        -> operator command
     -> FeedCoordinator
        -> handoff / harvest / playbook / ROI / known-state
     -> closure validator
```

The orchestrator is event-driven and resumable. A tick executes at most one externally visible action. The platform agent loop may choose among validated actions and fold observations, but SUB verifies its own lab-action counter because the current generic loop does not enforce all security budgets.

## Red/B/P boundary

`MutationCompiler` produces an immutable `RedOrderRequest`; `RedPurpleAdapter` translates it into the current scenario/order input. Existing target readiness, healing/substitution, tool dispatch, capture, telemetry shipment, and `Episode` verdict logic remain intact. The adapter returns a `RedExecutionReceipt`, `EpisodeReference`, and `EvidenceManifest` without redefining existing benchmark JSON.

During migration, the existing Purple caller remains the initiator and sends a shadow observation to Bully. After cutover, Bully may initiate the same adapter. Legacy benches continue to call the same public Red/Purple surfaces.

Synthetic executions retain `synthetic=true` through every derived record and cannot cross G0. Target substitution is recorded as an environment/context delta and invalidates an unmatched baseline.

## Model boundaries

Configured roles, not model IDs, are used:

- hypothesis/mutation proposer;
- evidence analyst;
- each adversarial council seat;
- detection/playbook drafter;
- specialist candidate.

Role resolution snapshots backend alias, exact model digest/tag, prompt/template version, inference parameters, and health. Model output must match a schema; parse/validation errors retry within budget and then block/abstain. A model never receives credentials or authority tokens and never calls raw tools directly. Council reviewers see the same frozen evidence bundle and cannot see one another’s opinions before submission.

## Embedding/reranking and knowledge flow

The outbox worker transforms typed source records into redacted index documents, obtains embeddings from the configured embed endpoint, and upserts the Bully LanceDB row. Projection schema/version and embedding model/version are stored. A dimension or model change creates a new projection and atomic read pointer after rebuild validation.

Recall is hybrid: structured SQL filters and trust/version policy constrain candidates; vector/FTS retrieval finds possible records; reranking orders them; the service dereferences source records and rejects stale/hash-mismatched rows. The resulting receipt contains query, projection version, candidates, exclusions, selected context, and token budget. TGT later appends whether/how that context changed ranking.

Cousin candidate retrieval uses a separate purpose and receipt from general recall. It unions semantic, ATT&CK-graph, event-motif, and family-source IDs before deterministic scoring. A failed source is explicit, not treated as an empty result.

## Inference interaction

All inference calls use the existing router/backend abstractions and an invocation record. Input is a redacted evidence/context bundle; output is stored as an evidence artifact plus a parsed DTO. Deterministic services consume only validated parsed fields and cited source IDs. Timeouts, malformed JSON, missing citations, or unknown enum values become failed/abstained invocations. A text instruction cannot advance a gate.

## Promotion and operator flow

```text
Classification
  -> G0 evidence validator
  -> replay job -> G1
  -> controls/causality evaluator -> G2
  -> SOC delivery + query receipt -> G3
  -> independent council -> objections/rebuttals -> G4
  -> operator promotion command -> G5/PROMOTED
```

Each gate validator takes the alert’s expected version and emits a `ValidationResult`. A later gate cannot run if an earlier required gate lacks a passing result for the same or superseding evidence manifest. A new evidence manifest invalidates downstream passes and creates a new alert version.

Operator commands use authenticated identity and role checks. Waiver, promotion, playbook activation, dataset release, and model alias change are separate commands so one approval cannot accidentally authorize all downstream actions.

## Adversarial failure flow

An opinion becomes one or more objections. `material=true` is accepted only for enumerated materiality categories with cited evidence or a specifically identified missing proof. A rebuttal cites new/existing evidence and requests re-review. Only the originating eligible seat or an equally independent replacement may withdraw after re-review; an authorized operator may waive with a durable reason. Unresolved material objections keep the state at `CAUSALLY_VALIDATED` or `SOC_VISIBLE`, never `ADVERSARIAL_CLEAR`.

## Temporal flow

After a signature/response is stored, the temporal engine selects only matched baseline cohorts. It verifies telemetry and environment controls, computes stored deterministic signals, updates EWMA/window state, and emits a cause result. Cause evaluation is repeatable from baseline/sample records. An environment/detection/telemetry schema change supersedes the baseline and starts a warm-up period; it does not masquerade as drift.

## Targeting and plateau flow

TGT reads eligible `CoverageCell`s, recall receipt, known-state versions, target statistics, active plateau, and resource status in one consistent snapshot. It persists all scored candidates. After an attempt closes, SCORE writes actual cost/yield, updates the Beta posterior, then PLT evaluates the window. Plateau status is a hard exclusion with explicit reset triggers; operator override is a recorded policy exception.

## Training flow

```text
completed durable cases
  -> HARV candidates (quarantined)
  -> schema/provenance/dedup/leakage review
  -> operator dataset release
  -> immutable DatasetVersion + split manifest
  -> exclusive trainer (base + replay mix)
  -> checkpoints/adapter
  -> five-arm frozen evaluation
  -> acceptance decision
  -> merge/export GGUF
  -> existing Ollama import
  -> shadow/canary role alias
  -> operator promotion or rollback
```

Trainer dependencies are optional and absent from production runtime imports. The active model alias is never modified before an accepted artifact exists and canary evidence passes. Dataset, model, and evaluation artifacts are content-addressed.

## Detection and playbook flows

A promoted finding may produce a detection proposal and a playbook proposal. Both reference immutable evidence and are separate lifecycles. HND integrates with detection engineers but cannot edit deployed rules. PLAY canaries against frozen replay plus bounded live shadow. Only a deployment receipt followed by Purple replay can mark a coverage cell known-covered. Only an active playbook pointer affects live scheduling, and its decision effect is recorded.

## Failure and recovery architecture

- **Lease:** one owner per hunt; compare-and-swap version; bounded renewal; expired leases are recoverable.
- **Idempotency:** all external executions/deliveries/training jobs use stable keys and receipts; retry checks before resubmission.
- **Outbox:** exponential bounded retry, dead-letter with operator remediation, projection rebuild command.
- **Cancellation:** cooperative at action boundaries; kill switch revokes authorization for new tools and records incomplete cleanup.
- **Degraded dependencies:** no fallback may weaken scope, evidence, or promotion requirements. Optional explanatory inference may abstain; required recall, telemetry, and authority block.
- **Migration:** schema migration is backup/preflight/transactional where SQLite permits; code refuses a newer unsupported schema.

## Repository operability

The Bully package must not import CLI/MCP adapters, research RAG, or training-only libraries at normal startup. Existing security public imports and benchmark outputs remain stable. New nested code must be included in code-surface/spine validation intentionally. Unit, integration, end-to-end, resource, and migration tests must run in bounded lanes; the existing security-core test command’s artifact-writing behavior must be accounted for by the future implementer.

## Dependency order

```text
contracts/config
   -> authority store/migrations/events/evidence
   -> Red/Purple Episode adapter + shadow ingestion
   -> outbox/projection/recall
   -> signatures/cousins/temporal
   -> mutation/executor + targeting/cost/plateau
   -> promotion/SOC/adversary/operator surfaces
   -> handoff + all six feed closures
   -> harvest/dataset/training/deployment
   -> component cutovers and legacy retirements
```

Store and evidence truth precede every feature. Shadow compatibility precedes orchestration cutover. Promotion proof precedes consequential feed activation. Full end-to-end proof precedes legacy retirement.

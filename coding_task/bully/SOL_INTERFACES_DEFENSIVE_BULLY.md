# Defensive Bully Interface Contracts

Boundary objects are immutable, schema-versioned, JSON-serializable DTOs defined in `portal/modules/security/core/bully/contracts.py`. IDs are UUIDv7 unless an existing Portal ID is being referenced. Times are UTC RFC 3339. Hashes use an explicitly recorded algorithm, initially SHA-256. Every command carries `command_id`, `idempotency_key`, `expected_version`, `actor`, and `correlation_id`.

## 1. Hunt command and orchestrator

**PRODUCER:** authenticated CLI/MCP/scheduler.  
**CONSUMER:** SUB orchestrator.  
**PURPOSE:** create, resume, cancel, or inspect a bounded hunt.  
**INPUT:** `HuntCommand` with scope/authorization reference, coverage neighborhood, budgets, requested playbook/config versions, command action, reason.  
**OUTPUT:** `HuntReceipt` with hunt ID/version/stage, accepted action, lease/status, next required action.  
**STATE EFFECT:** appends hunt and decision events transactionally.  
**ERROR/FAILURE SEMANTICS:** stale version → conflict; absent authority/scope/store → blocked; duplicate key → original receipt; cancel never deletes evidence.  
**PROVENANCE REQUIREMENTS:** authenticated actor/role, policy/config snapshot hash, authorization artifact, time.  
**IDEMPOTENCY/RETRY BEHAVIOR:** exact duplicate returns original; same key/different payload is rejected.  
**OPERATOR BOUNDARY:** operator authorization is mandatory for creation, scope widening, resume after safety block, and cancellation override.

## 2. Mandatory recall

**PRODUCER:** SUB before target selection; ORG outbox indexer produces projection rows.  
**CONSUMER:** TGT, mutation/evidence analysts, audit.  
**PURPOSE:** retrieve applicable prior outcomes and prove whether they affected the next decision.  
**INPUT:** `RecallRequest` containing hunt/neighborhood, structured filters, trust/version policy, query facets, top-K/token budget, projection requirement.  
**OUTPUT:** `RecallReceipt` with source/projection versions, candidate IDs/scores, excluded IDs/reasons, selected context IDs, dependency health; later `DecisionImpact` links ranking/action deltas.  
**STATE EFFECT:** receipt is persisted even for empty/degraded results.  
**ERROR/FAILURE SEMANTICS:** missing required projection, stale/hash mismatch, embed/rerank failure, or pending required outbox → hunt blocked; no silent empty fallback.  
**PROVENANCE REQUIREMENTS:** query/config/model versions and authoritative source hashes.  
**IDEMPOTENCY/RETRY BEHAVIOR:** keyed by hunt stage plus source watermark; changed watermark yields a new version.  
**OPERATOR BOUNDARY:** operator may remediate/rebuild, but cannot waive mandatory recall for promotion-capable hunts.

## 3. Target selection

**PRODUCER:** TGT/SCORE.  
**CONSUMER:** SUB and MUT.  
**PURPOSE:** choose one authorized coverage cell using explicit eligibility and ROI.  
**INPUT:** `TargetSelectionRequest` with coverage cells, recall receipt, known-state snapshot, target statistics, resource/readiness status, cost profile, plateau state.  
**OUTPUT:** `TargetDecision` containing every candidate, exclusion reason, raw features, posterior/interval, value/cost/priority, tie-break, selected cell.  
**STATE EFFECT:** persists decision and reserves selected cell/target lease.  
**ERROR/FAILURE SEMANTICS:** no eligible cell → blocked/plateau, not arbitrary fallback; missing material cost → unrankable.  
**PROVENANCE REQUIREMENTS:** algorithm/config and input-record versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** deterministic for a snapshot; resource change creates a new decision version.  
**OPERATOR BOUNDARY:** override requires reason and may not bypass authorization/readiness/telemetry hard gates.

## 4. Mutation proposal, validation, and compilation

**PRODUCER:** MUT proposer model or deterministic playbook.  
**CONSUMER:** mutation validator/compiler, then Red adapter.  
**PURPOSE:** express a bounded structural change without executable free text.  
**INPUT:** `MutationPlan` with reference signature, typed operators, bounded parameters, invariants, expected delta/observables, controls, replay policy, allowed targets/tools, cleanup, risk, approval reference.  
**OUTPUT:** `MutationValidation` and, on pass, `RedOrderRequest`.  
**STATE EFFECT:** persists proposal, validation, and approval; compilation is pure.  
**ERROR/FAILURE SEMANTICS:** unknown/unbounded operator, invariant conflict, scope/tool/readiness/control/evidence failure → rejected or blocked; never partially compiled.  
**PROVENANCE REQUIREMENTS:** proposer invocation, playbook/reference/config versions and approval.  
**IDEMPOTENCY/RETRY BEHAVIOR:** same plan/version compiles byte-identically; revision gets new version.  
**OPERATOR BOUNDARY:** new operator classes, risk levels, or widened scope require explicit confirmation.

## 5. Inner hunt action loop

**PRODUCER:** SUB.  
**CONSUMER:** platform agent loop through `BullyCapabilityProvider` and `BullyExecutor`.  
**PURPOSE:** choose and perform one grounded, bounded next action.  
**INPUT:** immutable hunt snapshot, validated action candidates, remaining lab/inference/time/storage budgets.  
**OUTPUT:** `ActionReceipt` with chosen action, provider candidate ID, execution reference, observations, actual budget debit, next-state suggestion.  
**STATE EFFECT:** intent and result are persisted on either side of external execution. SUB alone advances hunt state.  
**ERROR/FAILURE SEMANTICS:** no grounded action/low confidence → blocked; budget exhausted → blocked/plateau; model output cannot introduce an action.  
**PROVENANCE REQUIREMENTS:** decision/model/provider versions and observation evidence IDs.  
**IDEMPOTENCY/RETRY BEHAVIOR:** stable action key; check an existing execution receipt before resubmission.  
**OPERATOR BOUNDARY:** no additional boundary if action is already approved; widening requires a new mutation/operator approval.

## 6. Red execution

**PRODUCER:** mutation compiler/Bully executor.  
**CONSUMER:** existing Red/Purple adapter around `exec_chain` and `blue.run_purple_tests`.  
**PURPOSE:** execute the approved mutation and return evidence-producing runtime results.  
**INPUT:** `RedOrderRequest` with scenario/reference, target handle, ordered allowed actions, budgets, expected evidence, cleanup, correlation/idempotency IDs.  
**OUTPUT:** `RedExecutionReceipt` with existing Red result reference, actual target/substitution, tool arguments/observations, readiness, timestamps, synthetic flag, cleanup status.  
**STATE EFFECT:** external lab effects and immutable receipt/evidence references.  
**ERROR/FAILURE SEMANTICS:** lab/readiness/tool/cleanup failure is infrastructure/safety failure and excluded from discovery yield; unauthorized request is rejected before Red.  
**PROVENANCE REQUIREMENTS:** exact scenario, target/environment, model, tool, config, and authorization versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** receipt lookup before retry; replay is a separately identified attempt on a declared clean snapshot.  
**OPERATOR BOUNDARY:** target/scope already approved; cleanup failure triggers operator/safety escalation.

## 7. Episode and evidence ingestion

**PRODUCER:** existing Purple path and Episode adapter.  
**CONSUMER:** evidence service, signature/cousin/temporal engines, BIN.  
**PURPOSE:** normalize existing Purple output without breaking it.  
**INPUT:** existing `Episode`, Red/Purple result, capture/telemetry paths, detector observations, environment snapshot.  
**OUTPUT:** `EpisodeReference` plus `EvidenceManifest` of typed items, hashes, sizes, capture time, source, completeness, synthetic status.  
**STATE EFFECT:** append-only references and verification result; raw bytes remain in capture store.  
**ERROR/FAILURE SEMANTICS:** missing/hash-changing evidence → invalid; telemetry unhealthy → response indeterminate; imported unverifiable data is quarantined.  
**PROVENANCE REQUIREMENTS:** original Episode ID/statuses/evidence refs and all runtime versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** same byte hashes deduplicate; changed manifest creates a new version and invalidates downstream gate passes.  
**OPERATOR BOUNDARY:** no operator can relabel synthetic/unverified evidence as real.

## 8. Signature and cousin classification

**PRODUCER:** signature builder/candidate retriever/cousin engine.  
**CONSUMER:** BIN, TGT, HND, HARV, temporal engine.  
**PURPOSE:** establish relationship and defense-response axes reproducibly.  
**INPUT:** verified evidence manifest, detector predicate results, context, reference/candidate source receipts, algorithm/calibration version.  
**OUTPUT:** `BehaviorSignature`, `CandidateSetReceipt`, `CousinAssessment` with per-dimension distances, relationship, response, confidence/completeness, reasons.  
**STATE EFFECT:** immutable versioned records and outbox emission.  
**ERROR/FAILURE SEMANTICS:** inadequate dimensions → anomalous/unclassified or indeterminate; semantic-only relation cannot produce similar/new; candidate-source outage is explicit.  
**PROVENANCE REQUIREMENTS:** every normalized feature cites evidence; mapping/index/detector/environment versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** pure for an immutable input/version; algorithm change produces a new assessment, never overwrite.  
**OPERATOR BOUNDARY:** operator promotion confirms impact, not the arithmetic; threshold-policy changes are separately approved.

## 9. Temporal baseline and drift assessment

**PRODUCER:** BR-DRIFT.  
**CONSUMER:** BIN, TGT, HND, observability.  
**PURPOSE:** detect and attribute temporal attack/detection change against matched controls.  
**INPUT:** matched `TemporalSample`s, active baseline, telemetry/control/environment/detection versions.  
**OUTPUT:** updated baseline state and `TemporalAssessment` with signals/bands/breaches/cause/confidence.  
**STATE EFFECT:** append sample; update sufficient statistics; supersede baseline on version reset.  
**ERROR/FAILURE SEMANTICS:** unmatched/insufficient sample → warm-up/unclassified; sensor failure has precedence over attack/detection labels.  
**PROVENANCE REQUIREMENTS:** sample and control evidence IDs, algorithm/window versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** one sample key contributes once; recomputation from stored samples must match.  
**OPERATOR BOUNDARY:** policy/critical-bound changes require approval; cause itself is deterministic.

## 10. Promotion gate

**PRODUCER:** BIN gate validators.  
**CONSUMER:** SUB, HEART, HND/feed coordinator.  
**PURPOSE:** enforce G0–G5 and terminal outcomes.  
**INPUT:** `GateEvaluationRequest` with alert/evidence expected versions and gate-specific structured records.  
**OUTPUT:** `ValidationResult` and legal `PromotionTransition`.  
**STATE EFFECT:** append result/event and advance only by compare-and-swap.  
**ERROR/FAILURE SEMANTICS:** stale evidence/version → conflict; unmet proof → failed/blocked, not model override; new manifest invalidates downstream passes.  
**PROVENANCE REQUIREMENTS:** validator code/config version and exact evidence IDs.  
**IDEMPOTENCY/RETRY BEHAVIOR:** same gate/input returns original; retry attempts are separately numbered.  
**OPERATOR BOUNDARY:** G5 is explicit promotion; no generic “approve all” action.

## 11. SOC delivery and visibility

**PRODUCER:** SOC adapter.  
**CONSUMER:** G3 validator and operator/analyst.  
**PURPOSE:** prove the Bully finding is visible in the real analyst-consumer path.  
**INPUT:** redacted `BullyFindingEnvelope`, destination/config version, correlation marker, SLO, optional replay-load profile.  
**OUTPUT:** `SOCDeliveryReceipt` with write acknowledgment, queried analyst-facing object, timestamps/latency, content-hash match, load profile.  
**STATE EFFECT:** external delivery plus durable receipt.  
**ERROR/FAILURE SEMANTICS:** producer ack without consumer query is insufficient; timeout/content mismatch → G3 fail/block.  
**PROVENANCE REQUIREMENTS:** destination, adapter, query, queue-load, and content hashes; secrets excluded.  
**IDEMPOTENCY/RETRY BEHAVIOR:** stable correlation key prevents duplicate notables where supported; repeated delivery is recorded.  
**OPERATOR BOUNDARY:** destination is configured/approved; this receipt does not authorize detector deployment.

## 12. Council, objection, and rebuttal

**PRODUCER:** independent council runner and reviewers.  
**CONSUMER:** HEART/G4 and operator.  
**PURPOSE:** attempt to disprove promotable claims.  
**INPUT:** frozen `CouncilPacket`, seat/roster snapshot, identical evidence manifest/version, schema prompt.  
**OUTPUT:** `CouncilOpinion`; zero or more durable `Objection`s; `Rebuttal`; re-review/withdrawal decision.  
**STATE EFFECT:** append-only opinions/objections/rebuttals; material open objections block G4.  
**ERROR/FAILURE SEMANTICS:** timeout/malformed/missing citation → abstention and seat incomplete; quorum/vote count never clears; unavailable mandatory seat blocks.  
**PROVENANCE REQUIREMENTS:** model/seat/prompt/inference versions, evidence citations, independence family.  
**IDEMPOTENCY/RETRY BEHAVIOR:** one opinion per seat/packet/attempt; changed evidence creates a new packet.  
**OPERATOR BOUNDARY:** only authorized, reasoned waiver may close a still-material objection; waiver is visible in handoff.

## 13. Cost, outcome, and plateau

**PRODUCER:** runtime metering/SCORE/PLT.  
**CONSUMER:** TGT, ORG, scheduler.  
**PURPOSE:** measure actual effort/yield and stop exhausted neighborhoods.  
**INPUT:** typed resource observations, pricing profile, valid-trial outcome, posterior history, reset versions.  
**OUTPUT:** `CostRecord`, `TargetOutcome`, updated `TargetStatistics`, `PlateauAssessment`.  
**STATE EFFECT:** append cost/outcome; update versioned sufficient statistics/status.  
**ERROR/FAILURE SEMANTICS:** material missing cost blocks ROI; infrastructure failures do not enter valid denominator; reset is explicit.  
**PROVENANCE REQUIREMENTS:** meter/source/profile and window/input versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** one cost component per source key; recompute posterior/window deterministically.  
**OPERATOR BOUNDARY:** override cannot fabricate a valid trial and requires reason/expiry.

## 14. Detection-engineering handoff

**PRODUCER:** HND after promotion.  
**CONSUMER:** detection engineer/operator and later Purple replay.  
**PURPOSE:** propose family-generalizing coverage without auto-deployment.  
**INPUT:** promoted finding, replay/evidence bundle, affected coverage cells/detections, drafting model output.  
**OUTPUT:** `DetectionProposal`, engineer disposition, optional `DeploymentReceipt`, post-deploy `CoverageValidation`.  
**STATE EFFECT:** proposal lifecycle; known-covered only after deployment receipt and successful real replay.  
**ERROR/FAILURE SEMANTICS:** rejected/revise/expired are explicit and feed learning; draft syntax is not coverage.  
**PROVENANCE REQUIREMENTS:** finding/evidence/rule/test/owner/detector versions.  
**IDEMPOTENCY/RETRY BEHAVIOR:** revisions supersede; deployment IDs deduplicate.  
**OPERATOR BOUNDARY:** engineer accepts and authorized deployment owner deploys; Bully has no production write authority.

## 15. Harvest and dataset release

**PRODUCER:** HARV from durable completed cases.  
**CONSUMER:** dataset builder/TRAIN.  
**PURPOSE:** create safe, traceable positive and negative learning examples.  
**INPUT:** source decision IDs/evidence, labels, objections/rebuttals, trust tier, leakage/group metadata.  
**OUTPUT:** quarantined `TrainingExample`; immutable `DatasetVersion` and split manifest after checks/approval.  
**STATE EFFECT:** examples append/supersede; release freezes dataset.  
**ERROR/FAILURE SEMANTICS:** missing provenance, suspect trust, secret/licensing issue, duplicate or split leakage → quarantine/exclude.  
**PROVENANCE REQUIREMENTS:** exact source hashes, transformation code/config, label authority.  
**IDEMPOTENCY/RETRY BEHAVIOR:** content fingerprint deduplicates; corrected label supersedes and forces new dataset.  
**OPERATOR BOUNDARY:** dataset release is explicit and separate from model promotion.

## 16. Playbook proposal and activation

**PRODUCER:** PLAY from recurring validated outcomes.  
**CONSUMER:** replay/canary runner, SUB, operator.  
**PURPOSE:** change future hunt actions safely.  
**INPUT:** evidence-linked proposal with applicability, allowed actions, budgets, stop/control rules, fallback.  
**OUTPUT:** versioned playbook, replay/canary validation, activation/rollback receipt, later `DecisionImpact`.  
**STATE EFFECT:** append versions; atomically move active pointer after approval; preserve rollback target.  
**ERROR/FAILURE SEMANTICS:** safety/regression/cost/yield failure rejects or auto-rolls back; draft never activates itself.  
**PROVENANCE REQUIREMENTS:** source decisions, generator, tests, canary and approver.  
**IDEMPOTENCY/RETRY BEHAVIOR:** activation CAS on active pointer; repeated command returns receipt.  
**OPERATOR BOUNDARY:** activation and override require authorization.

## 17. Training, evaluation, and model deployment

**PRODUCER:** TRAIN/orchestrated host-native trainer and Portal model importer.  
**CONSUMER:** acceptance evaluator, configured specialist role, operator.  
**PURPOSE:** prove and safely deploy specialist improvement.  
**INPUT:** released dataset, base digest, training/toolchain config, resource lock, five-arm frozen suite, acceptance policy.  
**OUTPUT:** `TrainingRun`, adapter/checkpoints, `EvaluationComparison`, accepted/rejected `TrainedModel`, GGUF/Ollama import receipt, canary/promotion/rollback receipt.  
**STATE EFFECT:** immutable artifacts and model lifecycle; active alias changes only after canary and operator command.  
**ERROR/FAILURE SEMANTICS:** resource/preflight/train/export/eval failure leaves active alias unchanged; policy miss rejects model; partial artifact quarantined.  
**PROVENANCE REQUIREMENTS:** dataset/base/code/toolchain/config/seeds/artifact hashes and all metrics.  
**IDEMPOTENCY/RETRY BEHAVIOR:** job key resumes compatible checkpoint; import by artifact hash; alias update CAS.  
**OPERATOR BOUNDARY:** dataset release, model promotion, and exceptional rollback override are separate approvals.

## 18. Bench acceptance

**PRODUCER:** component/integration/end-to-end validation runner.  
**CONSUMER:** build/release gate and ROSTER/TRAIN evaluation.  
**PURPOSE:** prove semantics and compatibility rather than symbol presence.  
**INPUT:** immutable suite manifest, fixtures/real-lab cases, implementation/config/model versions, expected invariants.  
**OUTPUT:** `ValidationRun` and claim-level `ValidationResult`s with evidence artifacts and resource metrics.  
**STATE EFFECT:** append-only evaluation records; no production truth promotion solely from a bench.  
**ERROR/FAILURE SEMANTICS:** skipped/unavailable required case is not pass; synthetic lanes cannot satisfy real-evidence claims; flaky retry count is explicit.  
**PROVENANCE REQUIREMENTS:** suite/case/code/config/environment/model/evidence hashes.  
**IDEMPOTENCY/RETRY BEHAVIOR:** run attempts are distinct; aggregation never hides a failed required invariant.  
**OPERATOR BOUNDARY:** release acceptance is operator-controlled after all mandatory results pass.

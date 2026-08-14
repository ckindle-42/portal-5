# Defensive Bully Validation Design

## Validation standard

Validation proves behavior, state, evidence, and safety at exact versions. A passing import, symbol, schema, prompt, unit mock, or generated narrative is never sufficient by itself. Required cases cannot pass by skip. Synthetic fixtures prove plumbing and deterministic logic but cannot satisfy real-evidence promotion, SOC, or full end-to-end claims.

Every run emits `ValidationRun`/`ValidationResult` records with code commit, config/schema/algorithm/model/environment/detection/telemetry versions, suite/case hashes, exact inputs, expected/observed outputs, evidence hashes, resource use, retries/skips, and failure meaning. Random/property tests record seeds. Statistical claims publish intervals and raw counts.

## Component validation

### C1 — Authoritative state survives and rejects illegal transitions

**CLAIM:** durable truth is restart-safe, append-only, and state-machine enforced.  
**TEST METHOD:** unit/property tests plus process-kill recovery at every transaction/external-call boundary; corrupt a copied database/evidence item; attempt stale/illegal transitions.  
**INPUT:** representative hunts, alerts, objections, outbox items, leases, supersessions.  
**EXPECTED BEHAVIOR:** committed events recover exactly once; uncommitted work does not appear; stable idempotency returns original receipt; stale/illegal commands fail; corruption blocks affected claims.  
**REQUIRED EVIDENCE:** database/event-chain audit, before/after snapshots, command receipts, recovery logs.  
**FAILURE MEANING:** no higher-level capability is trustworthy; release blocks.

### C2 — Evidence integrity and truth boundaries

**CLAIM:** every derived claim is traceable to immutable evidence and synthetic/unverified data cannot be promoted.  
**TEST METHOD:** mutate/delete bytes after manifest creation, import incomplete legacy evidence, mark fixtures synthetic, exercise G0.  
**INPUT:** real-like and synthetic Episodes, valid/tampered manifests.  
**EXPECTED BEHAVIOR:** valid hashes verify; tampering/missing data is invalid/quarantined; telemetry absence is indeterminate; synthetic never passes G0.  
**REQUIRED EVIDENCE:** manifest/hash verification and gate events.  
**FAILURE MEANING:** evidence-truth invariant is broken; release blocks.

### C3 — Outbox, projection, and recall

**CLAIM:** all required knowledge is eventually indexed exactly once and recall dereferences authority.  
**TEST METHOD:** inject embed/rerank/LanceDB outages, duplicate deliveries, worker death, stale rows, full projection deletion/rebuild.  
**INPUT:** records across all trust/supersession tiers.  
**EXPECTED BEHAVIOR:** transactional outbox has no lost record; duplicates converge; stale/hash-mismatched rows are rejected; rebuild is equivalent; required dead letter blocks hunt closure/recall.  
**REQUIRED EVIDENCE:** SQL source counts/hashes, outbox attempts, projection comparison, recall receipts.  
**FAILURE MEANING:** mandatory recall/compounding claim fails.

### C4 — Deterministic calculations

**CLAIM:** signatures, distance, temporal signals, ROI/posteriors, plateau, and gate legality are repeatable.  
**TEST METHOD:** golden vectors, property tests, boundary values, reordered JSON/DB rows, replay from stored inputs.  
**INPUT:** complete/missing dimensions, threshold edges, low/high sample counts, cost missingness.  
**EXPECTED BEHAVIOR:** same versions produce byte-equivalent canonical outputs; missing data is not renormalized/zeroed; threshold ties follow specification.  
**REQUIRED EVIDENCE:** golden artifacts and property-test reports.  
**FAILURE MEANING:** decision audit cannot be reproduced.

## Integration validation

### I1 — Current Red/Purple compatibility

**CLAIM:** Bully integration preserves existing Red execution and Purple result semantics.  
**TEST METHOD:** run golden current bench cases with feature off, shadow on, and Bully authoritative initiation; compare legacy outputs and tool traces.  
**INPUT:** successful, readiness/substitution, tool failure, telemetry failure, synthetic, replay cases.  
**EXPECTED BEHAVIOR:** feature-off is unchanged; shadow does not affect result; adapter preserves statuses/evidence/tool args; infrastructure failure is not discovery yield.  
**REQUIRED EVIDENCE:** diff/golden reports and existing security validation results.  
**FAILURE MEANING:** migration cannot proceed.

### I2 — Bounded inner loop

**CLAIM:** only grounded actions execute and all budgets are enforced, including lab actions.  
**TEST METHOD:** adversarial model outputs unknown actions, repeats/no-progress, tries budget overflow; kill between intent and receipt.  
**INPUT:** capability candidates and small lab/inference/wall/storage budgets.  
**EXPECTED BEHAVIOR:** unknown action denied; exact counters stop execution; recovery reconciles without duplicate lab action; honest blocked status.  
**REQUIRED EVIDENCE:** intent/action receipts, tool audit, budget ledger, recovery trace.  
**FAILURE MEANING:** safety/resource invariant fails.

### I3 — Thin CLI/MCP and configuration

**CLAIM:** transports call the same application contracts and do not own state.  
**TEST METHOD:** command equivalence, concurrent/retry/auth tests, service restart, normal startup without training extras.  
**INPUT:** create/read/cancel/promote/waive commands by permitted and denied roles.  
**EXPECTED BEHAVIOR:** equivalent receipts; denied commands have no state effect; restart safe; training libraries not imported; secrets absent from snapshots/logs.  
**REQUIRED EVIDENCE:** command/audit results, import trace, config hash.  
**FAILURE MEANING:** authority or operability boundary fails.

## Behavioral and cousin-discovery validation

### B1 — Spatial relationship is not semantic similarity

**CLAIM:** only multi-channel structural family relations become `SIMILAR`/`NEW`.  
**TEST METHOD:** curated paired corpus: semantically close but structurally different; semantically distant but same event/action structure; exact; meaningful family delta; unrelated anomaly. Blind labels from qualified security review before scoring.  
**INPUT:** verified signatures spanning all five structural distance dimensions, separate detector-response evidence, and missing-data cases.  
**EXPECTED BEHAVIOR:** exact→SAME; family-near→SIMILAR; security-relevant family extension→NEW; semantic-only→DIFFERENT/UNCLASSIFIED; far anomaly is not automatically NEW. At least two non-semantic proofs are stored.  
**REQUIRED EVIDENCE:** confusion matrix, calibration curve, per-dimension receipts, reviewer adjudication.  
**FAILURE MEANING:** core product definition fails.

### B2 — Relationship and response remain independent

**CLAIM:** every combination is representable and response follows detector evidence, not novelty.  
**TEST METHOD:** factorial fixtures/real replays for SAME/SIMILAR/NEW/DIFFERENT against covered/near-miss/missed/indeterminate.  
**INPUT:** stable detector predicates, healthy/failing telemetry, alert outcomes.  
**EXPECTED BEHAVIOR:** classification axes do not overwrite each other; SAME×MISSED is regression; NEW×COVERED is not a discovery miss; telemetry failure is indeterminate.  
**REQUIRED EVIDENCE:** assessment records and detector-predicate traces.  
**FAILURE MEANING:** targeting/promotion labels are unsafe.

### B3 — Unknown-cousin discovery yield

**CLAIM:** the complete system finds blinded structural cousins that known-label/token matching and current detectors miss.  
**TEST METHOD:** hold out whole cousin families/campaigns; run candidate retrieval and full classification without target labels; compare to legacy heuristic and known-bad baseline.  
**INPUT:** authorized real-lab/replay corpus with independent labels and benign controls.  
**EXPECTED BEHAVIOR:** meets the approved calibrated recall/precision policy, improves unknown-family discovery over legacy, and does not reduce known-bad recall. Threshold acceptance is fixed before final evaluation.  
**REQUIRED EVIDENCE:** frozen manifest, raw predictions, family-grouped metrics/intervals, errors.  
**FAILURE MEANING:** final calibration/design implementation is not accepted.

## Mutation validation

### M1 — Typed mutation safety and structural effect

**CLAIM:** plans stay in scope and create their declared structural delta while preserving invariants.  
**TEST METHOD:** schema/property/fuzz tests followed by one-dimension and approved multi-dimension real lab executions with cleanup verification.  
**INPUT:** every operator type, boundary/unknown parameters, scope/tool attacks, conflicting invariants.  
**EXPECTED BEHAVIOR:** unsafe/unknown/unbounded plans never compile; compiled orders use allowlisted tools/target; observed signature matches expected delta/invariants; cleanup succeeds or safety-blocks.  
**REQUIRED EVIDENCE:** validation/compiled plan, Red tool audit, before/after signatures, target snapshot.  
**FAILURE MEANING:** MUT cannot be enabled.

### M2 — Causal isolation

**CLAIM:** multi-dimensional mutation conclusions are not attributed without controls.  
**TEST METHOD:** introduce a confounded environment or telemetry change and omit a constituent control.  
**INPUT:** paired runs with/without matched controls.  
**EXPECTED BEHAVIOR:** confounded/under-controlled case is unclassified/blocked; controlled case can advance.  
**REQUIRED EVIDENCE:** control plan/results and G2 reasons.  
**FAILURE MEANING:** causal claims are invalid.

## Alert-bin and SOC-context validation

### A1 — Every gate is substantive

**CLAIM:** no alert can skip G0–G5 or reuse stale proof.  
**TEST METHOD:** attempt every illegal transition; replace manifest after each gate; test one-of-two nondeterministic successes, benign/control alternatives, unresolved objection, absent operator.  
**INPUT:** alerts at each state and pass/fail/block artifacts.  
**EXPECTED BEHAVIOR:** only legal same-version transitions pass; changed evidence invalidates downstream gates; terminal outcomes are explicit; no majority/prompt bypass.  
**REQUIRED EVIDENCE:** transition table coverage and audit chain.  
**FAILURE MEANING:** promotion safety fails.

### A2 — Reproduction and causality

**CLAIM:** promotion requires fresh execution plus clean replay (or declared 2/3 policy), healthy controls, and behavioral—not signature-only—reproduction.  
**TEST METHOD:** real lab paired cases: true miss, irreproducible event, signature-only artifact, benign causal alternative, telemetry outage, environment change.  
**INPUT:** isolated snapshots, controls, manifests.  
**EXPECTED BEHAVIOR:** only true reproducible causally supported case passes G1/G2; alternatives end benign/disproved/blocked.  
**REQUIRED EVIDENCE:** independent run artifacts, control health, causal predicate results.  
**FAILURE MEANING:** promoted discoveries are not credible.

### A3 — SOC visibility under consumer conditions

**CLAIM:** the Bully finding—not the missed detector—reaches the actual analyst-visible path intact and within SLO.  
**TEST METHOD:** deliver uniquely marked findings, query the same index/notable/dashboard analysts consume, add replayed normal and peak queue load, inject producer-only ack/content truncation/latency.  
**INPUT:** approved Splunk/SOC test destination and redacted finding envelope.  
**EXPECTED BEHAVIOR:** G3 passes only on consumer-query receipt, hash/content match, and SLO; missed underlying detector may remain silent.  
**REQUIRED EVIDENCE:** send and analyst-query receipts, latency/load metrics, content hashes.  
**FAILURE MEANING:** consumer-context requirement fails.

## Adversarial-council validation

### H1 — Material veto and independence

**CLAIM:** one material objection blocks regardless of other supports/reliability; reviewers are independent.  
**TEST METHOD:** 4 support/1 material reject, high-reliability support versus low-reliability material reject, reviewer timeout, information-leak prompt, duplicate model-family seats.  
**INPUT:** frozen evidence packets and controlled opinions.  
**EXPECTED BEHAVIOR:** material objection/mandatory missing seat blocks; reliability only changes eligibility/additional review; packet/opinions are isolated.  
**REQUIRED EVIDENCE:** packets, invocation boundaries, objections, roster snapshot, G4 result.  
**FAILURE MEANING:** self-bullying has degraded into voting.

### H2 — Rebuttal and waiver

**CLAIM:** rebuttal does not self-close; withdrawal requires evidence re-review, and waiver is explicit.  
**TEST METHOD:** rebut with unchanged prose, new valid evidence, irrelevant evidence; issue authorized/unauthorized waiver.  
**INPUT:** material objections across categories.  
**EXPECTED BEHAVIOR:** only originating/equivalent seat withdraws after cited review; unauthorized waiver denied; authorized waiver records identity/reason and remains visible downstream.  
**REQUIRED EVIDENCE:** objection/rebuttal/re-review/waiver chain.  
**FAILURE MEANING:** adversarial gate is not auditable.

## Temporal-drift validation

### T1 — Cause attribution with matched controls

**CLAIM:** attacker, detector, telemetry, and environment changes are separated.  
**TEST METHOD:** controlled time series independently change attack sequence, detector rule, sensor completeness, environment fingerprint, and ambiguous combinations.  
**INPUT:** adequate warm-up baselines plus matched controls.  
**EXPECTED BEHAVIOR:** each isolated change gets its specified cause; sensor failure takes precedence; environment change is not detector drift; ambiguity is unclassified.  
**REQUIRED EVIDENCE:** samples, bands/EWMA/distribution statistics, control results, cause reasons.  
**FAILURE MEANING:** temporal findings cannot enter promotion.

### T2 — Stability and reset

**CLAIM:** normal variance does not alert and version changes reset correctly.  
**TEST METHOD:** stationary/noisy series, isolated single noncritical spike, three consecutive breaches, critical breach, detection/telemetry/environment policy changes.  
**INPUT:** seeded/generated plus captured time series.  
**EXPECTED BEHAVIOR:** false-alert rate meets calibrated policy; consecutive/critical rules work; key changes start warm-up rather than inherit confidence.  
**REQUIRED EVIDENCE:** raw series, alert decisions, baseline supersession.  
**FAILURE MEANING:** drift engine is noisy or causally stale.

## Targeting, plateau, and cost validation

### R1 — Selection and measured ROI

**CLAIM:** selection uses hard eligibility, conservative posterior value, and nonzero measured cost without double counting.  
**TEST METHOD:** golden ranking, correlated-feature cases, low-sample uncertainty, missing cost, tie-break, readiness/authorization exclusions.  
**INPUT:** fixed target cells/statistics/recall/resource snapshots.  
**EXPECTED BEHAVIOR:** ineligible never ranks; low-sample confidence is conservative; missing cost blocks; deterministic tie-break; all factors and exclusions recorded.  
**REQUIRED EVIDENCE:** target decision and recomputation.  
**FAILURE MEANING:** hunt allocation is unauditable.

### R2 — Plateau and reset

**CLAIM:** only sufficiently tested exhausted neighborhoods stop, and material version changes reopen them.  
**TEST METHOD:** fewer than eight trials, single mutation dimension, blocked failures, low/high yield, promotion, each reset trigger.  
**INPUT:** controlled attempt windows/posteriors.  
**EXPECTED BEHAVIOR:** minimum/sample/diversity rules hold; infra failure excluded; plateau local only; reset explicit.  
**REQUIRED EVIDENCE:** trial membership and statistical assessment.  
**FAILURE MEANING:** system stops too early or wastes resources indefinitely.

## Compounding validation

### F1 — Six feeds change future behavior

**CLAIM:** each feed has an activated record and a later causal decision effect.  
**TEST METHOD:** paired deterministic runs from identical initial snapshots, one with the feed activated and one without. Exercise: recalled objection/control; known benign/covered outcome; updated ROI yield/cost; harvested negative/positive example in a released dataset; accepted specialist alias; active playbook.  
**INPUT:** source outcomes and subsequent hunt/eval decisions.  
**EXPECTED BEHAVIOR:** the later target ranking, control/action, model output metric, or playbook action changes exactly as policy predicts; `DecisionImpact` links the source. No-effect is honestly recorded.  
**REQUIRED EVIDENCE:** before/after snapshots, feed activation, recall/impact receipts, downstream outputs.  
**FAILURE MEANING:** persistence exists but compounding does not.

### F2 — Negative, contradiction, expiry, and poisoning resistance

**CLAIM:** negative outcomes learn without becoming permanent/global false certainty, and suspect content cannot control consequential decisions.  
**TEST METHOD:** insert contextual benign, disproved, blocked, contradictory, expired, malicious retrieved instructions, and superseded records at each trust tier.  
**INPUT:** later target/promotion requests.  
**EXPECTED BEHAVIOR:** scoped priors/actions adjust; blocked is not benign; contradiction forces review; expiry/version change removes stale influence; suspect/retrieved instructions cannot expand tools/scope or clear gates.  
**REQUIRED EVIDENCE:** known-state versions, exclusions, target/gate receipts, security audit.  
**FAILURE MEANING:** learning can poison or freeze the system.

## Detection-handoff validation

### D1 — Proposal-to-covered lifecycle

**CLAIM:** a promoted finding produces a complete family-level proposal, and coverage changes only after external deployment plus real replay.  
**TEST METHOD:** accept/reject/revise/expire proposals; simulate draft syntax pass without deployment; deploy a version then run positive/negative Purple replay.  
**INPUT:** promoted findings with evidence and benign controls.  
**EXPECTED BEHAVIOR:** no automatic rule write; all dispositions feed ORG; known-covered only after successful deployed-version replay and acceptable negative noise.  
**REQUIRED EVIDENCE:** proposal, engineer/operator/deployment receipts, replay artifacts, new coverage-cell state.  
**FAILURE MEANING:** detection-engineering exit is unsafe or fictitious.

## Training-improvement validation

### L1 — Dataset integrity and leakage resistance

**CLAIM:** released datasets are reproducible, provenance-complete, deduplicated, and split by family/campaign/time.  
**TEST METHOD:** deliberately add duplicates, variants of the same evidence, cross-split family, post-cutoff test-derived label, secret/unlicensed/suspect record.  
**INPUT:** HARV candidates across positive/negative/objection cases.  
**EXPECTED BEHAVIOR:** invalid examples quarantine; grouped split prevents leakage; released manifest reproduces exact ordered bytes; later correction creates new version.  
**REQUIRED EVIDENCE:** source hashes, dedup/leakage/group report, approval, dataset digest.  
**FAILURE MEANING:** no training run may be accepted.

### L2 — Specialist adds value beyond context

**CLAIM:** training, rather than retrieval/playbook alone, creates a generalizing gain.  
**TEST METHOD:** five-arm frozen evaluation on held-out families/campaign/time, bootstrap by family, current regression lanes and benign controls.  
**INPUT:** base and specialist exact artifacts, identical retrieval/playbook context and inference policy.  
**EXPECTED BEHAVIOR:** specialist+both beats base+both by at least +5 macro-F1 points with 95% bootstrap CI above zero and no >2-point regression in benign FPR, calibration, tool reliability, known-bad recall, or mandatory security lanes. Otherwise reject.  
**REQUIRED EVIDENCE:** immutable suite/outputs, metrics/CIs, artifact/config hashes, error analysis.  
**FAILURE MEANING:** specialist is not promoted; system remains functional with incumbent.

### L3 — Deployment, resources, and rollback

**CLAIM:** training is isolated/recoverable and model activation is reversible.  
**TEST METHOD:** memory/disk preflight failure, interruption/resume, export hash check, Ollama import, shadow/canary, induced canary regression, rollback.  
**INPUT:** accepted/rejected small representative runs and final candidate.  
**EXPECTED BEHAVIOR:** exclusive lock prevents conflicting lab work; failure leaves active alias unchanged; checkpoint resumes compatibly; hashes connect base→adapter→GGUF→tag; canary failure/rollback atomically restores prior alias.  
**REQUIRED EVIDENCE:** resource peaks/lock logs, lifecycle/artifact hashes, alias receipts, live health checks.  
**FAILURE MEANING:** TRAIN cannot activate artifacts.

## Performance/resource validation

### P1 — Bounded operation under reference-host limits

**CLAIM:** hunts, indexing/rebuild, council, and training respect configured memory/disk/time/concurrency limits on the 64 GB reference host.  
**TEST METHOD:** realistic peak hunt, reviewer concurrency, backlog/rebuild, evidence growth, and exclusive training/canary; inject dependency latency.  
**INPUT:** production-shaped corpus and budgets without destructive production changes.  
**EXPECTED BEHAVIOR:** admission control/budgets cap work; no unbounded queue or model residency; normal Ollama/embedding services recover; training and lab do not overlap; disk thresholds block safely.  
**REQUIRED EVIDENCE:** time series of RSS/disk/CPU/model residency/latency/queue/budget, block/recovery events.  
**FAILURE MEANING:** resource configuration must change before activation, not product scope.

## Regression validation

### G1 — Existing Portal/security behavior remains supported

**CLAIM:** new code does not break inference/workspace/MCP boundaries or current security benches.  
**TEST METHOD:** run current mandatory doc/spine/code-surface/config/import tests and relevant security/Blue/Purple/council/telemetry/model lanes; compare golden outputs where exact compatibility is promised.  
**INPUT:** current repository suites at implementation HEAD.  
**EXPECTED BEHAVIOR:** all required lanes pass or an explicitly accepted migration changes the golden with documented semantic reason; no generic RAG/memory contamination; no training-only startup import.  
**REQUIRED EVIDENCE:** unabridged command/results/artifacts and change mapping.  
**FAILURE MEANING:** implementation is not releasable.

## Final end-to-end proof

### E2E — Complete Defensive Bully lifecycle

**CLAIM:** the implemented system fulfills the complete product, not a disconnected feature set.  
**TEST METHOD:** on a clean authorized lab snapshot, seed a blinded known-family structural cousin that current detector misses; execute full runtime. Include a false/benign hypothesis, a material council objection requiring new evidence, dependency restart/outbox retry, SOC load, a detection proposal/deployment/replay, a later hunt, playbook canary, dataset/training comparison, model canary/rollback drill, and temporal detector-degradation case.  
**INPUT:** approved targets, real telemetry/detection/SOC path, frozen evidence labels and budgets.  
**EXPECTED BEHAVIOR:** mandatory recall precedes targeting; scoped mutation executes through unchanged Red; real evidence produces correct relation/response; false case is rejected; true case reproduces and passes causality/SOC; objection blocks until evidence re-review; operator promotes; all outbox/cost records close; detection handoff becomes covered only after deployment/replay; a later decision changes due to feeds; plateau/temporal rules work; specialist is promoted only if acceptance passes; rollback works; existing lanes remain green.  
**REQUIRED EVIDENCE:** one linked audit graph containing authorization, recall/target/mutation/Red/Episode/evidence/signature/classification/gates/SOC/opinions/objections/rebuttal/operator/outbox/cost/handoff/deployment/replay/feed-impact/playbook/dataset/evaluation/model/rollback records plus raw artifact hashes and resource traces.  
**FAILURE MEANING:** the full system is incomplete even if individual components pass.

## Release acceptance

Release requires C1–C4, I1–I3, B1–B3, M1–M2, A1–A3, H1–H2, T1–T2, R1–R2, F1–F2, D1, L1–L3, P1, G1, and E2E. Threshold calibration artifacts must be frozen before the held-out final runs. Any safety/truth/provenance failure is zero-tolerance. Statistical product thresholds may be revised only through an approved new policy followed by a completely rerun frozen evaluation; they may not be tuned on the final test results.

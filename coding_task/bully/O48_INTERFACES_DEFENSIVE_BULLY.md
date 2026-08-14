# INTERFACES_DEFENSIVE_BULLY

Contract for every boundary the Defensive Bully crosses. Each contract states:
**PRODUCER · CONSUMER · INPUT · OUTPUT · STATE EFFECT · ERROR · PROVENANCE ·
IDEMPOTENCY · OPERATOR BOUNDARY.** These are logical contracts (shapes and
guarantees), not signatures to copy verbatim; the coding session re-verifies
exact symbols at HEAD. Field names in `DATA_MODEL_DEFENSIVE_BULLY.md`.

Cross-cutting guarantees (apply to every contract unless overridden):
- **Determinism:** code decides verdicts/distance/gates/quorum; models only
  produce content. Same inputs → same decision.
- **Never-PROVEN:** any synthetic-derived step makes a verdict never PROVEN.
- **Label-blind:** production cousin-grading and gating never read ground-truth
  labels; only the offline harvest oracle may (check BM).
- **Honest-BLOCKED:** on missing capability/evidence, block with a reason; never
  fabricate a pass.
- **Provenance:** every persisted record carries source authority + origin.
- **Operator confirm:** consequential promotions halt (`PROMOTE_POLICY=confirm`).

---

## 1. RED ← Bully (scenario direction)
- **PRODUCER:** MUT / LOOP. **CONSUMER:** `exec_chain` executor + `lab`.
- **INPUT:** a scenario dict `{name, target_host, target_port, vulhub_env,
  red_order[], red_prompt, detect_ground_truth[], persistence_technique}` (the
  existing `SCENARIOS` shape; passed as data, as `candidate_eval._prepare_scenario`
  already does).
- **OUTPUT:** none back to Bully at this boundary (Red emits telemetry consumed
  via the Episode contract).
- **STATE EFFECT:** lab VMs mutate; a clean Proxmox snapshot is taken/restored
  around the run (`lab.snapshot_lab_vms`/`restore_lab_vms`).
- **ERROR:** lab-unreachable / dispatch failure → run marked UNAVAILABLE; no
  Episode PROVEN.
- **PROVENANCE:** scenario origin recorded (known-reference id + mutation lineage
  if mutated).
- **IDEMPOTENCY:** each run is against a clean snapshot; re-running the same
  scenario dict reproduces the same correlation shape (the G1 assumption).
- **OPERATOR BOUNDARY:** red runs only in the isolated lab; the executor is never
  modified — the Bully may only choose/perturb scenario data.

## 2. EPISODE (Red-side telemetry → Bully)
- **PRODUCER:** purple path (`blue.py` / `agentic_blue_eval.py` / corpus benches)
  via `episode.derive_verdict`. **CONSUMER:** BR-COUSIN, BR-DRIFT, BIN, SCORE.
- **INPUT:** landed red trajectory + fetched telemetry (`blue._fetch_blue_telemetry`,
  `source ∈ {live, synthetic-fallback, synthetic}`).
- **OUTPUT:** immutable `Episode{verdict ∈ PROVEN|FAILED|INDETERMINATE|UNAVAILABLE,
  correlations[DetectionCorrelation per technique], evidence_refs[], used_synthetic}`.
- **STATE EFFECT:** none (immutable value); persisted downstream by SUB/ORG.
- **ERROR:** no telemetry → UNAVAILABLE; ambiguous → INDETERMINATE.
- **PROVENANCE:** `source` tag per correlation; evidence refs point at raw
  telemetry.
- **IDEMPOTENCY:** deterministic from inputs; recomputable.
- **OPERATOR BOUNDARY:** none (read-only fact).

## 3. LOOP (orchestration)
- **PRODUCER:** `core loop run` (operator/CLI). **CONSUMER:** all components.
- **INPUT:** goal + chosen neighborhood (TGT), class playbook (PLAY), budget/caps.
- **OUTPUT:** `EngagementState` (checkpointed), per-iteration findings, terminal
  status `ENGAGEMENT_{COMPLETE|ESCALATED|STUCK}` with a `resume_cmd`.
- **STATE EFFECT:** writes SUB (outcome, cost, decisions), indexes ORG, extracts
  HARV pairs, updates PLT.
- **ERROR:** hard-cap hit (50 iters / 7200 s / 200 actions) → checkpoint + STUCK
  notify; resumable.
- **PROVENANCE:** decision-event log entry per act/verify.
- **IDEMPOTENCY:** resume from checkpoint is safe (re-entrant); acts are guarded
  by snapshot lifecycle.
- **OPERATOR BOUNDARY:** promotions inside the loop halt for confirm.

## 4. ORG (semantic hunt memory)
- **PRODUCER:** LOOP (`index_emission`). **CONSUMER:** BR-COUSIN (`nearest`),
  LOOP (`require_recall`).
- **INPUT (index):** an emission (episode/finding/verdict/objection/cousin
  judgment/plateau) with metadata. **INPUT (query):** an embedding query + k.
- **OUTPUT (query):** ranked nearest known references with scores + metadata.
- **STATE EFFECT:** LanceDB vector + FTS index grows (append); no deletion.
- **ERROR:** embed/rerank service down → dense-only fallback (degraded, flagged);
  recall precondition unmet → hunt refuses to start (tool-enforced).
- **PROVENANCE:** each indexed emission carries origin + authority.
- **IDEMPOTENCY:** indexing is keyed by emission id (re-index overwrites same
  key, no duplicates); query is pure.
- **OPERATOR BOUNDARY:** none; but ORG retrieval feeds hunt context only, never
  model long-term memory at inference (seven-kinds rule #7).

## 5. SUB (persistent substrate)
- **PRODUCER:** LOOP, BIN, HND, TRAIN. **CONSUMER:** TGT, PLT, LOOP, audit.
- **INPUT:** coverage cell updates, known-benign/covered/dead records, baseline
  points, cost entries, decision events, promotions, supersessions.
- **OUTPUT:** current coverage/known-cells/cost/baseline views on read.
- **STATE EFFECT:** durable append-only writes; records superseded, never
  deleted.
- **ERROR:** store unavailable → hunt refuses (SUB is required, not optional).
- **PROVENANCE:** `SourceAuthority` + supports/contradicts on every record.
- **IDEMPOTENCY:** writes keyed by record id; supersede is monotonic.
- **OPERATOR BOUNDARY:** promotions and known-benign classifications that
  suppress future hunts are operator-visible; a wrong benign mark is reversible
  by supersession.

## 6. BR-COUSIN (spatial classification)
- **PRODUCER:** LOOP. **CONSUMER:** BIN, SCORE, HND.
- **INPUT:** an Episode + the k nearest ORG references.
- **OUTPUT:** `{band ∈ SAME|SIMILAR|NEW|DIFFERENT|ANOMALOUS_UNCLASSIFIED, D,
  per_axis{behavioral,attack,telemetry,detection_response,semantic}, nearest_ref,
  explanation}`.
- **STATE EFFECT:** none (pure); result persisted by LOOP.
- **ERROR:** no references (cold ORG) → ANOMALOUS_UNCLASSIFIED with low
  confidence (honest, not a crash).
- **PROVENANCE:** cites the matched reference id + overlapping features.
- **IDEMPOTENCY:** deterministic given inputs.
- **OPERATOR BOUNDARY:** none (a classification, not a promotion).

## 7. BR-DRIFT (temporal classification)
- **PRODUCER:** LOOP / scheduled. **CONSUMER:** SUB, alarm, HND.
- **INPUT:** `(technique, detection)` + a new firing signature.
- **OUTPUT:** `{drift: bool, cause ∈ attacker_evolution|telemetry_failure|
  environmental|detection_degradation, stats}`.
- **STATE EFFECT:** appends a baseline point (SUB); INSUFFICIENT_BASELINE until
  min-baseline reached.
- **ERROR:** telemetry source absent → `telemetry_failure` (routed to ops, not
  the bin).
- **PROVENANCE:** baseline window + model-constant proof (`model-canary`) recorded.
- **IDEMPOTENCY:** appending the same point is deduped by timestamp+signature.
- **OPERATOR BOUNDARY:** `attacker_evolution` may raise a suspect finding →
  normal confirm path; a lineage change is informational.

## 8. BIN (gated promotion)
- **PRODUCER:** LOOP. **CONSUMER:** HEART, SCORE.
- **INPUT:** a suspect finding (Episode + BR grade).
- **OUTPUT:** `promotable` (all of G0–G3 pass) or `non_finding{failed_gate,
  reason}`.
- **STATE EFFECT:** G1 takes/restores a clean snapshot; non-findings write SUB
  known-cells (feed 2).
- **ERROR:** replay lab failure → G1 INDETERMINATE (not a pass, not a silent
  drop).
- **PROVENANCE:** each gate records its evidence (snapshot id, benign-corpus
  result, notable id).
- **IDEMPOTENCY:** gates are re-runnable; G1 is snapshot-clean each time.
- **OPERATOR BOUNDARY:** only all-pass findings proceed; promotion itself is
  confirmed downstream.

## 9. HEART (adversarial council)
- **PRODUCER:** BIN (promotable finding). **CONSUMER:** SCORE, operator.
- **INPUT:** finding + evidence refs; council roster (bounded).
- **OUTPUT:** `{decision ∈ PROMOTE_ELIGIBLE|BLOCK|ESCALATE|ANOMALOUS, opinions[],
  material_objections[], dissent}`.
- **STATE EFFECT:** none directly; transcript + decision logged to SUB.
- **ERROR:** quorum unreached → ESCALATE (not a default-pass); seat/model
  unavailable → counts against roster denominator (check BL).
- **PROVENANCE:** per-seat opinion + objection retained; disagreement→ANOMALOUS
  mapping preserved.
- **IDEMPOTENCY:** re-running with the same roster+evidence yields the same gate
  decision (code); model prose may vary but does not change the decision.
- **OPERATOR BOUNDARY:** an unrebutted material objection **blocks**; the operator
  cannot be asked to confirm a blocked finding without a rebuttal that satisfies
  the objection in evidence.

## 10. MUT (cousin generation)
- **PRODUCER:** LOOP. **CONSUMER:** RED (via scenario dict).
- **INPUT:** a known reference scenario + mutation budget (dimensions, distance).
- **OUTPUT:** `[scenario dict]` — structurally valid, within budget.
- **STATE EFFECT:** none (generation); lineage recorded when a mutant lands.
- **ERROR:** a mutation that violates the grammar is rejected pre-dispatch (not
  sent to red).
- **PROVENANCE:** each mutant carries `parent_ref` + mutated dimensions.
- **IDEMPOTENCY:** seedable/deterministic given (reference, budget, seed).
- **OPERATOR BOUNDARY:** mutation budget is an operator dial; red execution
  unmodified.

## 11. DRIFT baseline engine (shared)
- **PRODUCER/CONSUMER:** BR-DRIFT and PLT both consume the `drift_gate`
  rolling-baseline primitive.
- **INPUT:** a labeled series + a new point. **OUTPUT:** `{delta, z, verdict ∈
  STABLE|DRIFT|INSUFFICIENT_BASELINE}`.
- **STATE EFFECT:** none (pure stats); series stored by the caller (SUB).
- **ERROR:** < min-baseline → INSUFFICIENT_BASELINE.
- **IDEMPOTENCY:** pure. **OPERATOR BOUNDARY:** thresholds are config.

## 12. SCORE (distance-graded value)
- **PRODUCER:** BR-COUSIN + BIN + HEART. **CONSUMER:** scoreboard, TGT (yield),
  operator.
- **INPUT:** finding + band + distance + gate/council outcome.
- **OUTPUT:** `{value, trustworthiness_rank, scoreboard_entry}`.
- **STATE EFFECT:** scoreboard + yield stats to SUB.
- **ERROR:** none (pure math).
- **INVARIANT:** a far NEW cousin can exceed a known-bad in value, but ANOMALOUS
  is never ranked below CONFIRMED (check BN).
- **IDEMPOTENCY:** pure. **OPERATOR BOUNDARY:** none.

## 13. TGT (target selection)
- **PRODUCER:** LOOP (pre-hunt). **CONSUMER:** LOOP/MUT.
- **INPUT:** SUB (coverage, known-cells, yield, cost) + ORG density + `capability_
  graph` gaps.
- **OUTPUT:** a ranked list of cousin-neighborhoods with `risk_reduction/cost`
  scores; the chosen neighborhood.
- **STATE EFFECT:** records the target decision (SUB decision log).
- **ERROR:** all cells known/dead → returns "no positive-EV target" (a valid
  stop, not a crash).
- **PROVENANCE:** cites the inputs that drove the score.
- **IDEMPOTENCY:** deterministic given state.
- **OPERATOR BOUNDARY:** weights are operator dials; a known-benign suppression is
  operator-reversible.

## 14. PLT (plateau + cost)
- **PRODUCER:** LOOP (post-hunt). **CONSUMER:** TGT.
- **INPUT:** neighborhood discovery-transition history + cost ledger.
- **OUTPUT:** `{plateaued: bool, transition_rate, cost_per_cousin}`.
- **STATE EFFECT:** plateau record to SUB.
- **ERROR:** insufficient history → not-plateaued (keep hunting) with a note.
- **IDEMPOTENCY:** deterministic. **OPERATOR BOUNDARY:** floor/window are config.

## 15. HND (detection-engineering exit)
- **PRODUCER:** operator confirm (post-HEART). **CONSUMER:** live detection set
  (via operator), SUB.
- **INPUT:** a promoted cousin + its family (nearby NEW cousins).
- **OUTPUT:** a detection package `{generalized_sigma, spl_change, log_sources[],
  attack_mapping, evidence, reproduction, fp_analysis, limitations, ir_implications,
  regression_test, coverage_delta}` + proof (`growth_loop` three legs).
- **STATE EFFECT:** on confirm, updates `spl_detections`/coverage (SUB); records
  promotion.
- **ERROR:** proof leg fails (fires-on-benign, or regresses) → package BLOCKED,
  not deployed.
- **PROVENANCE:** links to the finding, council decision, and family members.
- **IDEMPOTENCY:** package generation is deterministic given the family; deploy
  is operator-gated and idempotent (re-deploy is a no-op if unchanged).
- **OPERATOR BOUNDARY:** deployment into the live detection set is confirm-only.

## 16. HARV (training-pair harvest)
- **PRODUCER:** LOOP (offline). **CONSUMER:** TRAIN.
- **INPUT:** hunt emissions + council transcripts + cousin judgments (+ labels,
  offline only).
- **OUTPUT:** role-tagged jsonl (positive / adversarial / distance pairs) +
  dataset version.
- **STATE EFFECT:** dataset artifact + version recorded in SUB.
- **ERROR:** corpus below a minimum size → documented non-build (no training
  attempted), not a skipped-silent feed.
- **PROVENANCE:** each pair cites its source emission; `recall_attribution`
  attribution recorded.
- **IDEMPOTENCY:** dataset keyed by version + content hash.
- **OPERATOR BOUNDARY:** the label-blind boundary (BM) is enforced — labels enter
  only this offline path, never the production grader.

## 17. PLAY (playbook lifecycle)
- **PRODUCER:** LOOP outcomes. **CONSUMER:** LOOP decide-step, TRAIN (as a small
  model's runtime shaping).
- **INPUT:** per-class hunt outcomes (yielding mutations, dead cells).
- **OUTPUT:** a versioned refined playbook (scope/budget/stop/escalate + learned
  hints).
- **STATE EFFECT:** new playbook version (SUB/config).
- **ERROR:** none (accumulation); a bad hint is superseded.
- **PROVENANCE:** version lineage + the outcomes that justified each change.
- **IDEMPOTENCY:** versioned; re-deriving from the same outcomes is stable.
- **OPERATOR BOUNDARY:** a promoted playbook version is operator-confirmed before
  it shapes runtime.

## 18. TRAIN / DEPLOY (model lifecycle)
- **PRODUCER:** `core train` (offline). **CONSUMER:** fleet config (via operator).
- **INPUT:** a HARV dataset version + a base model.
- **OUTPUT:** `mlx_lm.lora` adapter → `mlx_lm.fuse` fused model → GGUF (llama.cpp
  convert+quantize) → `ollama create` named model → acceptance report.
- **STATE EFFECT:** a trained-model artifact + version; fleet config updated only
  on confirm.
- **ERROR:** GGUF-convert tool absent → TRAIN halts with a clear blocker (feeds
  1–4/6 continue); acceptance regression → model DECLINED (catastrophic-
  forgetting guard).
- **PROVENANCE:** model version ← dataset version ← source emissions; full chain
  recorded.
- **IDEMPOTENCY:** training keyed by (dataset version, base, hyperparams, seed);
  redeploy re-points config (reversible rollback to prior model).
- **OPERATOR BOUNDARY:** serving a trained model is confirm-only; runs offline,
  never concurrent with a live hunt.

## 19. ACCEPTANCE / BENCH (model gate)
- **PRODUCER:** TRAIN. **CONSUMER:** operator.
- **INPUT:** a candidate (trained) model, single-slot.
- **OUTPUT:** `candidate_eval` delta-vs-incumbent + `model-canary` behavioral
  drift, in isolated `results/candidates/`.
- **STATE EFFECT:** isolated results only; the self-index baseline is never
  polluted.
- **ERROR:** bench failure → report BLOCKED; no fleet change.
- **PROVENANCE:** delta report cites incumbent + candidate + scenarios.
- **IDEMPOTENCY:** isolated + repeatable.
- **OPERATOR BOUNDARY:** `PROMOTE_POLICY=confirm`; reports deltas, never swaps
  fleet config autonomously.

---

## Contract invariants summary

- The **Episode** is the sole Red→Bully data contract; Red exposes nothing else
  and consumes only scenario dicts.
- **Code-decided** outputs (verdict, band, gate result, quorum, objection
  materiality, value, ranking, plateau) are deterministic and reproducible;
  model outputs are content only.
- Every persistent write is **append-only + superseding**, carries provenance,
  and is keyed for idempotency.
- Every capability gap fails **honest-BLOCKED**.
- Every consequential promotion is **operator-confirmed**.
- The **label-blind** boundary (BM) and the **seven-memory-kinds** taxonomy hold
  across all contracts.

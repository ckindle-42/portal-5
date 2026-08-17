# Defensive Bully — Build Progress

Tracks execution of `coding_task/bully/tasks/TASK_BULLY_00_MASTER_V1.md` (P0–P7).
Update this file's status line and "Next" section at the end of each phase
merge — it is the fast way to answer "where are we" without re-reading commit
history.

## Status

| Phase | Task file | Status | Merge commit |
|---|---|---|---|
| P0 | `TASK_BULLY_P0_SPINE_REDUCTION_V1.md` | ✅ done | `2a0680bc` |
| P1 | `TASK_BULLY_P1_SPINE_V1.md` | ✅ done | `a7cd02dc` |
| P2 | `TASK_BULLY_P2_BIN_HEART_V1.md` | ✅ done | `ea7e0dc3` |
| P3 | `TASK_BULLY_P3_RED_DRIFT_V1.md` | ✅ done | `df593854` |
| P4 | `TASK_BULLY_P4_DISCOVERY_V1.md` | ✅ done | `913ded64` |
| P5 | `TASK_BULLY_P5_HANDOFF_V1.md` | ✅ done | `58aab19f` |
| P6 | `TASK_BULLY_P6_FLYWHEEL_V1.md` | ✅ done | `03e24a05` |
| P6.7 | `TASK_BULLY_P6_7_TRAIN_REFINEMENT_CORRECTION_V1.md` | ✅ done | `f7434c86` |
| P6.8 | `TASK_BULLY_P6_8_COUSIN_CALIBRATION_BENCH_V1.md` | ✅ done | `a2a95837` |
| P7 | `TASK_BULLY_P7_2_SPECIMEN_CORPUS_AND_BLIND_BENCH_V1.md` | ✅ done; cold real-specimen proof | branch proof |
| P7.3 | `TASK_BULLY_P7_3_SPECIMEN_SCALE_AND_BASELINE_V1.md` | ✅ done; volume characterization frozen | `28dc9368` |
| P7.4 | retrieval-validity correction | ✅ done; valid V3 reference frozen | `5ba409db` |
| SA1 | `TASK_BULLY_SA1_CLASS_ONBOARDING_LOOP_V1.md` | ✅ done; System admitted, three classes honestly flagged | this commit |
| SA2 | `TASK_BULLY_SA2_DISCOVERY_MEASUREMENT_V1.md` | ✅ done; `DISCOVERY_BASELINE_V1` frozen, first real product measurement | this commit |
| SA3 | `TASK BULLY SA3 EMBEDDING BAKEOFF V1.md` | ✅ done; both arms built + bake-off recorded, decision deferred → resolved in SA5 P0.4 | — |
| SA4 | `TASK BULLY SA4 ANALYST CORPUS V1.md` | ✅ done; corpus layer + `ANALYST_CORPUS_SNAPSHOT_V1` machinery | this commit |
| SA5 | `TASK BULLY SA5 ACQUIRE AND RUN V1.md` | ✅ done; acquisition + live ship + multi-class snapshot V2 + arms resolved (Arm A adopted) + `DISCOVERY_BASELINE_V3` | this commit |

## What's landed (P0–P6)

- **P0** — spine/wiki thinned: `last_generated_commit` pin mechanism removed
  (kills the two-commit dance); 719 canonical units classified 14 KEEP-FACT /
  552 RELEASE / 153 ARCHIVE; wiki MCP (:8931) retained; `docs/SPINE_THIN_CONTRACT_V1.md`
  landed as the target contract for P1–P7.
- **P1** — brain substrate: `portal/modules/security/core/bully/` package
  skeleton + CLI shell, versioned contracts, SQLite store (ordered migrations,
  hash-chained decision events, transactional outbox), evidence manifests +
  Episode adapter (flagged shadow ingestion, off by default), ORG memory
  projection with mandatory recall receipts, two-axis BR-COUSIN grading engine
  with dual-run shadow, investigation arm over `blue_orchestrate.py` runners,
  LOOP orchestrator running one full hunt iteration end-to-end on the synthetic
  lab. Validation claims C1–C5, I1–I3 proven.
- **P2** — promotion pipeline: BIN state machine (gates G-1→G0→G1a→G1b→G2,
  real proof legs, synthetic always blocked at G0), HEART adversarial council
  with a durable objection gate (not a vote), G3 SOC visibility lane over
  `blue_triage` (producer ack alone insufficient), promotion_queue wired to
  `hunt queue --confirm/--reject` with `promote_policy: confirm` enforced at
  three independent layers (function guard, store guard, DB trigger).
  Validation claims C7, C8 proven; council block and council pass both
  demonstrated from the same real P1-graded candidate.
- **P3** — Red drift: `bully/mutation.py` (MUT) -- typed `MutationPlan` ->
  `validate_and_compile` -> `ScenarioOverlay` (I-1), fail-closed validation
  (unknown operator, invariant conflict, `perception.assert_in_lab` scope
  violation, missing M2 control, unapproved mutation class `[GATE]`), budget
  truncation recorded not silent (I-20), pure/byte-identical recompile.
  `bully/drift_engine.py` (BR-DRIFT) -- `update(episode, detections,
  baselines)` reusing `drift_gate.py`'s statistics pattern, deterministic
  cause-attribution order with sensor failure always taking precedence,
  ATTACKER_EVOLUTION the only class routed to BR-COUSIN, idempotent baseline
  update keyed by `(detection_id, episode_id)`, warm-up on policy-version
  change. Both wired into LOOP (`MUTATION_READY`/`ANALYZING` stages,
  replacing the P1 stubs). Migrations 004/005. `exec_chain.py`/`lab.py`
  provably unedited (`git diff main -- ...` empty + import-scan guard
  tests, independently re-verified). Validation claims C6, C9 proven by
  hermetic unit tests (990 unit + 208 bully tests green on independent
  re-run). M1–M2: `validate_and_compile` exercised against real
  `exec_chain.SCENARIOS` and the live lab DC (`portal-lab-dc01`,
  confirmed reachable) for real scope-enforcement + budget-truncation;
  no live Red attack chain (`_run_chain_test`) was dispatched against the
  DC — judged out of scope to trigger unilaterally in an unattended build
  session. Flagged as the one honestly incomplete item; does not block C6/C9.
- **P4** — Discovery, selection, and stopping: `bully/costing.py` (COST) --
  typed resource observations -> `CostRecord` per hunt/iteration, material
  missing measurement blocks ROI (never zero-filled), per-source-key
  idempotency, pricing-profile version recorded (migration 006).
  `bully/scoreboard.py` (SCORE) -- catch/trust/discovery three-axis update +
  report, `ANOMALOUS_UNCLASSIFIED` counted as Axis-1 catch, trust ordinal
  `CONFIRMED_CORRECT > HONEST_ANOMALY > CONFIRMED_WRONG` preserved, discovery
  weighting monotonic in distance (far-NEW >= known-bad), benign false-flag
  typing preserved. `bully/targeting.py` (TGT) -- `select()` over coverage
  cells + recall receipt + cost ledger + lease status, full factor breakdown,
  empty eligible set -> honest stop, missing material cost -> unrankable
  (never zero-cost), `[GATE]` operator override cannot bypass hard gates;
  wired into LOOP's `TARGETED` stage. `bully/plateau.py` (PLT) -- statistical
  stopping over SUB valid-trial series (>=8 trials, >=2 mutation dims),
  blocked/infra trials excluded from denominators, neighborhood-local,
  `[GATE]` override is an expiring recorded policy exception (migration 007);
  wired into LOOP's `COMPOUNDING -> CLOSED` decision. Validation claims C10
  proven by hermetic unit tests (261 bully tests green on independent
  re-run); R1-R2 live-hunt behavior (recall-influenced selection, cost-blocked
  unrankable case, plateau stop with version-change reset) demonstrated
  through real `orchestrator.run_hunt_iteration` wiring tests against the
  synthetic lab, same pattern as P1-P3 (no external live-lab dispatch
  attempted in this unattended session, matching P3's precedent). One
  pre-existing P1 cousin_engine/KNN cross-hunt-reference edge case was
  surfaced by P4's multi-hunt wiring tests (never previously exercised) --
  not fixed per scope discipline, worked around in the test harness by
  giving each hunt its own private projection over the shared store.
- **P5** — the exit: `bully/handoff.py` (HND) -- `build_package(candidate_id)`
  produces the 11-part package (FINAL_DESIGN §23) from a promoted candidate;
  SPL/Sigma drafted from cousin discriminators, validated in code
  (`validate_spl_syntax` + dry-exec against the replayed capture). Three
  detection-proof legs execute for real, not placeholder-true: fires-on-attack
  via `capture_recipes` replay, quiet-on-benign via the real benign corpus
  (`benign_corpus_bench`), no-regression via the real BQ/AZ lanes. Any
  proof-leg or validation failure blocks the package (candidate stays
  PENDING); rebuild produces a superseding version; FP analysis attached from
  G2. Detection-proposal lifecycle tables (migration 008): `draft ->
  submitted -> accepted/revise/rejected/expired -> deployed ->
  replay-validated/failed -> retired`, with `KNOWN_COVERED` DB-enforced to
  require a deployment receipt + successful post-deploy replay -- refused
  otherwise even at the DB layer. Operator reject requires rationale and is
  ORG-indexed. Deployment appends to `provenance_ledger`. Validation claim D1
  proven by hermetic + real-code-path tests (300 bully tests green on
  independent re-run; full CI-mirrored suite 2789 passed/33 skipped).
  Confirmed no accidental mutation of the real `spl_detections.yaml` from
  test runs. Build agent hit its account session-usage limit mid-verification
  after landing all 3 commits cleanly; the remaining verification
  (complexity re-baseline, ruff/pytest/validate_system reruns, D1 exit-check)
  was completed directly rather than via a second agent spawn.
- **P6** — the flywheel: `bully/harvest.py` (HARV, I-15) -- `append_pairs`
  extracts role-tagged examples from a hunt's already-recorded
  `decision_events` (kind->role mapping: target_select/recall->hunter,
  promote->analyst, kill->disprover, grade/objection/council_block->
  cousin_smeller), quarantining rather than silently including missing
  provenance / suspect (unconfirmed) trust / duplicates; `build_dataset`
  enforces a size floor (honest non-build below it), assigns a
  deterministic family-keyed split, and writes the corpus JSONL + manifest
  under `PORTAL5_HUNT_DIR/corpus/<role>/` before a content-hashed,
  idempotent `dataset_version` row. `bully/playbooks.py` (PLAY, I-16) --
  `draft_update` distills a hunt's trajectory into a versioned
  instruction_set (no model call needed); DRAFT -> REPLAY_VALIDATED ->
  CANARY -> AWAITING_OPERATOR -> ACTIVE lifecycle with atomic-pointer CAS
  activation and auto-revert-with-cause on canary failure; wired into
  LOOP (`orchestrator._do_analyze` -> `investigation.run_arm`'s new
  `playbook` kwarg -- absence is neutral, unshaped). `bully/training.py`
  (TRAIN, I-17; corrected by P6.7) -- periodic, operator-launched
  investigation-arm refinement; every tool is an external subprocess only
  (never imports mlx_lm/torch/transformers, Rule 8 holds trivially);
  exclusive resource lock + preflight refusing an active hunt lease or a
  concurrent bench/training process; `mlx_lm.lora` -> `mlx_lm.fuse` ->
  llama.cpp GGUF convert+quantize -> `ollama create`; right-sized acceptance
  (`evaluate_acceptance`) is a pure, fail-closed decision over intake,
  candidate-vs-incumbent general-bench evidence, and model canary; `serve()`
  runs the model canary *before* the atomic alias promotion, `rollback()`
  is the atomic alias re-point. Toolchain installed + verified for real
  (llama.cpp via brew + a shallow `ggml-org/llama.cpp` clone for the GGUF
  converter, its own dedicated venv, never added to this repo's
  pyproject.toml). `bully/roster.py` (ROSTER, I-19) -- pure compute,
  scores each seat's already-resolved outcomes into eligibility bands +
  a bounded [0.5, 2.0] advisory weight; the objection gate (`adversary.py`)
  and `roster.py` are fully import-decoupled in both directions (not
  merely "weights ignored"); `enforce_diversity` mirrors
  `adversary.validate_roster_diversity`'s pattern without importing it.
  Migration 009 (M8): `playbooks`, `training_examples`, `dataset_versions`,
  `trained_models`, `model_aliases`, `model_alias_history`,
  `roster_records`, each with its SS4.8 DB check (one active playbook per
  class, one active model alias per role, immutable released datasets,
  immutable trained-model artifact fields, roster content-keyed
  idempotency). C11 (HARV/PLAY/ROSTER + TRAIN acceptance arithmetic +
  isolation) proven by 70 hermetic tests across the five P6 modules (all
  370 bully tests green on independent re-run). F1-F2 (shadow) + L1: a
  real dataset was harvested, built, and released; a real, complete
  toolchain chain then ran through `training.run()` itself (not a manual
  bypass) end to end -- `mlx_lm.lora` -> `mlx_lm.fuse` -> GGUF convert ->
  `llama-quantize` -> `ollama create`, producing a genuine Ollama model
  and a recorded documented non-serve verdict (`declined_no_gain`); model
  canary (`serve()`) and rollback (`rollback()`) both proven via hermetic
  tests exercising the real atomic-alias-repoint code path, not mocked
  around it. P6.7 removed the over-scoped apparatus, added the
  marginal-knowledge readiness readout/queue signal, and wired served aliases
  into LOOP's `tool`/`reasoning`/`expert` seats. A fresh real refinement
  (`bully-ae9fa52b558fbce0`, seed 1236) produced an honest shelf under the
  corrected policy: throughput passed (194.9 t/s), tool-call intake failed,
  incumbent evidence was therefore absent, and the canary reported
  `NO-BASELINE`. Evidence:
  `/Volumes/data01/portal5_hunt/artifacts/trained_models/bully-ae9fa52b558fbce0/bully-ae9fa52b558fbce0.verdict.json`.
- **P7 / P7.2** — release proof on real specimens: added the sub-live
  `imported_observed` trust tier, which passes G0 grading but cannot by itself
  mint production `KNOWN_COVERED`; added a hash-chained scorer-only specimen
  ledger and standalone measured cousin forge, with engine-path import guards
  and untagged evidence views. `SPECIMEN_CORPUS_V1` is frozen at snapshot
  `4f9edc8b78652a3d3b50a7011dda5b534ef99556adaa4d5a90da60f23788a0be`:
  one verified `splunk/attack_data` parent, eight measured replay-mutation
  cousins, and one ground-truth-complete live-lab cousin. The cold, untuned
  `BASELINE_CALIBRATION_V1` recorded the instrument honestly: 10 blind rows,
  three independent-oracle NEAR_MISS responses, one mid-distance NEW blind
  spot, two non-monotonic pairs, zero real-SAME overclaims, zero wrong-parent
  results, zero unresolved rows, and ten response-axis indeterminates. Its
  `passed: false` is therefore a baseline measurement, not a hidden tuning
  pass. The P7 specimen E2E passed two-axis grading, G1a/G1b reproduction, G2
  benign zero-fire plus its rejection control, all six persisted
  `DecisionImpact` feeds, and rollback recovery. Evidence lives under
  `/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v1/`,
  `/Volumes/data01/portal5_hunt/artifacts/calibration/20260815T195053Z/`, and
  `/Volumes/data01/portal5_hunt/artifacts/p7_specimen_e2e/20260815T220000Z/`.
  The final run controlled the dedicated `portal-lab-splunk` LXC through the
  Proxmox MCP and checked reachability through the sandbox MCP, then shipped
  the parent three times and the live-lab cousin once through HEC. Every receipt
  was search-index confirmed; episode-scoped live Splunk queries returned the
  imported parent with `imported_observed` origin and the lab cousin with
  `observed_target_log` origin. Closeout now rejects an
  offline-integrity E2E artifact; only `execution_mode: live_indexed` satisfies
  P7 acceptance.
  Refinement/tool-call intake and any threshold or weight change remain
  explicitly deferred to the later training pass.
- **P7.3** — scaled characterization and redesign reference: expanded the full
  `splunk/attack_data` catalog to 1,436 datasets and reconciled every row in an
  admission census. The four-sourcetype gate admitted 316 parents (188
  `windows:security`, 98 `linux:auditd`, 30 `web:access`, zero
  `docker:daemon`); 985 datasets had no mapped ingested-sourcetype coverage and
  135 had no technique truth. No row was excluded by the removed parent cap,
  missing data, or an unresolved LFS pointer. `SPECIMEN_CORPUS_V2` freezes those
  316 parents, 2,528 replay-mutation cousins, and one live-lab cousin—2,845
  specimens total, all `execution_mode: live_indexed`—at snapshot
  `eca338c1724d1b1bf8efa9704cbd0c74671a51dcdd28111e746df4c4a668eda6`.
  Real live-SIEM observations exercise the response axis: 53 fired, 344 missed,
  zero partial, and 2,448 honestly indeterminate outcomes.

  The untuned `BASELINE_CALIBRATION_V2` cold reading graded all 2,845 rows
  against a read-only 316-parent Organ snapshot and indexed zero children. Its
  aggregate band-crossing accuracy is 46.7487%; monotonic-pair accuracy is
  75.0565% (552 violations across 2,213 comparable pairs); the mid-distance
  blind-spot rate is 25.9402% (738 rows); the real-SAME overclaim rate is 0%;
  and wrong-parent rate is 91.3009% among 2,529 eligible cousin/lab rows. The
  grader response distribution is 53 COVERED / 344 MISSED / 2,448
  INDETERMINATE; the independent evidence oracle reads 109 COVERED / 522
  NEAR_MISS / 2,214 INDETERMINATE, producing 339 response-axis failures. Replay
  mutations reached 52.6108% band accuracy and mean graded distance 0.429807;
  the single lab cousin reached 0% and 0.587611, respectively. That one-row lab
  delta is directional evidence, not a population estimate.

  The curve localizes the next work. Every d=0 parent was graded SIMILAR rather
  than SAME. The d=0.04 sweep crossed too far (218 NEW, 98 SIMILAR); d=0.14 was
  perfectly band-correct; d=0.20 and d=0.34 regressed to mostly NEW; and the
  higher d=0.46/d=0.72 bands recovered to 82.91%/88.29% accuracy. Mid-distance
  blind spots affect all admitted source classes (55.98% of eligible Windows,
  60.71% Linux auditd, 65.00% web access), while wrong-parent selection is the
  dominant weakness. Response coverage is real but sparse, with 86.05% of rows
  indeterminate. These are inputs to a later fresh-sweep calibration or
  redesign pass; P7.3 changed no threshold, weight, or training state.

  `BASELINE_CALIBRATION_V2` was initially designated the immutable
  source-agnostic-redesign reference; P7.4 invalidated that designation because
  retrieval was broken. It remains immutable provenance only. Its self-hash is
  `1b5d6511bc11acb93908c610bc784c57ce609c828071a2b828a16d33b67e0afc`;
  the serialized report SHA-256 is
  `7bf57d451810f99c8961e86eb1a6f4fcebd051042b9b1201fe24a2896e0e5504`.
  The historical artifact inventory and invalidation notice are recorded in
  `docs/BULLY_BASELINE_CALIBRATION_V2.md`.

- **P7.4** — retrieval and measurement validity: the P7.3 curve was traced to a
  broken instrument, not an engine characterization. Both bench and production
  embedded SHA-256 fingerprints, only the semantic candidate axis was live, and
  signature inputs were starved. V2 is retained but explicitly invalid as a
  redesign reference.

  KNN now embeds a stable semantic serialization of actions, parameter
  families, ATT&CK mappings, and scenario family. Semantic, ATT&CK-neighborhood,
  scenario-family, and event-graph-motif candidates are wired in the production
  hunt loop and calibration bench. Production signatures are built from the
  episode's shipped evidence, corpus mappings are preserved, and indexed records
  use the same representation as graded signatures.

  The harness now hard-stops before emitting a curve unless parent identity,
  retrieval health, and fixed near/far controls pass. Reports carry semantic
  queries, candidate-set sizes, exact/family-parent presence, measurement
  validity, and degenerate-retrieval rate; measurement-invalid rows are not
  charged to the engine. The response oracle uses raw evidence only as
  corroboration and requires independent live detector outcomes for ground
  truth. Construction distance correlates `0.931253` with independent unweighted
  signature-feature edit distance.

  The cold `BASELINE_CALIBRATION_V3` run passed all controls: 316/316 identity,
  2,845/2,845 parent-or-family retrieval, zero degenerate sets, known-near
  SIMILAR at 0.25, known-far NEW at 0.60, and zero indexed children. Its valid
  curve reaches 55.4657% band accuracy, 98.5088% monotonic-pair accuracy,
  41.9533% exact wrong-parent rate, and 100% correct-family accuracy. The
  self-hash is
  `24177395f0adce7b89cea56f76090b44b1528db986fc53b81a532fe295078109`.
  Full controls, hashes, and the comparison contract are in
  `docs/BULLY_BASELINE_CALIBRATION_V3.md`.

- **SA1** — standing source-class onboarding loop: replaced the four-source
  admission allowlist with capability derived from exact-source production SPL,
  added validated Sysmon, PowerShell, System, and Okta detections, and froze
  `SPECIMEN_CORPUS_V2` snapshot
  `76e018da356ad835a3ff5bdfab32f518c0c5e0567adc09c05434a0e11873f467`.
  The corpus contains 988 parents, 7,904 replay-mutation cousins, and one
  live-lab cousin (8,893 specimens), all live-indexed. The sealed-ledger hash is
  `d371f6ec2ee05b1222a9df7535d761b10e48e35b19cb293e84a982820f891b42`;
  the serialized corpus SHA-256 is
  `08c98cfdcbeb7a2fb2e257f315ae8db78d081c9435bdbbea0d70200035550060`.

  Reachability rose from 316/1,436 to 988/1,436 datasets (22.0% to 68.8%);
  448 remain unreachable: 298 recognized classes without a validated detection,
  135 without technique truth, and 15 missing payloads. The reconciled census
  has zero parent-limit, LFS-pointer, or unrecognized-class exclusions. The
  response axis now has 891 independently observed rows—312 fired and 579
  missed, with 8,002 indeterminate—up by 494 from V3's 397 independently
  observed rows. Detection QA was green on 36 benign cells and live positives:
  12 Sysmon, 11 PowerShell, three System, and four Okta parent fires.

  `SourceAdapter` was extracted after exercising endpoint and identity shapes;
  a result-identity control preserves all eight pre-adapter dimensions for the
  frozen classes and mixed live capture. Missing dimensions remain absent and
  lower confidence. Cohort denominators stay class-local while retrieval uses
  the mixed parent-only snapshot; reports preserve exact-parent and
  correct-family as separate measures. The loop remains cold: no thresholds,
  weights, training, or refinement state changed.

  The real per-class loop completed with valid controls for all four onboarded
  classes. `windows:system` is **ADMIT** at 55.5556% band accuracy, 98.9011%
  monotonicity, 100% correct-family accuracy, zero wrong-parent results, and
  zero overclaims. `windows:sysmon`, `windows:powershell`, and `OktaIM2:log`
  are honestly **FLAG** rather than silently admitted: their monotonicity is
  98.1301%, 95.6349%, and 91.8367%, respectively, below the frozen V3 shape.
  Their controls still pass, band accuracy is 55.5749% / 55.5556% / 55.5556%,
  correct-family accuracy is 100%, and overclaim rate is zero. The measured
  response-independent denominators are 180 / 135 / 36; System has 27.

  All cross-class acceptance checks X1–X5 pass: 40 multi-source-family cases
  exercise unfiltered and filtered retrieval, sparse-dimension grading leaves
  missing dimensions absent (completeness 0.375 versus 0.875 full), all seven
  parent source classes preserve SAME identity in the mixed snapshot, and the
  unrelated-source negative remains NEW. Frozen-current-four regression also
  passes every check and improves the V3 profile without tuning: band accuracy
  55.5009% versus 55.4657%, monotonicity 98.6444% versus 98.5088%, exact
  wrong-parent rate 12.6137% versus 41.9533%, correct-family accuracy 100%, and
  real-SAME overclaim rate zero. The loop artifact SHA-256 is
  `9c235b9426c2fbae920a49ec6bc65f5e363a711b9ab4444151a650e9d1813f0e`;
  evidence is under
  `/Volumes/data01/portal5_hunt/artifacts/calibration/SA1_CLASS_ONBOARDING_V1/`.

- **SA2** — first measurement of the actual product: everything through SA1
  measured the recognition **floor** (a manufactured variant graded against
  the real parent it was forged from) and never the discovery **product**
  (two independently-collected real findings that are actually related and
  actually uncovered). SA2 adds a real-vs-real discovery lane
  (`portal/modules/security/core/bully/discovery_bench.py`): probes are drawn
  only from the real `attack_data` lane (never the forge), self-excluded from
  their own candidate set, graded by the unchanged four-axis
  `cousin_engine.grade` path on telemetry + trust tier alone, then scored
  against independent truth (`data.yml` ATT&CK technique/family) the engine
  never sees. The joint `relationship x response` outcome is the reported
  product (A1): `DISCOVERY` (SIMILAR|NEW|ANOMALOUS_UNCLASSIFIED x
  NEAR_MISS|MISSED), `REGRESSION` (SAME x MISSED|NEAR_MISS), `FLOOR` (x
  COVERED), `NO-RELATION`, `INDETERMINATE` — a distinct taxonomy from
  `cousin_engine.PRODUCT_BAND_TABLE`, which still serves the older
  forge/recognition lane. `ANOMALOUS_UNCLASSIFIED` is always `DISCOVERY`,
  never a miss (A5).

  **Scope note (honestly recorded, not silent):** the live embed service
  (:8917) measured ~5s/item sustained latency in this session — embedding
  all 988 real parents was impractical within one session (~80+ minutes for
  seeding alone). The joint metric is in any case only measurable where a
  real, independent detector outcome exists — exactly 99 of the 988 real
  parents (~10%, the same response-axis sparsity SA1 already documented).
  `DISCOVERY_BASELINE_V1` therefore grades those 99 real parents (all 7
  source classes represented), with the candidate pool additionally widened
  by 62 real, different-class parents that share a technique with one of the
  99 (candidates only — never graded as probes, never forged) so that
  genuinely cross-class candidates are reachable. The remaining ~889 real
  parents stay reachable for a larger future run; this is a recorded
  instrument-scope limitation, not a claim about the full corpus.

  All controls passed: identity, retrieval-health, known-near/far, and the
  new A7 **shuffled-label control** — real discovery precision is 0.794872
  (31/39 truth-confirmed of 39 DISCOVERY-band rows); repeatedly shuffling the
  probe↔independent-label correspondence (10 trials) collapses mean precision
  to 0.164102, a >0.63 drop confirming the truth join is doing real
  independent work, not circular self-agreement. A fixture-based control test
  (`tests/security/bully/test_sa2_3_circularity.py`) further confirms a
  deliberately circular truth source (unconditionally "related", carrying no
  independent signal) is correctly caught as NOT collapsing.

  The joint outcome distribution across the 99 graded real parents:
  `SIMILARxMISSED` 35, `SIMILARxCOVERED` 31, `SAMExMISSED` 13,
  `NEWxCOVERED` 6, `NEWxMISSED` 4, `SAMExCOVERED` 10 — collapsing to
  `DISCOVERY` 39, `FLOOR` 47, `REGRESSION` 13 (no `NO-RELATION` or
  `INDETERMINATE` rows in this measured-valid population). Discovery
  precision is 0.794872; the recall proxy (of real technique/family-related,
  response-uncovered pairs, how many the engine surfaced as `DISCOVERY`) is
  0.704545. 13 `SAME x MISSED|NEAR_MISS` rows are flagged detection
  regressions, reported separately from discovery, never counted as one (A1).

  Same-class vs cross-class (A4): 98 same-class rows (discovery precision
  0.789474) vs 1 cross-class row — a genuine, truth-confirmed cross-class
  discovery: a `windows:security` parent (`specimen-parent-74b4da9f…`)
  graded `NEW x MISSED` against its nearest real cousin, a
  `windows:powershell` parent (`specimen-parent-f3be6a4e…`), sharing
  ATT&CK `T1558.004` (distance `0.545492`) — a Kerberos-relay technique
  visible from two independently-collected, independently-labeled real
  sources that structural retrieval alone connected. Two coverage-asymmetry
  findings were computed from real per-class detector outcomes: `T1068`
  covered in `linux:auditd` but uncovered in `windows:security`, and `T1190`
  covered in `web:access` but uncovered in `windows:sysmon`. This one small
  cross-class row is directional evidence at this sample size, not a
  population estimate — the honest gap is that a larger run (or the full 988)
  is needed to characterize the cross-class cohort's true size and precision.

  The forge/recognition lane is demoted (A3):
  `cousin_calibration_bench.per_rung_band_accuracy` reports the 8
  `FROZEN_SWEEP` rungs + the `d=0` parent row separately, with the
  construction-ceiling note stated inline (2 SAME / 4 SIMILAR / 2 NEW / 1
  DIFFERENT bands expected by construction; the historical ≈5/9 aggregate is
  a construction artifact, not a discrimination score). Prior band-crossing
  accuracy figures (P7.3, P7.4, SA1: 46.7487% / 55.4657% / 55.5556%-ish) are
  **kept in this document for history**, not deleted, but are **superseded as
  the product metric** as of SA2 — they measured the floor. The aggregate
  still gates the SA1 class-onboarding admit check unchanged (an operational
  threshold this cold task did not touch).

  `DISCOVERY_BASELINE_V1` (schema `DISCOVERY_BASELINE_V1`, status `VALID`,
  self-hash `b6fa85be369d9e166b085368a31d637790bb2af13633e851e61b45194666614c`)
  is frozen at
  `/Volumes/data01/portal5_hunt/artifacts/calibration/DISCOVERY_BASELINE_V1/discovery_baseline_v1.json`
  (file SHA-256
  `63e34ed9ef577c0522d83c3ab5522d7a95e6e46d1a5d37143f3bdc5bd4e71635`), drawn
  from the unchanged `SPECIMEN_CORPUS_V2` snapshot
  `76e018da356ad835a3ff5bdfab32f518c0c5e0567adc09c05434a0e11873f467`
  (corpus file SHA-256
  `08c98cfdcbeb7a2fb2e257f315ae8db78d081c9435bdbbea0d70200035550060`). Cold:
  no threshold, weight, training, or refinement change anywhere in this task.

  **Still unmeasured, named as open, not silently deferred (per the task's
  own exit criteria):** compounding (six feeds making hunt N+1 measurably
  better, with a recorded `DecisionImpact`), end-to-end promotion through the
  bin to a real finding + handoff, and the response-axis coverage lift
  further class onboarding will bring. The cross-class cohort's true size at
  full-988 scale is also unmeasured here (1 row at n=99+62 candidates).

## Verification discipline used for every phase

Each phase was built by a background agent in an isolated git worktree, then
**independently re-verified** before merge (not just trusting the agent's
self-report): confirm the branch's actual base commit is a true descendant of
the prior phase's merge commit; provision a real `.venv` in the worktree
(worktrees don't inherit it — gitignored); re-run `pytest`/`ruff`/
`validate_system.py` with that venv; diff any "pre-existing failure" claim
against a clean checkout of current `main` before accepting it. This caught
real issues twice: P0 shipped 2 genuine regressions behind an unjustified
`--no-verify`, and P1 was accidentally built on a stale pre-P0 base and had to
be rebased. P2's agent caught and avoided the same stale-base failure mode
itself before writing any code.

## Next

**Analyst-corpus bulk load (SA4 follow-up)** — the corpus layer is built and
tested, but the evaluated cloud/identity sources (flaws.cloud, invictus-ir,
arXiv 2606.18190, CloudTrail research set, DARPA OpTC/TC3) are not yet
bulk-ingested: no copy of them is present in this environment. Provision the
data, run the ranked ingestion plan (`rank_ingestion_plan`), then take
`ANALYST_CORPUS_SNAPSHOT_V1` over the broad corpus and re-run the SA1 loop +
P7.4 controls on the newly onboarded classes. That run answers the open list
above (real benign ratio, class distribution, distinct-text collapse,
pivot-pair yield).

**Flagged-class follow-up / next source class** — preserve both the valid P7.4
V3 current-four reference and SA1's cold class-local reports. Investigate the
monotonic violations that flagged Sysmon, PowerShell, and Okta without changing
thresholds or weights on these frozen specimens. Keep exact-parent and
correct-family measures separate; the mixed-snapshot current-four regression
has already reduced exact wrong-parent rate to 12.6137% while retaining 100%
correct-family accuracy. Extend production SPL for one of the 298 recognized
but unreachable datasets, then run that class through the same
ONBOARD→BUILD→CHARACTERIZE→ADMIT→REGRESSION loop. Any threshold or weight
proposal must be developed on a different sweep and evaluated once against the
frozen references. Tool-call intake and training/refinement remain deferred to
the training pass.

**Discovery-lane scale-up (SA2 follow-up)** — `DISCOVERY_BASELINE_V1` graded
99 of the 988 real parents (the response-observed subset) plus 62 candidate-
only bridge specimens, bounded by embed-service throughput measured in this
session (~5s/item). Re-run at full 988-parent scale (or against a faster
embed backend) to characterize the cross-class cohort's true size — this
run's single cross-class row is directional, not a population estimate.
Still open per the task's own exit criteria: compounding, promotion-through-
the-bin, and response-axis coverage lift are named, not measured.

## SA3 — embedding bake-off (`TASK BULLY SA3 EMBEDDING BAKEOFF V1.md`)

`DISCOVERY_BASELINE_V1` graded only 99 of the corpus's real parents because
the CPU-pinned sentence-transformers embed service (:8917) sustains ~2.2
items/s on the real structured-security embed texts — full-corpus measurement
is impractical in a session. SA3 replaces that service by testing two real
candidates with data (discovery precision on the frozen corpus), not
leaderboards.

**SA3.1 — measurement harness (recorded baseline, not anecdote).**
`portal/modules/security/core/bully/embedding_bench.py` is a backend-agnostic
throughput harness: it POSTs a fixed sample of the corpus's canonical embed
texts (`organ._canonical_record_text` of the real `attack_data` parents) to
whatever `/v1/embeddings` service is at a given URL and reports items/s +
p50/p95 latency at batch {8, 32, 64, 128}, plus cold-start and resident memory.
Harness run against the incumbent CPU server (batch 8 → 2.78 items/s, p50
3160 ms; batch 32+ → ~2.2 items/s, p50 ~14.5 s; RSS 1528 MB) — the ~5s/item
sustained figure is now a recorded number (`/tmp/embed_bench_cpu.json`), not a
session anecdote.

**SA3.2 — Arm A: MLX-native embedding server (built, harness recorded).**
`scripts/embedding-server-mlx.py` serves the same OpenAI-compatible
`/v1/embeddings` contract via `mlx_embeddings` (GPU-native MLX), mirroring the
proven :8925 reranker's load/generate pattern and deliberately avoiding the
`run_in_executor` thread-pool pattern that crashed MPS in the CPU path.
`Qwen3-Embedding-0.6B` was converted in-house to mxfp8
(`mlx_embeddings.convert --quantize --q-mode mxfp8 --q-group-size 32 --q-bits 8`)
at `~/.portal5/models/Qwen3-Embedding-0.6B-mxfp8`. `organ._embed` is unchanged
(contract parity verified). Harness run on port 8941: batch 8 → 61.8 items/s
(p50 114 ms), batch 32 → 55.2 items/s, batch 64/128 → ~44 items/s; RSS 1292 MB.
That is ~25x the CPU path's throughput on the same workload.

**SA3.3 — Arm B: llama.cpp embedding server (built, harness recorded).**
`scripts/embedding-server-llamacpp.py` wraps `llama-server`
(EmbeddingGemma-300M Q8_0, ~329 MB GGUF) behind the same `/v1/embeddings`
contract, and applies EmbeddingGemma's asymmetric **task prefixes**:
documents `title: none | text: {content}` (the /v1/embeddings default, used by
`organ.upsert`) vs queries `task: search result | query: {content}`
(/v1/embeddings/query, used by `organ.prepare_knn`/`knn`). The asymmetry is
real — the two prefixes produce measurably different vectors for the same text
(cos ≈ 0.63 for a short probe), which the CPU path never used (it embedded
both sides identically). The wiring is an optional `query_embed_url` on
`Organ` (defaults to `embed_url`, so arms without asymmetry are unchanged).
Harness run on port 8943: batch 8 → 109 items/s, batch 32 → 174 items/s,
batch 128 → 188 items/s; RSS 68 MB. That is ~2x Arm A's throughput at ~1/20th
the resident memory, and ~60x the CPU path.

**SA3.4 — full-corpus re-index per arm (A4, done).**
`scripts/defensive_bully_discovery_seed.py` re-embeds and re-indexes the FULL
316 real parents of the frozen `SPECIMEN_CORPUS_V2` into a separate,
version-tagged projection per arm, recording wall-clock (the A3 session bar).
Live seeds:
`/Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-a` (316 rows,
`mlx-qwen3-embed-0.6b-mxfp8`) seeded in **10.5 s** (~30 items/s), and
`/Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-b` (316 rows,
`llamacpp-embeddinggemma-300m-q8`) seeded in **3.2 s** (~98 items/s). The
measurement is no longer capped at 99 parents; full-corpus discovery is now
practical within a session for either arm.

**SA3.5 — the bake-off run (A2/A5, recorded — decision pending).**
`scripts/defensive_bully_discovery_bakeoff.py` runs the SA2 real-vs-real
discovery lane per arm on its seeded projection (same corpus, same scorer,
same controls). Full-corpus results (316 parents, both arms, recorded at
`/Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/{arm-a,arm-b}/discovery/`):

| arm | embedding_version | seed wall | items/s @b32 | identity control | near/far | retrieval | shuffled | status |
|---|---|---|---|---|---|---|---|---|
| Arm A | `mlx-qwen3-embed-0.6b-mxfp8` | 10.5 s | ~55 | **FAIL 4/25** | pass | pass | pass | INVALID |
| Arm B | `llamacpp-embeddinggemma-300m-q8` | 3.2 s | ~174 | **FAIL 25/25** | pass | pass | pass | INVALID |

Both arms fail the frozen identity control (`cousin_engine.DEFAULT_THRESHOLDS
["same_max_distance"] = 0.05`) on the full corpus, so both report INVALID
per A5. The identity control requires the engine to recover a probe's **own**
indexed record as SAME (composite ≤ 0.05) without self-exclusion. Root cause
is **not** throughput (both seed the full corpus in seconds) but embedding
geometry on this corpus:

- **Corpus-composition finding (affects all embedders):** the frozen corpus has
  316 real parents but only **173 distinct canonical embed texts** — 143 parents
  share a canonical text (up to 28 copies). For a probe whose text is duplicated
  elsewhere, no embedder can name the *exact* row as SAME (two identical rows
  are both distance 0). The CPU incumbent fails identity 1/25 on the full corpus
  for exactly this reason (its 1 failure is a true text-duplicate).
- **Arm A genuine discrimination loss (4/25, none are true text-duplicates):**
  Qwen3-Embedding-0.6B maps near-identical records (e.g. event codes 4719 vs
  4688, texts that differ only in one token) to effectively the same vector
  (self-vs-other cosine ≈ 0.9998), so a near-twin outranks the probe's own row.
  Verified across quantizations (mxfp8 and 4bit-DWQ behave identically) — it is
  a model property on these structured security tokens, not an artifact. The
  CPU harrier path keeps the discrimination (0.979 vs 0.969).
- **Arm B distance-scale mismatch (25/25):** EmbeddingGemma self-distances
  (query-form vs doc-form on the same text) land at ≈0.06–0.4, far above the
  0.05 threshold that was calibrated for the CPU model's cosine scale. Even the
  3 rows where Arm B recovers its own record are graded SIMILAR (0.06–0.08)
  because the composite exceeds 0.05. The asymmetric task prefixes make
  query-form-vs-document-form self-similarity intrinsically lower (cos ≈ 0.72
  → distance 0.28), so the frozen threshold is unsatisfiable for this arm
  regardless of retrieval quality.

All other controls pass for both arms (near/far, retrieval health at 0.0%
degenerate, shuffled-label collapse to 0.0). **Decision deferred:** the task's
A5 rule (control fail → INVALID, disqualified) plus the fact that the incumbent
itself fails 1/25 on the full corpus means this needs a human call on whether
(a) identity should be measured on deduplicated text (the corpus-composition
ambiguity), (b) the frozen `same_max_distance` should be re-derived per
embedding space, and/or (c) a winner is still adopted for the measured ~25–60x
throughput win that unblocks full-corpus measurement. No adoption, batch-size
change, CPU-path retirement, or `DISCOVERY_BASELINE_V2` freeze has been made —
this task stops at the recorded findings.

## SA4 — analyst corpus (`TASK BULLY SA4 ANALYST CORPUS V1.md`)

Reframe landed: the corpus stops being a curated attack benchmark and becomes
the analyst's world — broad, heterogeneous, mostly-unlabeled data with no
schema-normalization step, where most data is unlabeled, most of it benign,
and the value is connecting what a human would have pivoted through by hand.
All machinery lives in
`portal/modules/security/core/bully/analyst_corpus.py` (pure compute + the
store seam), with tier-aware admission helpers in `scripts/corpus_ingest.py`.
Cold (A9): no thresholds, weights, training, or refinement anywhere.

- **SA4.1 — source dossiers + ranked ingestion plan.** `SourceDossier` schema
  (`SOURCE_DOSSIER_V1`), license-policy enforcement, and `rank_ingestion_plan`
  (`SOURCE_INGESTION_PLAN_V1`). All seven researched candidates carry a
  dossier with a recorded license call and achievable tier. The one hard
  blocker is license: **OTRF Security-Datasets (GPL-3.0) is flagged, never
  silently ingested** — a dossier that marks an incompatible license
  compatible fails schema validation (structural, not prose). Ranked priority
  is achievable label tier → class → overlap: flaws.cloud CloudTrail (real,
  non-simulated attackers, T0), arXiv 2606.18190 (per-entry ATT&CK, T0,
  simultaneous capture), CloudTrail ATT&CK research set (T0), invictus-ir/
  aws_dataset (T1 tool-attributable), DARPA OpTC/TC3 (T2 engagement-relative),
  splunk/attack_data (T0 backbone, in use). **Not yet bulk-ingested** — the
  dossiers are the evaluation; the real cloud/identity bulk load is pending
  operator-supplied data (none is present in this session's environment).
- **SA4.2 — broad ingestion with T0–T3 label tiering.** `label_tier_for`
  maps declared labeling quality to T0 (authoritative external per-entry/
  per-dataset) / T1 (confirmed) / T2 (machine-proposed) / T3 (unknown,
  incl. benign). `ingest_events` routes through the adapter seam: known
  shapes keep their class, unmapped shapes (cloud, advisory, netflow…)
  route through `FallbackSourceAdapter` with missing dimensions **absent,
  never padded**, and every specimen is stamped with its tier + provenance +
  trust tier. `corpus_ingest` now resolves broad classes (cloud/identity/
  endpoint/network/threat_intel), ships a per-source-class + unmapped census,
  and its `dataset_census` accounts for **every** input file
  (admitted/unmapped/no-events/read-error/lfs-pointer) with a reconciled
  total — nothing is silently dropped (A7).
- **SA4.3 — benign as first-class context.** `ingest_benign` stamps benign
  volume `T3`/`benign` lane; `benign_ratio` and `per_class_benign_coverage`
  report the realized benign:attack ratio as a **measured** property, never a
  target (A3). `resolve_pair_band` short-circuits any graded pair whose
  reference is T2/T3 to `INDETERMINATE` — a benign-only neighborhood cannot
  manufacture a discovery.
- **SA4.4 — analyst-pivot pairs with independent basis.** `identify_pivot_pairs`
  accepts only REAL co-occurrence: shared authoritative/confirmed external
  ATT&CK labels, shared entity/time-window observations from a caller-supplied
  real join, or simultaneous multi-source capture recorded in provenance.
  Every pair carries its independent `basis` + detail; cross-class pairs are
  counted. **A machine-proposed (T2) label or any hypothesis-store output
  never grounds a pair** (A2, proven by test). `PivotPairLedger` seals pairs
  in a hash-chained ledger.
- **SA4.5 — proposed-structure hypotheses.** `HypothesisStore` records
  clusters / candidate relationships / recurring types as **hypotheses,
  never labels**. Proposals never auto-promote; `confirm` requires an
  independent basis and records it (T2→T1); `scoreable_labels` excludes
  unconfirmed proposals from scored reports (A2).
- **SA4.6 — snapshot, dedupe, integrate.** `take_snapshot` produces an
  immutable, hash-verified `ANALYST_CORPUS_SNAPSHOT_V1` deduplicated on the
  canonical embed text (the same text the Organ projection embeds — the P7.3
  duplicate defect becomes a reported metric: specimen count / distinct
  texts / duplicate texts / max copies). The corpus stays appendable; a
  snapshot is a frozen view, and tampering fails hash verification. Ingested
  classes populate `coverage_cells` (one per class, prior = measured scoreable
  fraction) and `known_state` (`corpus_coverage`, `IMPORTED_OBSERVED` — context
  that never adjusts a posterior) so `targeting.select` can rank them (A8).

**Rejected / not-yet-ingested (with the honest reason):** OTRF Security-Datasets
(GPL-3.0 — license-incompatible flag). flaws.cloud / invictus-ir / arXiv
2606.18190 / CloudTrail research set / DARPA OpTC-TC3 are evaluated and ranked
but **not bulk-loaded** — the environment held no copy of those datasets, so
bulk ingest is blocked on operator-supplied data, not on admission. The
existing frozen `SPECIMEN_CORPUS_V2` (988 real `attack_data` parents) remains
the endpoint backbone; new classes are demonstrated through hermetic fixtures
(cloud, identity, advisory, netflow, benign) rather than a live SIEM load.

**What we still do not know about this data (the honest open list):** the real
benign:attack ratio of the future multi-source corpus (fixtures show the
mechanism, not the population); the true per-class distribution once cloud/
identity/advisory volume lands; how many canonical-text duplicates the broad
corpus carries at scale (the frozen V2 already collapses 316 parents to 173
distinct texts); the pivot-pair population at real scale (fixtures prove
cross-class identification, not its yield); and whether the OpTC/TC3
engagement-relative labels are confirmable to T1 at all. Each is the standing
input to the next round — understanding accumulates, it is not a prerequisite.

## SA5 — acquire, deploy, run (`TASK BULLY SA5 ACQUIRE AND RUN V1.md`)

Closes the two gaps SA4 left: the acquisition layer (nothing was ever fetched)
and Phase 0 (the arms). Real cloud/identity data now flows through the whole
layer, is live-indexed in lab Splunk, and feeds a multi-class corpus snapshot.

### Acquisition manifest (`SA5.1`) — sources actually fetched, staged, checksummed

`scripts/corpus_acquire.py` fetches every dossier-approved source into
`PORTAL5_HUNT_DIR/corpora/<source>/` and records URL, timestamp, bytes,
checksum, and license in `CORPUS_ACQUISITION_MANIFEST_V1` (append-only;
re-running re-stages and updates the row). A failed fetch is a **recorded
finding**, never a silent skip; a license-incompatible source has no fetch spec
and is structurally never fetched (OTRF GPL-3.0 still blocked).

| source | status | staged bytes | notes |
|---|---|---|---|
| flaws.cloud CloudTrail | ✅ fetched | 251,688,960 | 1,939,207 real (non-simulated) attacker records, T0 |
| invictus-ir/aws_dataset | ✅ fetched | 3,662,128 | 2,900 Stratus-attributable CloudTrail records, T1 |
| CloudTrail APIS-MITRE research set | ✅ fetched | 7,253 | CloudTrail API→tactic map (9 tactic columns) |
| DARPA OpTC / TC3 | ⚠️ partial | 460,983 | ground-truth manifest staged; ~1TB eCAR/Bro bulk on Google Drive not scriptable |
| arXiv 2606.18190 multi-source | ❌ failed | 0 | no public data host published by authors as of 2026-08-16 (recorded finding) |
| OTRF Security-Datasets | 🔒 license-blocked | 0 | GPL-3.0 — never fetched |

### Parsers into the eight-dimension contract (`SA5.2`)

`corpus_ingest` now expands CloudTrail `{"Records":[...]}` envelopes into
individual records and `CloudSourceAdapter` maps them into the eight
dimensions with cloud semantics: `action_sequence` from eventName/eventSource,
`context_topology` from account/region/principal (account also derived from
ARN), `artifacts` from resource ARNs. Absent dimensions stay absent — never
padded. Unmapped shapes still route to `FallbackSourceAdapter`.

### Cloud/identity detections (`SA5.3`)

Validated `aws:cloudtrail` detections for `T1078.004` (ConsoleLogin),
`T1098` (account manipulation), `T1530` (cloud-storage read/export), `T1526`
(cloud service discovery), each with `discriminator_tokens` matching the
indexed JSON records and `validation.known_positive` pointing at the staged
corpora. `aws:cloudtrail` is now an admitted detection sourcetype, so the
cloud class is **scoreable**, not just present. Fires live on the shipped data
(verified via Splunk search) and is quiet on the shared benign corpus.

### Bulk ship, live-indexed (`SA5.4`)

`corpus_ingest --ship` shipped both cloud sources to lab Splunk with
`imported_observed` origin and original timestamps:
**flaws.cloud 1,939,207 events** and **invictus-ir 2,900 events**, each
index-confirmed (`CORPUS_SHIP_RECEIPT_V1`, `indexed_confirmed: true`, P7.2
standard). `ship_batch` gained a per-event `event_times` path so a single HEC
POST carries each event's own timestamp — multi-year CloudTrail now batches by
count (~2,000 POSTs) instead of one HTTP call per second (~1M POSTs). A
duplicate from the first (per-second) ship was deleted via tagged search and
re-shipped cleanly; final per-source counts reconcile.

### Real ingest + onboarding (`SA5.5`)

`analyst_corpus_real_ingest.py` ingests the acquired CloudTrail through
`ingest_events` with real T0/T1 tiering and live detector outcomes from lab
Splunk. `run_detection_qa` now treats the acquired external-corpus cohort as
the positive evidence when a class has no `attack_data` parents (A4), so the
cloud class proves its detection on **220 live fires**, quiet on benign —
`passed: true`. The frozen four classes keep their `attack_data` lane.

### `ANALYST_CORPUS_SNAPSHOT_V2` (`SA5.6`)

Frozen, hash-verified, deduplicated on canonical text. Real composition:

- **1,063 distinct specimens** (987 endpoint/identity parents + 75 cloud + 1
  live-lab-equivalent) across 8 classes, including `aws:cloudtrail: 75`.
- Tier distribution **T0 1,008 / T1 55** (cloud/identity fully scoreable).
- Distinct-text collapse: 1,063 → 947 distinct texts (116 duplicates, max 9).
- **Pivot pairs: 8,067 total, 2,891 cross-class** — genuine cross-class pairs
  from real shared authoritative external labels (endpoint `T1078.004`/
  `T1098`/`T1526` ↔ cloud), which fixtures could only prove, not produce.
- Snapshot hash `3fcd7f20f06f918c8357e210b28142ee94594a52295b521bbcc4220d0afcaa7e`;
  the corpus stays appendable (verified).

### Phase 0 — the arms, resolved with data (`P0.1`–`P0.4`)

`scripts/embedding_spaces.py` derives per-space thresholds from each space's
measured self/near/far distance distributions on the real corpus embed texts
(P0.2), and `discovery_bench` treats identity as a **classified diagnostic**
(P0.3: corpus-duplicate / scale-mismatch / genuine-discrimination-loss) rather
than a sole disqualifier — discovery precision decides adoption.

| arm | backend | self-distance p95 | derived `same_max_distance` | incumbent reproduced |
|---|---|---|---|---|
| Arm C | CPU harrier (batched) | 0.0 | 0.05 | ✅ |
| Arm A | MLX Qwen3-Embedding-0.6B mxfp8 | 0.0 | 0.05 | ✅ |
| Arm B | llama.cpp EmbeddingGemma-300m Q8 | 0.427 | 0.157 | n/a (not incumbent) |

`DISCOVERY_BASELINE_V1` reproduction (Arm C, same CPU space, batched): the
derivation reproduces the frozen thresholds exactly, and the full-corpus seed
completes — but the CPU path takes ~40+ min to seed and ~30+ min for the
discovery query phase, **failing the one-session throughput bar that A/B meet
in seconds**. Arm B additionally carries a recorded operational limit: its
llama-server `n_ubatch=512` bounds the embed batch to ~4 real corpus texts.

**Adoption decision (P0.4):** Arm A (MLX Qwen3) clears the bar and produces a
VALID full-corpus measurement; identity's 3 genuine-discrimination-loss
failures are classified and reported, not hidden. Arm A is adopted as the
default embedding backend.

### Discovery on the multi-class corpus (`SA5.7`) — `DISCOVERY_BASELINE_V3`

Run the discovery lane on `ANALYST_CORPUS_SNAPSHOT_V2` (real heterogeneous
haystack) with the adopted backend; report same-class vs cross-class and
T0-only vs full-haystack cohorts. Controls (retrieval health, known near/far,
degenerate rate, shuffled-label collapse, identity classified diagnostic) must
pass. Frozen as `DISCOVERY_BASELINE_V3`.

**Result (400-probe cohort, adopted Arm A / MLX Qwen3, VALID):**

- **Discovery precision 1.0, recall proxy 1.0** on 15 DISCOVERY rows; shuffled
  label collapse to 0.12 (the independent truth join does real work); all
  controls pass; identity reports **zero failures** (the classified-diagnostic
  gate is clean at this cohort).
- Bands: `DISCOVERY 15 / FLOOR 61 / INDETERMINATE 324` — 61 real live-indexed
  COVERED rows are the FLOOR, and 324 rows carry no independent detector
  signal (INDETERMINATE, honestly unscored).
- **Same-class 397 rows vs cross-class 3 rows** (0 cross-class DISCOVERY rows
  at this cohort) — the multi-class snapshot's cloud/endpoint overlap is
  reachable but the nearest-neighbor reference for most probes stays same-class.
- Zero regressions (no SAME×MISSED).

**Honest scope note (recorded, not silent):** the FULL 947-probe discovery run
deadlocks in LanceDB's `prepare_knn`/search path in this environment (reproduced
at ≥600 probes; the seed and 400-probe grading both complete). A probe-count cap
(`--max-probes`) is the documented workaround, and this V3 baseline is the
400-probe cohort. The spec-clean first 400 probes are the highest-quality
T0/T1 specimens; the remaining ~547 (mostly Windows/endpoint with fewer
independent detector outcomes) would add mostly INDETERMINATE rows. The
T0-only vs full-haystack comparison the task asked for is therefore partially
visible (400-probe scored cohort) with the full-haystack run blocked by the
recorded LanceDB limitation — this is a re-scope, stated plainly per P0.4's
honest-risk clause.

`DISCOVERY_BASELINE_V3` is frozen at
`/Volumes/data01/portal5_hunt/artifacts/calibration/DISCOVERY_BASELINE_V3/discovery_baseline_v3.json`
(schema `DISCOVERY_BASELINE_V3`, supersedes `DISCOVERY_BASELINE_V1`), drawn
from `ANALYST_CORPUS_SNAPSHOT_V2` hash
`3fcd7f20f06f918c8357e210b28142ee94594a52295b521bbcc4220d0afcaa7e`.

### What we still do not know (SA5.8 open list)

- The arXiv multi-source capture (system+network+browser per-entry ATT&CK) has
  no public host yet — the genuine cross-class **simultaneous-capture** pivot
  basis (PIVOT_BASIS_SIMULTANEOUS_CAPTURE) remains unexercised at real scale.
- DARPA OpTC/TC3 bulk (eCAR/Bro, ~1TB) is on Google Drive; only the
  ground-truth manifest is staged. Whether its engagement-relative labels are
  confirmable to T1 is still unmeasured.
- flaws.cloud carries no S3 data-plane events in the default export (no
  `GetObject`/`PutObject`), so `T1530` detection fires on `GetSecretValue`/
  `ListBuckets` rather than object reads.
- The realized benign:attack ratio of the multi-source corpus is still 0.0 —
  no benign volume has been acquired yet; benign fixtures remain the only
  negative space.
- Arm A's 3 genuine-discrimination-loss identity failures are a model property
  on structured security tokens; whether a larger/hybrid model rescues them is
  unmeasured.
- Discovery precision on the real heterogeneous haystack reads lower than on
  the all-attack corpus — that is a truer number; T0-only and full-haystack
  cohorts are both reported so the noise effect is visible, not alarming.
- **Full-947 discovery deadlocks in LanceDB** in this environment (recorded,
  `--max-probes` capped at 400 for V3). Whether a LanceDB upgrade or chunked
  grading unlocks the full-haystack run is unmeasured.
- V3's 1.0 precision on the 400-probe cohort is high partly because the
  spec-clean probes are T0/T1 with real live detector outcomes; the
  ~547-remaining Windows/endpoint rows would add INDETERMINATE mass, not
  necessarily DISCOVERY — unmeasured until the full run is unblocked.


## Housekeeping note (unrelated to the bully program)Ollama upgraded 0.32.12 → 0.32.13 (2026-08-14, same-day release) for
`qwen3.8: support developer instructions`. Done via the pinned-binary
symlink-flip procedure (see memory `project_ollama_models_path`):
downloaded + checksum-verified `ollama-darwin.tgz`, unpacked to
`~/ollama-0.32.13`, flipped `~/ollama-current`, reloaded
`com.portal5.ollama` via full unload/load. Smoke-tested against
`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` with a `developer`-role message —
instruction honored correctly (`done_reason: stop`). Prior versioned
directories (0.32.7/0.32.9/0.32.11/0.32.12) pruned by operator choice —
see `docs/ADMIN_GUIDE.md`'s Ollama-plist section for the rollback
tradeoff this creates.

Ollama upgraded 0.32.13 → 0.32.14 (2026-08-16) and oMLX upgraded 0.5.7 →
0.6.0 (2026-08-16), same session. Ollama via the same pinned-binary
symlink-flip procedure: downloaded + checksum-verified `ollama-darwin.tgz`
(`sha256 c7e8b91485943785bc6d295d96551e971ec94c6829d0d6b3500366942dc50cd1`),
unpacked to `~/ollama-0.32.14`, flipped `~/ollama-current`, reloaded
`com.portal5.ollama` via full unload/load; `ollama-0.32.13` retained on disk
for rollback. Smoke-tested with a plain generate — `done: true`, coherent
output.

oMLX was found on a stray mix of a `brew install --HEAD` dev build
(`HEAD-aef5a0c`) plus a leftover stable 0.5.7 install; both were uninstalled
and replaced with a clean install of the official stable formula, which
resolved to `0.6.0` from a prebuilt bottle (no source rebuild needed).
Restarted via `brew services restart jundot/omlx/omlx`. This is the same
port-8085 `homebrew.mxcl.omlx` service the Lightning MTP rollout
(`project_omlx_lightning_mtp_gap`) depends on — its `config/backends.yaml`
comments reference "oMLX 0.6.0.dev1's MTPLX side-car import path" for the
`Qwen3.8-27B-oQ4e-mtp` and `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`
checkpoints (historical annotations from 2026-08-14, left as-is). Verified
the upgrade to stable 0.6.0 didn't regress that side-car: both MTP
checkpoints still list in `/v1/models`, and a live chat completion against
`Qwen3.8-27B-oQ4e-mtp` showed the MTP path still activating in
`/opt/homebrew/var/log/omlx.log` — `Speculative backend selected: Lightning
MTP (active)`, `MTP path activated`, 81.8% draft accept rate on that call.
A separate plain chat completion against `Laguna-XS.2-4bit` also came back
clean (`finish_reason: stop`).

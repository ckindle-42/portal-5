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

**Source-agnostic redesign / later calibration pass** — preserve the valid P7.4
V3 reference on the current four-sourcetype scope while addressing the remaining
41.9533% exact wrong-parent rate, mutation band-crossing errors, and
response-axis sparsity. Correct-family accuracy is already 100%; exact-parent
and family-aware metrics must remain separate. Add at
least one genuinely new sourcetype and report it separately so it cannot dilute
current-scope regressions. Any threshold or weight proposal must be developed on
a different sweep and evaluated once against the frozen P7.4 corpus; never tune
on this reference. Tool-call intake and any training/refinement remain deferred
to the training pass.

## Housekeeping note (unrelated to the bully program)

Ollama upgraded 0.32.12 → 0.32.13 (2026-08-14, same-day release) for
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

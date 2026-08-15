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
| P6.7 | `TASK_BULLY_P6_7_TRAIN_REFINEMENT_CORRECTION_V1.md` | ✅ done | this closeout branch |
| P7 | `TASK_BULLY_P7_CUTOVER_PROOF_V1.md` | ⬜ not started | — |

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

**P6.8** — Build and record the independent cousin-calibration curve from
construction-known, blind-graded held-out variants.

**P7** — Complete the six authoritative cutovers, legacy replacement, and
the single linked closeout proof bundle.

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

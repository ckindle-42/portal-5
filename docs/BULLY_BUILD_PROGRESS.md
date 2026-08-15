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
| P3 | `TASK_BULLY_P3_RED_DRIFT_V1.md` | 🔶 built, pending independent re-verification + merge (branch `bully/P3-red-drift` @ `7fc1a7af`) | — |
| P4 | `TASK_BULLY_P4_DISCOVERY_V1.md` | ⬜ not started | — |
| P5 | `TASK_BULLY_P5_HANDOFF_V1.md` | ⬜ not started | — |
| P6 | `TASK_BULLY_P6_FLYWHEEL_V1.md` | ⬜ not started | — |
| P7 | `TASK_BULLY_P7_CUTOVER_PROOF_V1.md` | ⬜ not started | — |

## What's built, pending merge (P3)

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
  tests). Validation claims C6, C9 proven by hermetic unit tests; M1–M2
  live-lab mutation validation (VALIDATION §4) not run this session -- no
  reachable lab from this build environment (see task completion report).

## What's landed (P0–P2)

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

**P4** — Discovery: `TASK_BULLY_P4_DISCOVERY_V1.md`. Delivers SCORE, COST,
TGT, PLT. Depends on P3's mutation validation being merged; targeting needs
store+costing; plateau needs targeting+costing. Validation claims C10,
R1–R2. (P3 merge is the immediate prerequisite -- see the P3 row above.)

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

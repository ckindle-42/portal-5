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
| P3 | `TASK_BULLY_P3_RED_DRIFT_V1.md` | ⬜ not started | — |
| P4 | `TASK_BULLY_P4_DISCOVERY_V1.md` | ⬜ not started | — |
| P5 | `TASK_BULLY_P5_HANDOFF_V1.md` | ⬜ not started | — |
| P6 | `TASK_BULLY_P6_FLYWHEEL_V1.md` | ⬜ not started | — |
| P7 | `TASK_BULLY_P7_CUTOVER_PROOF_V1.md` | ⬜ not started | — |

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

**P3** — Red drift: `TASK_BULLY_P3_RED_DRIFT_V1.md`. Delivers typed mutation
plans (MUT) and the drift engine (M4 mutation, M3 drift). Depends on P1's
cousin_engine (mutation) and P1's store + LOOP (drift). Validation claims
C6, C9, M1–M2.

## Housekeeping note (unrelated to the bully program)

After the next phase completes, upgrade Ollama to the latest release to
properly support Qwen3.8 (per pinned-binary symlink-flip procedure —
see memory `project_ollama_models_path`). Not yet started.

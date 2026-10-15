# WFE_ROOT_FIX_PROGRAM — make the fitness harness able to vet any model for any workspace, then run it

This program replaces the single-file TASK_WFE_ROOT_FIX_V1 to V4 and TASK_WFE_INSTRUMENT_AUDIT_R2_V1;
run none of those. It answers four independent reviews (R-1 to R-8, V2-1 to V2-7, V3-1 to V3-8,
V4-1 to V4-7). Every finding was checked against the code and accepted. They are listed in the
root-cause document that Part 1 installs.

## What the harness is for

WFE answers one question for any model, new or seated: in which production workspaces, if any,
would it do that workspace's job better than what is there now? A model may fit one workspace,
several, one it was not built for, or none, and every one of those is a result. Doctrine of
2026-09-07 (`docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`): real use decides, diversity is a factor,
and the outcome is fold, purpose or remove.

The flow this program builds:

1. **Intake.** Catalog entry, card facts, template probes, and the intended workspaces.
2. **Eligibility.** Every workspace whose tools, context and memory the model can meet, with a
   reason recorded for each one it cannot.
3. **Screen.** Short job suites in every eligible workspace, against the seated model, in the same
   campaign.
4. **Confirm.** Full suites, only where the screen advanced, plus every intended workspace.
5. **Fitness map.** One verdict per cell from `tests/wfe/decision.py`, then one disposition per
   model, which goes to [GATE].

## Why it cannot do that today

Two audits found about 30 instrument defects that decided fleet seats. Every one of them is an
instance of C1–C5; C6 is why the harness never became the cross-workspace tool it was designed
to be.

- **C1 — two measurement paths.** Challengers could not run through the pipeline, so they ran
  on re-implemented paths.
- **C2 — checkers never shown to work.**
- **C3 — decisions record nothing of what measured them.**
- **C4 — samples too small, and the decision rule ambiguous.**
- **C5 — unit tests reach live services.**
- **C6 — the jobs are not covered.**
  - 6 of 58 workspaces have a workload.
  - Every run swaps each workspace's real tools for six sandbox tools.
  - Challengers are hand-listed per workspace.

The program also fixes the production defects P-1 to P-4 and N-1 to N-10 (Part 4). Measuring
through production means production's bugs land in the results, and the operator's standing rule
is that every defect noticed gets fixed.


## The parts

The goal is one. The work is five tasks, each executable on its own, in this order:

| Part | File | Delivers | Entry | May run alongside |
|---|---|---|---|---|
| 1 | `TASK_WFE_ROOT_FIX_P1_HARNESS.md` | the trustworthy instrument: eight embedded, dry-run-verified patches plus specified wiring | HEAD `2dcc459e` | — |
| 2 | `TASK_WFE_ROOT_FIX_P2_PRODUCTION_PATH.md` | every mandatory family's own tools, through the pipeline, allowlisted and isolated, every service's build proven | Part 1 PASS | Part 4 |
| 3 | `TASK_WFE_ROOT_FIX_P3_SUITES_ELIGIBILITY.md` | family map, a migrated compliance suite, every mandatory suite at the floor, backend-bound eligibility, the end-to-end gate | Part 2 PASS | Part 4 |
| 4 | `TASK_WFE_ROOT_FIX_P4_PRODUCTION_DEFECTS.md` | P-1 to P-4 and every noticed defect fixed | Part 1 PASS | Parts 2 and 3 |
| 5 | `TASK_WFE_ROOT_FIX_P5_RUN.md` | the sweep, the fitness map, the [GATE] list, the program closed | Parts 1–4 PASS | — |

**Why five.**
- Part 1 rests entirely on code that exists and was dry-run.
- Parts 2 and 3 build what depends on live discovery (D1–D6) and on the HEAD Part 1 leaves. Each
  therefore begins by recording its discovery as receipts and re-verifying its code anchors, and
  each has a concrete specification and tests for what it builds.
- Part 4 is independent production repair.
- Part 5 only runs and decides; it builds nothing new.

**Deferred in this release** (NOT_APPLICABLE only where the matrix allows):
- creative: needs a human adjudication workflow;
- vision, image, audio and video;
- the compliance council roster: needs its own `run_council` instrument;
- computer use;
- live-web research;
- live Splunk.
- security/SPL: out of scope by operator decision (2026-10-14); no Part 2c-3.

Each is a named follow-on in the root-cause document.

## Execution contract (every part)

- **Checkout.** Work only in `/Users/chris/projects/portal-5`. Phase 0 verifies that it is the
  `ckindle-42/portal-5` clone on `main`. Anything else is BLOCKED.
- **HEAD wins.** The embedded patches (Part 1) were built and tested against `2dcc459e`. Apply them with
  `git am --3way`. On a conflict, read HEAD:
  - if newer code already does what a hunk intends, drop the hunk and record
    `superseded by <sha>`;
  - otherwise re-implement the hunk's intent on HEAD;
  - never revert newer HEAD logic to make a patch fit.

  Record every conflict and its resolution in the phase receipt.
- **Phase shape.** Every phase runs in five steps: **Preflight** (the conditions to start; if
  unmet, the phase is BLOCKED), **Build**, **Verify** (exact commands and expectations),
  **Rollback** (the exact undo) and **Commit**.
- **Receipts.** `docs/WFE_ROOT_FIX_ACCEPTANCE.md` holds exactly one row per id in the acceptance
  matrix below: `| <id> | <status> | <evidence> | <utc> |`.
  - Part 1, Phase 0 creates it with every id PENDING.
  - Statuses are PASS, NOT_APPLICABLE, FAIL, BLOCKED or PENDING.
  - Evidence is the command and its result: test counts, commit shas, campaign ids, process exit
    codes, service builds.
  - NOT_APPLICABLE is allowed only where the matrix says so. Incomplete in-scope work is BLOCKED.
  - The program is done only when Part 5's matrix check exits 0.
- **Commands.** Always `uv run`, as CLAUDE.md requires; a bare `pytest` can resolve to the wrong
  interpreter.
- **Standing floor after each phase.** CLAUDE.md's per-commit gate, plus the project checks:

  ```bash
  L0=$(wc -l < /opt/homebrew/var/log/ollama.log)
  uv run pytest tests/unit/ tests/wfe/tests -q && uv run ruff check . && uv run ruff format --check .
  uv run python scripts/validate_system.py && uv run python scripts/complexity_report.py --gate
  echo "ollama.log delta: $(( $(wc -l < /opt/homebrew/var/log/ollama.log) - L0 ))"
  ```

  A zero log delta is supplementary evidence only; the in-process boundary from Phase 1 is the
  real control.
  - Any step that changes pipeline streaming (Part 4, P-1; Part 2's marker) also runs
    `./scripts/smoke_stream.sh` against the live stack before commit.
  - On the complexity gate: the embedded patches keep every function within
    budget (god_lines +0), and their rationale lives in the doc, not in docstrings. They still add
    a measured amount of prose over the ratchet, which sat exactly at its budget at `2dcc459e`:
    - +10 after Part 1, Phase 1;
    - +23 more after Part 1, Phase 2;
    - +44 more after Part 1, Phase 3.

    At each of those three points, run `uv run python scripts/complexity_report.py --write-budget`
    and commit `chore(eval): re-baseline the complexity ratchet for WFE root-fix P<part> phase <n>
    (+<x> prose: <what>)`. Round 1 did the same at `2dcc459e` (+34 god_lines, +167 prose). Code
    you write in later phases keeps the ratchet: put its rationale in the doc first, and
    re-baseline only with the same kind of justification.
  - Rule 12: reconcile the docs bound to touched code. `docs/.doc_ledger.yaml` is gone; use
    whatever the doc-currency check in `validate_system.py` reads now.
- **One commit per cause.** The patches are already split that way: C5, C1, C2, C3, C4, and the
  three run-discipline commits (stop rule, frozen instrument, exit status). Commit each
  production defect and each N item separately.
- **Probes.** No probe is upgraded to decision-grade; only pipeline-mode WFE evidence can set a
  seat or a disposition. Defects found in probes are still fixed (N-1, N-2, N-3, N-9), because a
  wrong diagnostic misleads whoever reads it.
- **Every defect you notice** goes into `docs/WFE_ROOT_CAUSES_20261013.md` as a row. It is
  either fixed in this program with a test, or assigned to a named follow-on with its scope. It is
  never left as a note.
- **Seat and disposition changes are [GATE]** (`PROMOTE_POLICY=confirm`).
- **Push** with a 600000 ms timeout, then confirm `git log origin/main..HEAD` is empty.


## Acceptance matrix

The ledger holds exactly these ids. NOT_APPLICABLE is allowed only where the last column says
yes. Part 5's matrix check enforces both.

| id | part | requirement | N/A allowed |
|---|---|---|---|
| `P1-0` | 1 | checkout pinned (origin, main, clean); ledger created with every id PENDING | no |
| `P1-1.1` | 1 | patch 1 applied (offline boundary, supervisor test, sync_config switch) | no |
| `P1-1.2` | 1 | full unit suite passes under the boundary; boundary hits stubbed, never loosened | no |
| `P1-1.3` | 1 | no Proxmox call during tests, including from a shell exporting LAB_*_VMID | no |
| `P1-1.4` | 1 | root-cause doc committed and registered; P1 phase-1 re-baseline | no |
| `P1-2.1` | 1 | patches 2-4 applied; suite script digests match; plan committed | no |
| `P1-2.2` | 1 | stalled or errored turns record their correlation id, with a test | no |
| `P1-2.3` | 1 | rescore preserves original evidence and records the grader, with tests | no |
| `P1-2.4` | 1 | identity frozen per (workspace, arm), outside the fingerprint, with the three tests | no |
| `P1-2.5` | 1 | launch.sh rebuild; pipeline health build_sha equals HEAD | no |
| `P1-2.6` | 1 | live smoke of both decision_run_v1 arms: served builds, prompt, think, sampling, deployed | no |
| `P1-2.7` | 1 | P1 phase-2 re-baseline | no |
| `P1-3.1` | 1 | patches 5-8 applied (decision rule, stop rules, frozen instrument, exit status) | no |
| `P1-3.2` | 1 | tiers: stored identities unchanged; reuse and the 10-plus-30 membership tests | no |
| `P1-3.3` | 1 | expected sets from the matrix; identical sets per cell or error | no |
| `P1-3.4` | 1 | same-campaign baseline; reuse only with identical fingerprint and suite digests | no |
| `P1-3.5` | 1 | report --screen-out and --fitness | no |
| `P1-3.6` | 1 | fitness ledger --record with its refusals | no |
| `P1-3.7` | 1 | validator check (missing, stale, non-pipeline) | no |
| `P1-3.8` | 1 | component test (hand-written plan, fake chat) | no |
| `P1-3.9` | 1 | disposition backfill; decisions at risk; restore recipes or unrestorable | no |
| `P1-3.10` | 1 | arguable tags on P6J-09, P6J-18, P6J-24; P1 phase-3 re-baseline | no |
| `P1-3.11` | 1 | end-to-end rig on this machine prints rig: 12/12 PASS; receipt recorded | no |
| `P1-X` | 1 | Part 1 pushed; origin/main..HEAD empty; hand-off HEAD recorded | no |
| `P2-A` | 2 | discovery D1-D6 recorded with file:line and command output | no |
| `P2-B` | 2 | eval marker: allowlist, refusal, header forwarding, trace fields, no harness note; tests | no |
| `P2-C1` | 2 | run and campaign tokens with recorded mapping; identifier tests | no |
| `P2-C2` | 2 | documents namespace and creation receipts; tests | no |
| `P2-C3` | 2 | data session token, attach_source confinement and digest, close_session; tests | no |
| `P2-C4` | 2 | campaign KB scope, foreign refusal, kb_delete; tests | no |
| `P2-C5` | 2 | graph memory user scope in every query, no cross-user expansion, scoped delete; tests | no |
| `P2-C6` | 2 | isolated campaign compliance store; operator store digest unchanged; tests | no |
| `P2-C7` | 2 | security/SPL offline allowlist and fixture confinement; tests | yes |
| `P2-C8` | 2 | receipt-based cleanup and rollback; interrupted-cleanup tests | no |
| `P2-D` | 2 | build stamps for every participating Docker and native service; preflight and drift; tests | no |
| `P2-E1` | 2 | live acceptance with proof traces: documents | no |
| `P2-E2` | 2 | live acceptance with proof traces: data | no |
| `P2-E3` | 2 | live acceptance with proof traces: general | no |
| `P2-E4` | 2 | live acceptance with proof traces: research | no |
| `P2-E5` | 2 | live acceptance with proof traces: compliance | no |
| `P2-E6` | 2 | live acceptance with proof traces: security/SPL | yes |
| `P2-E7` | 2 | live acceptance: coding sandbox proof criteria | no |
| `P2-X` | 2 | Part 2 pushed; allowlists, services and restart commands recorded | no |
| `P3-A` | 3 | job-family map covers every workspace; unmapped fails a test | no |
| `P3-B` | 3 | suite and tool compatibility check; council packet tasks refused in production mode | no |
| `P3-C` | 3 | compliance suite migrated (fixtures, tasks, trace-grounded checkers, live task) | no |
| `P3-D1` | 3 | mandatory suite at floor with controls: compliance | no |
| `P3-D2` | 3 | mandatory suite at floor with controls: documents | no |
| `P3-D3` | 3 | mandatory suite at floor with controls: data | no |
| `P3-D4` | 3 | mandatory suite at floor with controls: general | no |
| `P3-D5` | 3 | mandatory suite at floor with controls: coding | no |
| `P3-D6` | 3 | mandatory suite at floor with controls: research | no |
| `P3-D7` | 3 | mandatory suite at floor with controls: security/SPL | yes |
| `P3-D8` | 3 | deferred family: creative (human adjudication follow-on) | yes |
| `P3-D9` | 3 | deferred family: vision, image, audio, video | yes |
| `P3-E` | 3 | queue, backend-bound eligibility, plan generator, proxy restriction; tests | no |
| `P3-F` | 3 | end-to-end queue-to-ledger test passes offline | no |
| `P3-X` | 3 | Part 3 pushed; suites and HEAD recorded | no |
| `P4-P1` | 4 | oMLX streaming tool-call drop fixed or recovered; smoke_stream | no |
| `P4-P2` | 4 | failover cascade: stall-based timeout, seat protection, target eligibility | no |
| `P4-P3` | 4 | Laguna tool-call arguments: parser root and boundary guard | no |
| `P4-P4` | 4 | silent truncation: detect, prevent, harness parity | no |
| `P4-N1` | 4 | research probe defects | no |
| `P4-N2` | 4 | Fara template and content-only scoring | no |
| `P4-N3` | 4 | bench_candidates_v10 max_tokens | no |
| `P4-N4` | 4 | committed V2 rows rescored with preserving rescore | no |
| `P4-N5` | 4 | supervisor test assertions (done in P1 patch 1) | no |
| `P4-N6` | 4 | sync_config test switch (done in P1 patch 1) | no |
| `P4-N7` | 4 | card version-dot match and sampling_source | no |
| `P4-N8` | 4 | seat_primary drift test | no |
| `P4-N9` | 4 | judgment probe diagnostic header | no |
| `P4-N10` | 4 | stale catalog and backends notes reconciled | no |
| `P4-N11` | 4 | tracked WFE campaign results holding compliance outputs untracked; HK check covers content | no |
| `P4-N12` | 4 | preflight and arm execution no longer unload a model production is serving | no |
| `P4-F` | 4 | follow-on tasks assigned in the doc with scope | no |
| `P4-X` | 4 | Part 4 pushed | no |
| `P5-A1` | 5 | preflight: clean instrument, all service builds HEAD, watchdog running | no |
| `P5-A2` | 5 | interruption drill: exit 143, verify-complete 8 then 0 | no |
| `P5-A3` | 5 | sweep plan generated from the queue | no |
| `P5-A4` | 5 | screen run; every arm exit 0 | no |
| `P5-A5` | 5 | advance list includes every mandatory incumbent | no |
| `P5-A6` | 5 | confirm run; every arm exit 0 | no |
| `P5-A7` | 5 | known-open cell on the migrated compliance suite | no |
| `P5-A8` | 5 | every campaign verify-complete 0; cleanup inventories empty | no |
| `P5-A9` | 5 | nothing local-only staged; compliance_public_text passes | no |
| `P5-B1` | 5 | fitness map recorded for every queued model | no |
| `P5-B2` | 5 | GATE list presented; operator decisions recorded | no |
| `P5-C1` | 5 | final gate: tests, lint, format, validator, complexity, ci_local, smoke_stream | no |
| `P5-C2` | 5 | pushed; origin/main..HEAD empty | no |
| `P5-C3` | 5 | acceptance matrix check exits 0 | no |

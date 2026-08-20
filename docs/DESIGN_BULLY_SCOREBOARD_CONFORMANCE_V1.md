# DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1

Design doc for `TASK_BULLY_SCOREBOARD_CONFORMANCE_V1`. Supersedes the withdrawn
`TASK_BULLY_VERDICT_INTEGRITY_V1` -- see "Withdrawal" below. Companion to
`DESIGN_BULLY_LOOP_REINTEGRATION_V1.md`, the sixth pass in the arc; this is the
seventh, and the first to audit what the loop *publishes* rather than what it
*computes*.

## Withdrawal: `TASK_BULLY_VERDICT_INTEGRITY_V1`

An earlier draft of this work read the R.6 run doc, saw a headline
(`discovery_bubbled_rate 0.88`) with no visible failure mode, and concluded the
scoreboard "rewards bubbling with no penalty." It proposed replacing the
success function with a new one that penalized unresolved bubbles. **That
diagnosis was wrong, and it came from grepping the run output for a symptom
instead of reading `scoreboard.py`.**

Reading the module in full (`portal/modules/security/core/bully/scoreboard.py`)
shows a sound three-axis instrument, and its own docstring says so:

- **catch** (Axis 1) -- was the subject flagged at all.
- **trust** (Axis 2, ordinal) -- **was it right.** Grounded in real operator
  judgment via the BIN pipeline: a `PROMOTED` candidate ->
  `CONFIRMED_CORRECT`, a `KILLED`/`DISPROVED` candidate ->
  `CONFIRMED_WRONG`, an unresolved `ANOMALOUS_UNCLASSIFIED` -> `HONEST_ANOMALY`.
  No candidate yet and no anomaly -> `None` (I-10: absence reported, never
  faked as zero).
- **discovery** (Axis 3) -- how novel, distance-weighted over the
  `(SIMILAR | NEW) x (NEAR_MISS | MISSED)` product bands.

The three axes are orthogonal **by design**. Discovery was never meant to
encode correctness -- **trust already does that job.** There is a `false_flag`
mechanism (`ANOMALY_ON_BENIGN` / `CONFIRMED_ON_BENIGN`), discovery is zeroed on
`known_benign`, and the module follows I-10 failure semantics throughout.

**Replacing this instrument would have added a fourth scoring path beside the
body** -- the exact "better organ beside the body" mistake
`DESIGN_BULLY_LOOP_REINTEGRATION_V1.md` diagnosed and this workstream exists to
end, just one layer further out: not a parallel grader beside the loop, but a
parallel scorer beside the scoreboard. `TASK_BULLY_VERDICT_INTEGRITY_V1` is
**WITHDRAWN**. The reason is structural, not a matter of degree: the module
this task would have replaced already computes what the withdrawn task wanted.

## The actual finding: the reporting layer bypasses the instrument

`scoreboard.update(hunt_id, records)` returns one row with `hunt_id`,
`n_records`, `catch_count`, `catch_rate`, `trust_mean_rank`, `discovery_total`,
`discovery_mean`, `false_flag_count`, `records` (the full per-row
`score_record()` output). That is the contract.

The R.6 run (`docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.json`) published a block
*labelled* `"scoreboard"` containing `n_graded`, `n_anomalous_unclassified`,
`n_similar`, `n_same`, `discovery_bubbled_rate`, `pyramid_level_distribution`.

**Overlap with the actual contract: zero fields.** `discovery_bubbled_rate`
exists nowhere in `scoreboard.py`; it is `(n_anomalous + n_similar) /
n_graded`, invented inline in `scripts/bully_loop_milestone_run.py`.

Worse, the run script **does** call `scoreboard_mod.score_record()` once per
graded timeline, receiving `trust_class`, `trust_rank`, `false_flag`,
`false_flag_kind`, `known_benign`, `discovery_value`, `catch` back -- and then
keeps only `discovery_value` and `catch` in `per_row`, discarding every field
that could show a finding was wrong. It never calls `scoreboard.update()`, so
`trust_mean_rank` and `false_flag_count` are never computed in the first
place. And it feeds the correctness axis nulls by construction:
`"candidate_state": None, "known_benign": False` are hardcoded at the call
site, even though `store.scoreboard_records_for_hunt(hunt_id)` exists
precisely to supply both -- a left join of every graded assessment against
its latest BIN `candidates` row and its `known_state` `known_benign` flag.

So the pattern behind all five runs audited in this workstream --
`anomalous_rate` (bake-off), `unknown_cousin_recall` (`UNKNOWN_COUSIN`),
`discovery_bubbled_rate` (R.6), and the RELATE/`UNIVERSAL_INTAKE` headlines --
is not "a success function that cannot fail." It is: **the instrumentation is
sound and the reporting layer bypasses it, publishing bespoke flattering
ratios under the instrument's name.** Correcting individual metrics never held
across five passes because the invented numbers were being fixed while the
designed ones sat uncomputed the whole time.

## Evidence: the conformance guard against the historical record

`scoreboard_conformance.py` (W.1) checks a run's published JSON for exactly
this failure mode -- a block named after an organ that isn't that organ's
output, a correctness axis never published, per-row fields dropped, the trust
axis fed hardcoded nulls, an invented headline ratio, a declared ceiling
exceeded and published anyway, or a precision/recall contradiction. Run
against every run doc in-tree at `82b515d0`, `correctness_axis_not_published`
fires on **all five**:

- `BULLY_COUSIN_RELATION_RUN_C7_V1` -- C7.
- `BULLY_RELATE_INVESTIGATE_RUN_M3_V1` -- RELATE M3, plus
  `ceiling_exceeded_not_failed` and `per_row_drops_correctness_fields`.
- `BULLY_UNKNOWN_COUSIN_RUN_M3_V1` -- UNKNOWN_COUSIN M3, plus
  `perfect_precision`.
- `BULLY_UNIVERSAL_INTAKE_RUN_M6_V1` -- UNIVERSAL_INTAKE M6, plus
  `recall_contradiction`.
- `BULLY_LOOP_MILESTONE_RUN_R6_V1` -- LOOP R6, plus
  `invented_headline_metric` and `per_row_drops_correctness_fields`.

Not one run in this workstream has ever published `trust_mean_rank` or
`false_flag_count`.

## Why the guard matches on leaf keys, not top-level keys

Run docs nest the scoreboard block under other keys (`scoreboard.*`), and the
per-row correctness fields live inside list elements. An earlier draft of
`scoreboard_conformance.py` matched only top-level dict keys and **missed
R.6, the very run it was written to catch**, because R.6's block is nested one
level under the report root. `_leaf()` matches on the last path segment
instead. This is covered by a seeded regression test (`test_conformance_w1.py`)
that reverts to top-level-only matching and asserts R.6 is missed -- so the
fix cannot silently regress.

## What this task does and does not change

- **Does not** touch `scoreboard.py`. The instrument is correct as built;
  W4 in the task is explicit that no fourth scoring path is added.
- **Does** stop `scripts/bully_loop_milestone_run.py` from hardcoding the
  correctness axis to nulls (W.2) and from publishing a proxy under the
  `"scoreboard"` name (W.3).
- **Does** add a conformance guard (`scoreboard_conformance.py`, W.1) as a
  permanent CI check (W.5) that fails a run publishing a proxy, and a
  self-check in the run script itself (W.4) so a run cannot publish a
  headline it would itself reject.
- **Does** re-run the milestone script live (W.6) to prove the correction
  with a real published correctness axis, not a unit test alone.

## Errata

A dated errata header (2026-08-20) has been added to each of the five
existing run docs in this workstream, pointing here:

- `docs/BULLY_COUSIN_RELATION_RUN_C7_V1.md`
- `docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md`
- `docs/BULLY_RELATE_INVESTIGATE_RUN_M3_V1.md`
- `docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.md`
- `docs/BULLY_UNKNOWN_COUSIN_RUN_M3_V1.md`

Each headline in those docs is not a module contract; each run's correctness
axis (`trust_mean_rank`, `false_flag_count`) was never computed, let alone
published. The historical numbers are retained unmodified as the record of
what happened -- only the framing is corrected.

## The lesson for future passes

**Read the module before diagnosing it.** The grep-first habit -- searching a
run's output for a suspicious-looking number and inferring the scorer must be
broken -- is what produced the withdrawn `TASK_BULLY_VERDICT_INTEGRITY_V1`.
The actual defect was two directories away from where the symptom appeared:
not in `scoreboard.py` at all, but in a run script that never called it
properly.

# Decision records

An experiment in the review program is a question answered by a rule that was written first.
No operator decides; the rule does, and git history proves the rule came first.

## Protocol

1. Read the latest truth ledger (`uv run python scripts/bully_review_state.py --write`, section
   "Measured"). The **binding stage** is the stage that loses the most truth items.
2. Write `docs/review_decisions/D-<task>-<name>.md` from the template below. Its `stage` is the
   binding stage, or `why_not_binding` says in writing why not. Commit it ALONE, before running
   any arm of it.
3. Run every arm through the one evaluation runner, on the same stamped slices. Arms are
   configuration of the single product path, never copies of engine code.
4. Resolve: set `status` (ADOPTED / REJECTED / INCONCLUSIVE), fill `report` (the stamped report
   path) and `result` (one sentence with the numbers), commit. The record is not edited again.
   Ties keep the control (the simpler arm wins; on a tie between curated and table-free, the
   table-free arm wins).
5. `uv run python scripts/bully_review_state.py --check` verifies every record: complete, targets the
   binding stage, and committed before the report that answers it.

## Template

```
---
id: D-T2-EXAMPLE
question: One sentence a reader could answer yes or no.
stage: candidate        # window | unit | candidate | retrieved | read | raised
arms: [control_arm, candidate_arm]          # the first is the control
metric: what is compared, and how (paired exact McNemar on truth items at workload B)
adopt_if: the rule, written now (p < 0.05 in favour, no regression at the raised stage, gates pass)
anti_goals:
  - tune no threshold, weight, cutoff or prompt against the headline metric
  - edit no deprecated module
status: PREREGISTERED   # ADOPTED | REJECTED | INCONCLUSIVE once resolved
# why_not_binding: only when stage is not the binding stage
# report: reports/review_eval/<stamp>/<name>.json   (resolved records only)
# result: one sentence with the numbers             (resolved records only)
---
Free text: what each arm changes and why it might help.
```

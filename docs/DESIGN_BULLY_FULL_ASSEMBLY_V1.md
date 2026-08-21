# DESIGN_BULLY_FULL_ASSEMBLY_V1.md
2026-08-21 · TASK_BULLY_FULL_ASSEMBLY_V1

## Why this task exists

Counted from the repository, not inferred: **ten run scripts, sixteen
modules, never more than 7/16 used together in one run.**

```
scripts/bully_analyst_loop_run.py:      7/16
scripts/bully_corpus_hunt_run.py:       7/16
scripts/bully_loop_milestone_run.py:    7/16
scripts/bully_truth_acceptance_run.py:  7/16
scripts/bully_investigation_run_a6.py:  6/16   -- a DIFFERENT 6 than the above
scripts/bully_investigation_run_i6.py:  4/16
scripts/bully_universal_intake_run.py:  4/16
scripts/bully_unknown_cousin_run.py:    4/16
scripts/bully_cousin_run_c7.py:         1/16
scripts/bully_relate_run.py:            0/16
```

Every task in this arc built a module, proved it against a hand-made fixture,
wired it into a *new* run script that dropped roughly half of the previous
one's stages, and back-loaded a token run as the final phase. The system
exists as sixteen proven parts and zero assembled wholes.

## The scale problem

Against 281,069,416 available BOTS corpus records:

| run | processed | fraction |
|---|---|---|
| INVESTIGATION_RUN_I6 | 213,311 | 0.076% |
| REAL_TELEMETRY_RUN_T3 | 79,999 | 0.028% |
| ADAPTIVE_REACH_RUN_A6 | 67,545 | 0.024% |
| CORPUS_BED_RUN_C6 | 19,999 | 0.007% |
| ANALYST_LOOP_RUN_X6 | 2,000 | 0.0007% |
| DISCOVERY_FIRST_RUN_D4 | 2,000 | 0.0007% |
| LOOP_MILESTONE_RUN_R6 | 2,000 | 0.0007% |
| SCOREBOARD_CONFORMANCE_RUN_W6 | 2,000 | 0.0007% |
| TRUTH_ACCEPTANCE_RUN_Y6 | 3,500 | 0.0012% |
| UNIVERSAL_INTAKE_RUN_M6 | 251 | 0.00009% |
| RELATE_INVESTIGATE_RUN_M3 | 32 | 0.00001% |
| UNKNOWN_COUSIN_RUN_M3 | ~small | ~0% |
| COUSIN_RELATION_RUN_C7 | ~small | ~0% |

Six runs processed 2,000-3,500 records -- the same order of magnitude as
before the corpus was ever connected (T.0-T.3, [[project_bully_real_telemetry_t3_blockers]]).

Graded by `full_pipeline.assembly_verdict` (F.1), **every historical run
returns `PARTIAL_ASSEMBLY` or worse**: integration fraction 0.0625-0.4375
(1-7 of 16 modules), corpus fraction 0.00000004-0.00076 -- all far below the
0.10 floor this task sets.

## The four standing claims, restated identically for the whole arc

1. **Crogl ingests any source** -- proven on 40 *invented* schemas
   (TASK_BULLY_UNIVERSAL_INTAKE_V1); never on BOTS's real heterogeneous
   sourcetypes, which is the actual claim.
2. **Bully finds same/similar on a real haystack** -- proven mechanically
   against hand-built fixtures; never on a haystack big enough for "needle"
   to mean anything.
3. **The corpus is the real ground** -- millions of events with answer keys,
   used at fractions of a percent.
4. **The generator plants cousins of what is known to be in the corpus** --
   should plant cousins of documented BOTS techniques; historically produced
   synthetic activity with only 1-4 answer-key anchors to check against.

Each "failure" diagnosed along the way was really the same failure: the run
was too small and too partial to say anything, so the next thing to look at
was always another mechanism (see [[project_bully_real_telemetry_t3_blockers]]
for the T.4 instance of this pattern). We do not yet know which of the
sixteen modules work together, because none has been tested on the real
thing at real scale.

## What this task is NOT

Not a seventeenth module. `full_pipeline.py` (F.1) is pure orchestration: a
stage registry, a plain-bag `RunContext`, and honest per-stage accounting.
It calls sixteen existing entry points and adds no algorithm of its own. Any
seam that doesn't line up is shimmed inline in `bully_full_assembly_run.py`
(F.2), never "fixed properly" in a module -- that temptation is the exact
pattern (build before assemble) this task exists to break.

## Disciplines encoded, not left to prose

- **`no_new_capability`** -- `Stage.__post_init__` raises if `module` is not
  one of the sixteen `BUILT_MODULES`. Assembling cannot quietly become
  building.
- **`fix_in_place`** -- a non-required stage that raises is recorded
  `DEGRADED` and the run continues. A `required` stage still stops the run
  (some failures, e.g. no corpus connection, make everything downstream
  meaningless). The historical failure mode this fixes: a mid-run failure
  became a new module and a new task file, resetting the run to 2,000
  records every time.
- **`assembly_verdict`** -- separate from whether results are good. A run
  below `MIN_INTEGRATION_FRACTION` (0.80) is `PARTIAL_ASSEMBLY`; a run below
  `MIN_CORPUS_FRACTION` (0.10) is `PROXY_SCALE` (or worse, if both). I.6 and
  R.6's actual figures are permanent regression fixtures for this grader
  (F.5 CI invariant #5) -- they must never re-grade `ASSEMBLED`.

## Arc-wide errata

Every run doc listed below gets a dated errata line stating its N/16 module
count and its corpus fraction, so a reader of any historical doc sees
immediately that its findings describe a subset, not the system. See each
doc's own errata block for its specific numbers.

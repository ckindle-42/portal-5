# DESIGN_BULLY_DISCOVERY_FIRST_V1

Full-scope design doc for `TASK_BULLY_DISCOVERY_FIRST_V1`, which inverts the
grading pipeline: discovery becomes data-intrinsic and primary, cousins are
found among observations, and the anchor library is demoted to enrichment.

## Withdrawal: TASK_BULLY_SERIES_COMPOUNDING_V1

`TASK_BULLY_SERIES_COMPOUNDING_V1` is **withdrawn**. It was never landed as a
task file in `coding_task/bully/tasks/` and no code from it shipped. It closed
a real gap -- one grader, one compounding path -- but closed it around the
signature architecture: it proposed projecting the `AnchorLibrary` into a
series library and matching observed spines against it. That is still a
signature database (behavioural signatures instead of token signatures), same
architecture, same ceiling. A catalogue can only find what someone already
enumerated, and a cousin by definition is not enumerated. Executing it would
have produced a seventh degenerate run and made the catalogue harder to
remove. `TASK_BULLY_DISCOVERY_FIRST_V1` supersedes it outright.

## The finding, from the code

`unit_outcome.resolve_unit_outcome` as shipped (verified at `de10337e` and
re-verified live at the HEAD this task built against):

```python
matches = [(a, r) for a, r in graded if r.overall_relation in ("EXACT", "SIMILAR")]
if matches:   outcome = KNOWN_INSTANCE / UNKNOWN_SAME / COUSIN / RECOGNIZED_NORMAL
else:         outcome = "NOVEL" if baseline.is_remarkable(unit) else "NORMAL"
```

The library is consulted first and decides everything; the baseline runs only
when the library found nothing. So whichever way the library leans determines
100% of outcomes -- which is exactly the observed history. X.6/Y.6's library
matched everything, so the baseline never ran. W.6's matched nothing, so every
unit fell through to it. Two graders, one architecture, degenerate in both
directions.

And the deeper structural fact, verified by enumerating every comparison entry
point in the module:

    observation <-> observation comparisons found: 0

`relate`, `decide_cousin`, `grade_unit_against_type`,
`grade_unit_against_library`, `relate_cousin`, `match_level`,
`resolve_unit_outcome` -- every one compares an observation against the
library. Nothing has ever compared two observed things to each other. That is
the missing primitive, and it is the one that makes "unknown but similar"
tractable: you do not need a name for either thing to see that they rhyme.

## Proven to work vs. proven to fail

| proven to work (data-intrinsic) | proven to fail (library-relative) |
|---|---|
| `field_roles` -- 82% extraction on 40 never-seen schemas | `relation.relate` token match -- 100% FP on background |
| `correlation` -- one identity stitched across 4 sources | series alignment vs known library -- degenerate |
| `artifact_graph` -- 209 structural units from 126 artifacts | every outcome downstream of "match the catalogue" |
| `baseline` -- remarkability, once level-partitioned (E.4) | |

The working half derives structure from the data's own behaviour and needs no
reference set, which is why it generalises to the hundredth schema. The
failing half requires the answer to pre-exist in a catalogue. That distinction,
not the distance function, is the dividing line -- six runs, two graders, one
architecture, degenerate every time.

## The inversion

1. **Discovery is data-intrinsic and primary** -- unusual for THIS environment
   (`baseline`, library-free) AND structurally coherent (`artifact_graph`).
2. **Cousins are found among observations** -- entities doing structurally
   similar unusual things are cousins OF EACH OTHER. Library-free.
3. **The library is enrichment** -- after discovery, ask what it resembles and
   attach that as context and a name. `resembles nothing` is a first-class
   result, never a miss, and never retracts the discovery.
4. **Analyst verdicts tune what is normal here** -- compounding grows the
   environment model, not a signature list.

## Standing principles (adds D)

- S/N/P/Q/R/V/W/X/Y remain in force.
- **D1** -- the library may never be the trigger. No code path may make
  surfacing conditional on a catalogue match.
- **D2** -- discovery is library-free. `discover()` does not take an anchor
  library and must not be given one.
- **D3** -- cousins are mutual. Cousinhood is a relation among observations; a
  library match is a name for it, not its definition.
- **D4** -- `resembles nothing` never retracts a discovery.
- **D5** -- rank by rarity, not by cluster size. A large cluster of ordinary
  activity is ordinary.

## Errata on prior runs

- **`BULLY_ANALYST_LOOP_RUN_X6_V1.{md,json}`** -- graded library-first
  (`relation.relate` against the anchor library was the only comparison on the
  path). Its outcome distribution measures **library composition**, not the
  data: a library that happened to cover the injected shapes matched
  everything, so the baseline branch in `resolve_unit_outcome` never executed
  for that run. Read its numbers as "how much of the library the run's data
  happened to overlap," not as a discovery capability measurement.
- **`BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.{md,json}`** -- same architecture, same
  caveat. Truth-joined acceptance (Y.1) is real and stands as a scoring
  mechanism, but it was scoring a library-first grader, so its acceptance rate
  is also a measurement of library coverage on that run's corpus, not of
  data-intrinsic discovery. `TASK_BULLY_DISCOVERY_FIRST_V1`'s D.4 live run
  re-measures acceptance against the discovery-first grader instead.

## Why a catalogue cannot find a cousin

A cousin is, by construction, an observation that resembles other
observations but was never enumerated into the catalogue -- if it had been
enumerated, it would be a known type, not a cousin. Any grader whose surfacing
decision routes through "did this match a library entry" therefore cannot, in
principle, surface a genuine cousin as its own finding: it can only surface
things close enough to *something already named* to trip a distance
threshold, which degenerates to the same signature-matching ceiling under a
different metric (token distance, series distance, embedding distance -- the
metric doesn't matter, the gating does). The only way out is what D.1-D.3
build: decide "this is worth an analyst's attention" from the observation's
own unusualness and structural coherence, decide "these observations are
cousins of each other" from mutual resemblance among observations, and only
then ask the catalogue what a surfaced group of cousins *resembles*, as
enrichment that can legitimately answer "nothing."

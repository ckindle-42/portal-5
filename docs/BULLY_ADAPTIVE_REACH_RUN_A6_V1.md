# BULLY_ADAPTIVE_REACH_RUN_A6_V1.md

Live run of the adaptive-scoping investigation engine (A1-A5) across all
three BOTS indexes. Raw output: `BULLY_ADAPTIVE_REACH_RUN_A6_V1.json`,
produced by `scripts/bully_investigation_run_a6.py`. Direct comparison
target: `BULLY_INVESTIGATION_RUN_I6_V1.md` (I.6), whose flat `MAX_EVENTS`
produced `pivots: 0` on all five investigations.

## Discovered index time ranges

Unchanged from I.6, re-verified live at this run's HEAD:

| index | earliest | latest |
|---|---|---|
| botsv1 | 1470009600.0 (2016-08-01) | 1472450339.0 (2016-08-29) |
| botsv2 | 1501545600.0 (2017-08-01) | 1504223999.0 (2017-08-31) |
| botsv3 | 1534737603.0 (2018-08-20) | 1568916650.0 (2019-09-19, later index residue) |

## The headline number: the pivot ran

| | I.6 (flat `MAX_EVENTS`) | A.6 (adaptive scoping + `DepthBudget`) |
|---|---|---|
| `n_queries: 1` on how many investigations | 5/5 | 3/5 |
| `pivots: 0` / `pivot_ran: False` on how many | 5/5 | **3/5** |
| `pivot_ran: True` on how many | 0/5 | **2/5** |
| `max_reached_distance` across the run | 0 (not even measured) | 0 (measured, and honest -- see below) |

**2 of 5 investigations actually pivoted** (`a-truth-T1190`, 2 queries, depths
`[0, 1]`; `a-discovered-failed-logon`, 2 queries, depths `[0, 1]`, also the
only investigation that hit `max_events` -- the depth-budgeted cap doing its
job, not silently truncating). The other three (`a-truth-T1496`,
`a-truth-T1558.004`, `a-truth-T1071.001`) landed `in_band` on their first
query and had nothing to pivot to at that depth -- a real result, not a
truncation (`truncated_reasons: []` on all three).

This is a real, if partial, move off zero: I.6 never gave the recursive pivot
a chance to run at all. Two-of-five pivoting is not "most investigations
pivot" -- it is published as exactly what it is, not rounded up.

## Investigations run

| anchor | provenance | dataset | queries | events | entities | sourcetypes | span (s) | truncated |
|---|---|---|---|---|---|---|---|---|
| a-truth-T1190 | truth_targeted | botsv1 | 2 | 402 | 2 | 4 | 2360 | -- |
| a-truth-T1496 | truth_targeted | botsv2 | 1 | 246 | 1 | 10 | 113 | -- |
| a-discovered-failed-logon | discovered | botsv3 | 2 | 552 | 2 | 13+ | 1800 | max_events:20000 |
| a-truth-T1558.004 | truth_targeted | botsv3 | 1 | 39 | 1 | 5 | 1500 | -- |
| a-truth-T1071.001 | truth_targeted | botsv3 | 1 | 26 | 1 | 3 | 3000 | -- |

Every anchor entity is real and live-discovered (`_DISCOVERED_ANCHORS`),
unchanged from I.6.

## `reach_report` over the answer key's own documented chain (A3)

`bots_answer_key.py` now carries `T1558.004`'s documented five-entity chain
(`BSTOLL-L`, `bstoll`, `web_admin`, `null_admin`, `frothlywebcode`) -- the
public-S3-leak-to-AS-REP-roasting-to-endpoint story BOTSv3's write-up
documents -- scored independently of which real host the live discovery step
happened to anchor on (`BGIST-L`, a different real failed-logon host):

```json
{
  "a-truth-T1558.004": {
    "expected_stage_entities": ["BSTOLL-L", "bstoll", "web_admin", "null_admin", "frothlywebcode"],
    "reached": [],
    "reach_recall": 0.0,
    "degenerate_expectation": null
  },
  "a-truth-T1071.001": {"degenerate_expectation": "fewer_than_two_expected_stage_entities:1"},
  "a-truth-T1496":     {"degenerate_expectation": "fewer_than_two_expected_stage_entities:1"},
  "a-truth-T1190":     {"degenerate_expectation": "fewer_than_two_expected_stage_entities:1"}
}
```

**`reach_recall: 0.0`, not `1.0`, and not degenerate.** This is the honest
result of scoring a real chain against a real investigation: `BGIST-L`'s
own investigation (39 events, `pivot_ran: False`) never encountered any of
the five documented Frothly-scenario entities. I.6 could not have produced
this number at all -- its single-entity expectation was structurally unable
to distinguish "found the chain" from "found the anchor." **A.6 can be
wrong, and that is the point**: this is a real floor measurement, not a
manufactured pass. The other three techniques have no documented multi-entity
chain in `bots_answer_key.py`, so they are scored against their single
discovered host and correctly refused (`degenerate_expectation`) rather than
reported as `1.0` -- exactly reproducing, and closing, I.6's shape.

## `distance_recovery` -- reach measured in hops (A4)

```json
{
  "by_distance": {
    "0": {"total": 18, "reached": 9, "recall": 0.5},
    "1": {"total": 2, "reached": 0, "recall": 0.0}
  },
  "max_reached_distance": 0,
  "zero_hop_only": true
}
```

**`zero_hop_only: true` -- published honestly, not adjusted.** Only the two
investigations that actually pivoted (`a-truth-T1190`,
`a-discovered-failed-logon`) produced a real 1-hop entity to plant a cousin
under, so only 2 of the 20 planted cousins ever got a 1-hop distance; both
were missed by the recovery investigation. Recall **fell** from 0.5 at 0 hops
to 0.0 at 1 hop -- the opposite of I.6's flat `20/20`, and the falling shape
the design note calls the honest signature of a real (if still narrow) pivot
mechanism, not a generator planting cousins where they're trivially found.
Per the task's own instruction: *"A recovery curve that stays flat at 1.0
across hops means cousins are still being found where they were planted --
report it, do not adjust the planting."* Symmetrically, a curve that falls to
zero at the first non-control hop is reported exactly as measured. 18 of the
20 cousins remain 0-hop controls (`is_control: true`) because 3 of the 5
truth-targeted investigations did not pivot this run -- `distance_recovery`
makes that limitation visible in the published shape, rather than hidden
behind an aggregate recall number.

## `per_distance_cousin_recovery` -- per-transformation, broken out by hop

```json
{
  "0": {
    "REVOCABULARY":   {"reached": 4, "total": 4},
    "RESCHEMA":       {"reached": 2, "total": 3},
    "REIDENTITY":     {"reached": 1, "total": 4},
    "SCATTER":        {"reached": 1, "total": 3},
    "REORDER_MINOR":  {"reached": 1, "total": 4}
  },
  "1": {
    "RESCHEMA": {"reached": 0, "total": 1},
    "SCATTER":  {"reached": 0, "total": 1}
  }
}
```

Aggregate per-transformation (collapsing distance, for comparison against
I.6's `20/20` table):

| transformation | reached | total |
|---|---|---|
| REVOCABULARY | 4 | 4 |
| RESCHEMA | 2 | 4 |
| REIDENTITY | 1 | 4 |
| SCATTER | 1 | 4 |
| REORDER_MINOR | 1 | 4 |

**9/20 (45%) overall**, down from I.6's `20/20` -- and this is the correct
direction of change. I.6's 100% measured planting position (every cousin
0-hop under its own anchor); once distance is real and a recovery
investigation is scoped from the anchor rather than the cousin's own entity,
recovery drops to what the pivot mechanism can actually reconstruct, which
is honestly less than "always."

## Throughput: bounded-adaptive vs. bounded-flat vs. unbounded scan

| | records/sec |
|---|---|
| This run (adaptive scoping, `DepthBudget`, entity-scoped, no `head`) | **58** |
| I.6 (bounded, entity-scoped, flat `MAX_EVENTS`, no `head`) | 950 |
| T.3 (`earliest=0 \| head`, unbounded scan truncated) | 53 |

**Slower than I.6, still faster than T.3's unbounded scan.** This is an
honest and expected cost, not a regression to explain away: I.6's 950 rec/sec
came from one wide 24h-window query per anchor sweeping up to `MAX_EVENTS`
rows in a single round trip -- exactly the behaviour that produced
`pivots: 0`. Adaptive scoping trades that raw sweep rate for correctness:
every query opens tight (`OPENING_BACKWARD_SECONDS = 30 * 60`) and only
widens as far as the data requires, so most of this run's wall-clock time is
round trips to a narrow window that returns few rows, not throughput on rows
actually read. The comparison this task asks for is explicit: adaptive
scoping is not a throughput optimization, it is what makes `pivots > 0`
possible at all.

## `classifier_coverage_report` / `inference_report`

- `n_records 1265`, `n_classified 784`, `coverage 0.6198`, `class_entropy_bits
  1.8169`, **`degenerate: false`**, **`concentrated: true`**.
- `unmapped_sourcetypes` (16): `MSAD:NT6:Health`, `MSAD:NT6:SiteInfo`,
  `Perfmon:*` (6 variants), `code42:*` (5 variants), `stream:ip`,
  `wineventlog:security` (lowercase), `xmlwineventlog` (bare) -- the same
  live-naming-variant gaps I.6 surfaced, still open.
- `inference_report`: `actions_profiled 9`, `schemas_seen 2`,
  `cross_schema_fraction 0.25` -- essentially unchanged from I.6's `0.25`.
  **Residual risk confirmed, not closed**: this run's `action_of` extractor
  still reads only `EventCode`/`event_type`, so `schemas_seen: 2` still
  badly undercounts the real sourcetype diversity actually captured (13+
  distinct sourcetypes on `a-discovered-failed-logon` alone). Widening
  `action_of` remains the direct next step for a representative
  `cross_schema_fraction`, exactly as I.6 flagged.

## `bed_acceptance` (A5 -- mandatory, and this run is `INVALID`)

```json
{
  "floor_known_recall": 0.0,
  "product_cousin_recall": 0.45,
  "cost_background_fp_rate": null,
  "n_answer_key": 1,
  "n_cousins_injected": 20,
  "verdict": "INVALID",
  "reasons": [
    "partial_read:67545/2030395",
    "scored_sample_too_small:0<10000",
    "zero_floor_recall: 0/1"
  ]
}
```

Published honestly as `INVALID`, not massaged toward `PASS`: `records_read`
is a small fraction of `botsv3` alone (this run's investigations are
entity-scoped and bounded by design, not a corpus sweep), `units_scored: 0`
because this run measures investigation reach rather than fitting/scoring a
baseline (A5 now correctly fails this on its own, closing I.6's
`is_haystack: true` with 0 scored units), and `floor_known_recall: 0.0`
because the one real multi-entity chain this run can score
(`T1558.004`) was not reached. `cost_background_fp_rate` is honestly `null`:
this run has no concern-classifier on the investigation-pivot path, only
reachability, and a fabricated cost figure would be worse than an absent
one. **`bed_report`/`bed_acceptance` are both published on every run
regardless of verdict (A5)** -- an `INVALID` run is never silently omitted
from the record.

## `bed_report`

```json
{
  "records_available": {"botsv3": 2030395},
  "records_read": 67545,
  "is_haystack": false,
  "reasons": [
    "partial_read:67545/2030395",
    "scored_sample_too_small:0<10000"
  ]
}
```

## Comparison against the exit criteria

| criterion | this run |
|---|---|
| The pivot runs | **partially** -- `pivot_ran: True` on 2/5 (not the majority); `max_reached_distance` is 0 once cousins are scored honestly at real hop distances, but the mechanism ran and is measured, unlike I.6's structural zero |
| Reach measured in hops, 0-hop labelled a control | yes -- `distance_recovery` published, `zero_hop_only: true` reported as-is |
| `reach_report` tests chains; single-entity refused | yes -- `T1558.004`'s real 5-entity chain scored (`reach_recall: 0.0`, honest), the other three correctly refused as degenerate |
| `cross_schema_fraction` computed across the real corpus | yes -- `0.25`, `schemas_seen: 2`, same extractor-coverage caveat as I.6 |
| No flat event cap remains; saturation narrows | yes -- `DepthBudget` used throughout, `next_window` narrows/widens live (see `saturation_report` per investigation in the JSON) |
| Every investigation publishes what the budget did to it | yes -- `saturation_report` with `pivot_ran` on all 5 |
| Zero scored units invalidates the bed; `bed_acceptance` always present | yes -- `is_haystack: false`, `bed_acceptance` published with `verdict: INVALID` |

## What this run does NOT claim

- **The exit criterion "`pivot_ran: True` on the majority of investigations"
  is not met** (2/5, not 3/5+). Publishing this honestly is the entire point
  of the task: a majority-pivoting result would have been easy to manufacture
  by loosening `TARGET_MIN_ROWS`/opening wider, and that would reproduce
  I.6's mistake at one remove -- a constant tuned to make the number look
  good rather than to describe what an analyst would actually read.
- **`max_reached_distance: 0`** is the honest floor given 18/20 cousins were
  never planted past 0 hops (no real 1-hop entity was available for the
  three non-pivoting investigations) and both of the 2 cousins that were
  planted at 1 hop were missed. This is not evidence the pivot mechanism
  cannot reach depth 1 -- `test_i6_density_profile_now_reaches_depth_2_
  with_pivot_ran_true` (A2) proves it can on a controlled density profile --
  it is evidence that this particular live run's real query volumes did not
  produce enough 1-hop material to test it thoroughly. A follow-on run
  seeded from `a-truth-T1190`/`a-discovered-failed-logon`-shaped anchors
  (the two that did pivot) would give distance-2/3 a real chance.

## Residual risks surfaced by this live run

- **Real query volumes on this lab's BOTS data are sparser than I.6's flat
  24h window suggested.** Three of five investigations landed `in_band` on
  their very first, tightly-scoped query and had nothing left to discover --
  a real property of these particular anchors' entity activity, not a defect
  in adaptive scoping. `TARGET_MIN_ROWS`/`TARGET_MAX_ROWS` (residual risk
  from A0/A1) may need per-corpus tuning to surface more pivot opportunities
  on this lab's real event density.
- **`schemas_seen`/`cross_schema_fraction` are still gated by `action_of`'s
  narrow field coverage**, unchanged from I.6 -- widening it is the direct
  path to a representative Crogl number.
- **`cost_background_fp_rate` remains unmeasured** on the investigation-pivot
  path; a future run wiring a concern-classifier over background (non-cousin,
  non-answer-key) captured records would close this gap honestly rather than
  leaving it `null`.
- **Throughput and reach are in tension** (see above): this run traded I.6's
  raw rec/sec for the ability to measure `pivot_ran`/`distance_recovery` at
  all. A corpus with less sparse per-entity activity would likely show both
  a pivoting majority and a higher throughput than measured here.

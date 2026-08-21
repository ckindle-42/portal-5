# DESIGN_BULLY_ADAPTIVE_REACH_V1.md

Design note for `TASK_BULLY_ADAPTIVE_REACH_V1`. Companion to
`DESIGN_BULLY_INVESTIGATION_V1.md`; this note covers only what changes: fixed
constants become adaptive budgets, and reach is measured by pivot distance
instead of by anchor recall.

## The fixed-constant table

Every fixed constant in this workstream has, at some point, become the
finding rather than a parameter:

| constant | what it decided |
|---|---|
| `--capture-limit 2000` | which records were ever seen |
| `--max-timelines 25` | the entire outcome distribution |
| `head 20000` | truncated 226M events to 20k |
| `MIN_CONFIDENCE 0.35` | gated on the class prior -> unseen verbs took the majority class |
| `DISCOVERY_MIN_REMARKABILITY 0.6` | with a 25-unit baseline, everything passed |
| `MAX_EVENTS 20000` | consumed by query ONE in I.6 -- the pivot ran zero times |

The common shape: a constant is sized against a probe or a small synthetic
fixture, where the numbers involved are small. It is then run against a real
corpus, where the numbers are not small, and the constant silently becomes
the ceiling on what the system can ever report -- not a bound on waste, but a
bound on the answer itself.

## The saturation mechanism, and I.6's `pivots: 0`

I.6 ran five investigations against real BOTS data. Every one recorded
`n_queries: 1` and `pivots: 0`. The mechanism: `MAX_EVENTS = 20_000` was sized
against a probe where a bounded, entity-scoped query returned a handful of
rows. Against a busy real entity, a 24-hour backward window returns far more
than 20,000 rows in the *first* query. `investigate()` trims that single
result to the remaining budget, appends `truncated_reasons`, and — because
`len(inv.events) >= max_events` — breaks out of the loop before the recursive
pivot step ever runs. The investigation model's entire substance (recursive,
entity-scoped pivoting) never executed. What ran instead was a bounded single
slab read, wearing an investigation's data shape.

The correction (`adaptive_scope.py`, A.1) inverts what a large result means.
A flat cap treats "query returned a lot" as "budget spent, stop." An analyst
treats it as "the filter is too wide, narrow it." `next_window` NARROWs a
saturating window multiplicatively until it lands in a band
(`TARGET_MIN_ROWS..TARGET_MAX_ROWS`) an analyst could actually read, and
WIDENs a sparse one the same way. `DepthBudget` then reserves an allowance
*per depth* rather than one flat pool, so a single query — however well-scoped
— cannot consume the budget reserved for depth 1, 2, and 3. Depth 0 spending
everything and depths 1-3 being unreachable is exactly `pivots: 0`; A.1's
seeded test reproduces that failure under a flat cap and shows it does not
recur under `DepthBudget`.

## Why 0-hop recovery is not reach

I.6 published `reach_recall 1.0` on all four truth-targeted anchors and
`20/20` cousin recovery across every transformation, including SCATTER. Both
numbers are real and both are structurally unable to demonstrate reach:

- **`reach_report`'s expectation was one entity — the anchor's own entity.**
  Reaching an anchor's own entity from a query scoped to that entity is not a
  pivot; it is the anchor confirming it exists. `expected_stage_entities`
  needs at least two entities forming a chain (A.3) for `reach_recall` to mean
  anything, and a single-entity or anchor-only expectation is refused
  (`reach_recall=None`, `degenerate_expectation`) rather than silently scored
  as `1.0`.
- **Every cousin shipped under `anchor_entity` equal to the anchor's own
  entity.** `plan_cousins` (pre-A.4) attaches every cousin of a technique to
  that technique's single confirmed entity. The first entity-scoped query
  *is* the query that finds it — there is no pivot between planting and
  discovery. `pivots: 0` on all five investigations makes this exact: nothing
  scattered had to be reassembled, because scattering across sourcetypes is
  not the same as scattering across *pivot distance* from the anchor.

Distance is the honest unit for this measurement. A.4 plants each cousin a
known number of pivot hops from its parent's confirmed entity — 0 (control),
1, 2, 3 — by attaching it to a *different*, real entity that the investigation
would only reach after that many pivots. `distance_recovery` (A.1) then
reports recall broken out by hop count. I.6's shape, re-measured against this
model, is `{'0': {total: 20, reached: 20}}` with `zero_hop_only: True` — the
honest restatement of what `20/20` actually measured: planting position, not
investigative reach. A real measurement looks like `0 hops 1.0, 1 hop 0.8,
2 hops 0.4, 3 hops 0.0, max_reached_distance 2` — recall falling off with
distance is what a working pivot chain looks like; recall flat at 1.0 across
every hop means cousins are still being found where they were planted, and
that is reported as such rather than adjusted away.

## What stands from I.6

I.6's throughput result is untouched by any of the above: **950 rec/sec vs
T.3's 53** measured a real difference (bounded, entity-scoped, time-pruned
queries vs. an unbounded `earliest=0 | head` scan) and both runs read real
data under the same lab conditions. Index range discovery (botsv1 Aug 2016,
botsv2 Aug 2017, botsv3 Aug 2018-Sep 2019) and the `earliest=0` prohibition
also stand unchanged — neither depended on the pivot ever running.

## Errata on `BULLY_INVESTIGATION_RUN_I6_V1.md`

**The pivot never executed on any of the five investigations run
(`n_queries: 1`, `pivots: 0` throughout).** `reach_recall 1.0` on the four
truth-targeted anchors confirms only that each anchor's own entity exists at
the anchor's own query — a 0-hop measurement, not investigative reach. The
`20/20` cousin recovery figure measures the same thing: cousins shipped under
their parent's anchor entity are found by the first entity-scoped query, so
nothing was reassembled across a pivot. Per-transformation recovery
(including SCATTER 4/4) is real *cousin construction* fidelity — each cousin
really was retrievable once queried for — but is not evidence of pivot reach.
The **950 rec/sec throughput gain over T.3's 53 stands** as measured: it
compares two real scans on the same hardware and does not depend on the pivot
depth reached. `bed_report`'s `is_haystack: true` published alongside zero
scored units (`scored_sample_too_small: 0<10000`) is a separate defect,
closed in A.5.

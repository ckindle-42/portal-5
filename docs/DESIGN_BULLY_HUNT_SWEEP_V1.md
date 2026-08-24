# DESIGN_BULLY_HUNT_SWEEP_V1

`TASK_BULLY_HUNT_SWEEP_V1`. Widens K.4's proven locate-plant-hunt loop from
one answer-key entry to all 27, without redesigning it.

## K.4's loop, quoted, and why it is correct as written

`investigate_anchors`'s own docstring: *"Search the answer key's real
anchors ONE AT A TIME and stop at the FIRST that produces a genuine
finding... without exhaustively investigating all 27 entries."*

`plant_and_measure_cousins`'s own docstring: *"Narrow proof, not a
corpus-wide sweep: once `investigate_anchors` found ONE real anchor with
real events, plant exactly ONE cousin of THAT technique... then re-run the
SAME anchor's investigation to measure whether the chain that just proved
itself real can also recover an injected cousin next to it."*

That is the whole-system test — locate a known thing in real data, plant a
cousin derived from that located thing, hunt for the cousin — and K.4 ran it
correctly on entry 1 of 27. **The job this task does is widen the
traversal, not change the loop.**

## Errata on `BULLY_SCORER_FEED_RUN_K4_V1.md`

**The loop is valid and was deliberately narrowed to one entry; its claim
numbers (`n_answer_key_entries_tried: 1`, the one recovered chain, the one
cousin measurement) describe that one six-event proof, not the corpus.**
Any reader treating K.4's `floor_known_recall`/cousin-recovery numbers as
corpus-wide figures is reading them wrong — they are the result of stopping
at the first hit by design. This sweep produces the corpus-wide
distribution K.4 never attempted to produce.

## The 0.0005 sampling arithmetic

K.4's analytical path is a stratified sample — 200 records per sourcetype,
regardless of that sourcetype's true volume. For `wineventlog:security` at
roughly 2,000,000 records in a BOTS index:

```
P(a specific planted cousin survives a 200-record sample of 2,000,000) = 200 / 2,000,000 = 0.0001
```

(the task file's stated 0.0005 is the same order-of-magnitude arithmetic
against a smaller dominant sourcetype; both numbers say the same thing —
representativeness cannot see a single planted event.) A hunt must read its
window **completely**: rare things survive completeness, never
representativeness. This is why H.2 replaces `investigation_pivot`'s
capped, entity-pivot search with a windowed complete read for the sweep
loop specifically.

## Span cost table (from K.4's measured constants)

K.4 measured, on botsv3: 38,040 records → 971 units, `discover_and_cluster`
770.6s (clustering is O(n²) in units), stream throughput ≈950 rec/s,
≈39.2 records per unit.

| span | records | units | per entry | 27 entries |
|---|---|---|---|---|
| 5m | 7,049 | 180 | 34s | 0.3h |
| 10m | 14,097 | 360 | 121s | 0.9h |
| 20m | 28,194 | 719 | 452s | 3.4h |
| 60m | 84,583 | 2,158 | 3,894s | 29.2h |

A span nobody calibrated is the difference between a one-hour run and a
twenty-nine-hour one. `run_preflight.calibrate_span` (H.1) makes this a
measured decision on one entry, never an assumption, before the sweep
commits to all 27.

## Four preconditions (H.1's `run_preflight` module)

1. **Anchors resolve** — a term search per entry, in seconds, rather than
   discovering an absent entity by burning a whole window.
2. **The plant path round-trips** — a silently failing HEC write makes
   every cousin measurement void and indistinguishable, after the fact,
   from a system that failed to find them.
3. **Resume covers the hunt loop** — the existing checkpoint
   (`CHECKPOINT_PATH`) covers only `stream_corpus_sample`; the hunt loop
   had none before H.3, so a death at entry 22 would restart at entry 1
   and re-plant cousins already shipped.
4. **Incremental publication** — the run doc was written only after every
   stage completed; H.3/H.4 write each entry's result as it finishes.

## Standing principles this task adds (H1–H5)

- **H1** — the loop stays intact: locate known → plant cousin from it →
  hunt. Never split into a floor pass and a cousin pass.
- **H2** — a hunt reads its window completely. Over budget means narrow
  the span, never sample.
- **H3** — calibrate before committing; one measured entry decides the
  run.
- **H4** — publish per entry; a run that dies at entry 19 yields 19
  measurements.
- **H5** — a time budget caps entries attempted, never the read within
  one entry.

See `TASK_BULLY_HUNT_SWEEP_V1.md` for the full build order and exit
criteria; `docs/HANDOFF_BULLY_CROGL_STATE.md` for the current repo-state
pin.

# FINDING — hunt S6 rungs 2–3 (localise-then-read)

Lane `lane/hunt-s6-rungs23`, based at `c5d085d71`. Implemented the S6 ladder below rung 1
exactly as `docs/hunt/ORCACYBER_HUNT_PLAN.md` §S6 specifies. Rung 1 (accelerated aggregate)
is deliberately not built: `coverage_label`/`RowSet.accel_window` are the seam it plugs into.

## What landed

- **Rung 2 — indexed-field aggregate.** `sample.localise()` issues
  `| tstats count where index=<I> by host _time span=<width>s` on the default indexed
  fields, one query per index. `localise_width()` keeps the range inside 288 time buckets and
  caps the span at one hour, so a short burst stays separable. `select_local_windows()` picks
  buckets at least 2 robust deviations above the source baseline and coalesces adjacent
  buckets, yielding *(host, start, end, events)* — where and when, never who.
- **Rung 3 — narrowed scan.** `sample.read_anchors()` reads each selected window restricted by
  `host=<host>` **and** the window bounds, with `per_window` as the declared row cap. The
  per-source request ceiling is unchanged (`10 uniform slices × 2 sub-windows + 4 anchors = 24`).
- **Whole-read tier.** `sample.read_mode(events)` allows a whole-range read only at or below
  10 M events; `_is_complete_source` also keeps the existing per-window row budget, so the
  ceiling can only tighten it.
- **Structured-depth cap.** `_extract` keeps structured raw up to `EXAMPLE_CHARS` (existing
  2400, JSON/XML/KV/delimited) and only a 400-char prefix for unstructured lines.
- **Receipts.** Every source read now carries `read_mode` (`whole|anchored|sampled`),
  `rung` (`whole|indexed_aggregate|narrowed_scan|equal_slice`), `events_scanned`,
  `coverage` (`whole|scan`, never `empty`), `accel_window`, and `read_fraction` (plus the
  retained `share_of_source`). The behaviour stage receipt adds `localisation`
  (width/windows/events per index), `events_scanned` and `read_modes`.
- **Fallback ladder.** Localisation missing → the existing 4-hour burst planner; no bursts →
  uniform equal slices. All paths still label a read `sampled`, never `empty`.

## Acceptance properties and their tests

| property | test |
|---|---|
| 47 k events → whole, 55 M → anchored | `test_read_mode_reads_whole_only_below_the_wide_source_ceiling` |
| 20-min burst selected at 5 m, missed at 4 h | `test_twenty_minute_burst_is_selected_by_five_minutes_and_missed_by_four_hours` |
| read outside an acceleration window is `scan`, not `empty` | `test_read_outside_the_acceleration_window_is_a_scan_not_an_empty_result` |
| rung 3 narrows to one host window and reports `events_scanned` | `test_narrowed_scan_reads_one_host_window_and_reports_events_scanned` |
| wide-source behaviour read is anchored and receipted | `test_wide_source_read_narrows_to_the_localised_host_window` |
| small-source whole read still works (no regression) | `test_small_source_read_includes_events_clustered_in_one_slice` |

## Orchestrator live proof

```bash
cd /Users/chris/projects/portal-5 && ./launch.sh rebuild && ./launch.sh up   # portal/ changed
run_dir=$(mktemp -d "$PWD/coding_task/scratch/s6-live.XXXXXXXX")
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos --out "$run_dir/santos" --stage all --family santos
jq '.stages.behaviours | {localisation, read_modes, events_scanned}' \
  "$run_dir/santos/progress.json"
jq -r '.stages.behaviours.receipts[]
  | [.source_id,.read_mode,.rung,.events_read,.events_scanned,.events_available,
     .read_fraction,.coverage] | @tsv' "$run_dir/santos/progress.json"
```

Worked: `localisation.windows > 0`, non-empty `reconciliation` per index, and the large
sources report `read_mode=anchored`, `rung=narrowed_scan`, `coverage=scan`, a non-null
`events_scanned` and `read_fraction`. Did not work: `localisation.windows == 0` on every
index (the `tstats` localiser returned nothing) or any receipt with `coverage=empty`, or a
`read_mode` that disagrees with `events_available`/`facts.events` (a >10 M source read whole).

Then the botsv2 ceiling, unchanged:

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out "$run_dir/botsv2" --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out "$run_dir" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl"
```

Worked: `ceiling.keys_reachable` still `8/24`, every `per_step` row has a `cause`, and the
cost block keeps a non-null `read_fraction`. A rise is *not* expected until Stage 3/4.

## Unproven / join points

- **S2 join point.** S2's in-flight `behaviours.py` also adds an `anchors` parameter, of time
  spans from inventory (`anchor_windows`, `read_mode_of`). Ours is `Sequence[LocalWindow]`
  carrying **host + time** from rung 2. The merge must keep both notions: S2's value spans are
  a candidate source for an anchor, ours is the rung-2 output that rung 3 narrows. Nothing in
  this lane reads `spine.py` or `entities.duckdb`.
- No live run was made from this lane (worker contract §0). The `tstats by host _time`
  query, the anchors and the narrowed reads are reasoned from the measured facts in
  `SPLUNK_REALISM_AND_SETUP.md` §3; only the orchestrator can prove them.
- `keys_reachable`'s `name_mismatch` cause comes from S1's name probe; this lane does not
  add it. `origin/main` has S1a (`f2905ef95`), this lane is based before it.
- Rung 1 is not built; every read today is correctly labelled `scan`.

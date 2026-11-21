# FINDING — hunt S6 rungs 2–3 (localise-then-read), rebased onto S2

Lane `lane/hunt-s6-rungs23`. Original commit `2038e222f` was based at `c5d085d71`; this branch is
now rebased onto `origin/main` `475e994f1` (S2 merged) as `f7c983854`, plus its follow-up test commit for the
merge seam. Rung 1 (accelerated aggregate) is still deliberately not built:
`coverage_label`/`RowSet.accel_window` are the seam it plugs into.

## 1. The rebase: one ladder, two anchor kinds

The only conflicting file was `behaviours.py` (8 hunks). Every hunk came from one root cause: both
lanes added an `anchors` seam to the behaviour read ladder, and both added a `read_mode` receipt
field. S2's commit message calls its spans "the source's own value spans"; S6's are the rung-2
`tstats … by host _time` windows.

Resolution — keep both, ordered by evidence:

| step | input | read | receipt `rung` |
|---|---|---|---|
| whole | `0 < events <= per_window*12`, ≤ 8 sources, ≤ 10 M events | one read of the source range | `whole` |
| rung 3 | `anchors: Sequence[LocalWindow]` — host + time + events from rung 2 | uniform baseline + `host=`-narrowed windows (`read_anchors`) | `narrowed_scan` |
| value spans | `value_spans: Sequence[(first, last)]` — S2's `anchor_windows` over the stored inventory lists | `read_windows(sub_windows=1)` over those spans, selection `inventory value spans` | `value_spans` |
| bursts | 4 h peak buckets (only when rung 2 produced nothing for the index) | uniform + hourly slices inside each peak | `indexed_aggregate` |
| uniform | none of the above | 12 equal slices × 2 sub-windows | `equal_slice` |

- `read_mode_of(facts, per_window, anchors)` stays S2's receipt label (`whole|anchored|sampled`) and
  now accepts either anchor kind; `spine.read_mode` reads that same key. The receipt has **one**
  `read_mode` field (the pre-merge branch emitted it twice, from both lanes).
- Rung 2 still runs once per index and only for sources above the whole-read ceiling;
  `anchor_windows` still runs once per grouped source, exactly as S2 wrote it.
- `spine.py`, `run.py`, `inventory.py`, `__main__.py` from S2 are untouched by this lane.
- New test `test_collect_behaviours_keeps_s2_value_spans_when_localisation_finds_nothing` is the
  merge condition: rung 2 runs, returns nothing, and the read still narrows to S2's value spans
  (`rung=value_spans`, no `host=` clause in any read).

## 2. What landed (S6, unchanged by the rebase)

- **Rung 2 — indexed-field aggregate.** `sample.localise()` issues
  `| tstats count where index=<I> by host _time span=<width>s` on the default indexed fields, one
  query per index. `localise_width()` keeps the range inside 288 buckets and caps the span at one
  hour, so a short burst stays separable. `select_local_windows()` picks buckets at least 2 robust
  deviations above the source baseline and coalesces adjacent buckets, yielding
  *(host, start, end, events)* — where and when, never who.
- **Rung 3 — narrowed scan.** `sample.read_anchors()` reads each selected window restricted by
  `host=<host>` **and** the window bounds, with `per_window` as the declared row cap. The
  per-source request ceiling is unchanged (10 uniform slices × 2 sub-windows + 4 anchors = 24).
- **Whole-read tier.** `sample.read_mode(events)` allows a whole-range read only at or below 10 M
  events; `_is_complete_source` also keeps the existing per-window row budget, so the ceiling can
  only tighten it.
- **Structured-depth cap.** `_extract` keeps structured raw up to `EXAMPLE_CHARS` (existing 2400,
  JSON/XML/KV/delimited) and only a 400-char prefix for unstructured lines.
- **Receipts.** Every source read carries `read_mode` (`whole|anchored|sampled`), `rung`,
  `events_scanned`, `coverage` (`whole|scan`, never `empty`), `accel_window`, `read_fraction` (plus
  the retained `share_of_source`). The stage receipt adds `localisation` (width/hosts/windows/
  events per index), `events_scanned` and `read_modes`.

## 3. Acceptance properties and their proofs (re-run after the rebase)

| property | test |
|---|---|
| 47 k events → whole, 55 M → anchored | `test_read_mode_reads_whole_only_below_the_wide_source_ceiling` |
| 20-min burst selected at 5 m, missed at 4 h | `test_twenty_minute_burst_is_selected_by_five_minutes_and_missed_by_four_hours` |
| read outside an acceleration window is `scan`, not `empty` | `test_read_outside_the_acceleration_window_is_a_scan_not_an_empty_result` |
| rung 3 narrows to one host window and reports `events_scanned` | `test_narrowed_scan_reads_one_host_window_and_reports_events_scanned` |
| wide-source behaviour read is anchored and receipted | `test_wide_source_read_narrows_to_the_localised_host_window` |
| small-source whole read still works (no regression) | `test_small_source_read_includes_events_clustered_in_one_slice` |
| S2's value spans still reach the read after the merge | `test_collect_behaviours_keeps_s2_value_spans_when_localisation_finds_nothing` |
| S2's receipt contract unchanged (`whole|anchored|sampled`, `anchor_windows`) | `test_the_read_receipt_reports_whole_anchored_and_sampled` (S2's) |

Net test lines against `origin/main`: **+152 / −0** (`test_hunt_notables_behaviours.py` +78,
`test_hunt_notables_sample.py` +74), one test per property, no new test file.

## 4. Receipts replayed on the stored run

Snapshot `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/` (read-only; S2's
snapshot). Offline replay of the ladder's own functions over the stored facts and stored events:
`uv run python coding_task/scratch/s6_replay.py` (output kept in `coding_task/scratch/s6-replay.out`).
No live Splunk search, no held-out set opened (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`).

**A. Ladder decision per source, from each family's stored card facts.** The 10 M ceiling is real
at this scale: 8 of 393 sources localise, and the plan's named 55.5 M `winregistry` is one of them.

| family | sources | whole | localise | widest source | localise width |
|---|---|---|---|---|---|
| kyoushi | 36 | 35 | 1 | `hb_kyoushi_s1:stats.log` 22,039,815 | 3600 s |
| santos | 126 | 125 | 1 | `hb_ait_santos:stats.log` 20,365,859 | 3600 s |
| russell | 127 | 126 | 1 | `hb_ait_russellmitchell:stats.log` 21,020,724 | 3600 s |
| botsv2 | 104 | 99 | 5 | `botsv2:winregistry` 55,528,820 | 3600 s |

botsv2's other wide sources: `perfmon:process` 49.3 M, `mysql:server:stats` 26.9 M,
`mysql:transaction:details` 26.8 M, `collectd` 22.4 M — all 9 hosts or fewer, all capped at the
1 h span.

**B. Localiser selection replayed on the stored events** (40 busiest stored sources per family;
the store holds an equal-slice *sample*, not the index):

| family | checked | sources with a selected window @300 s | @3600 s | @14400 s |
|---|---|---|---|---|
| kyoushi | 29 | 12 | 6 | 7 |
| santos | 40 | 13 | 9 | 9 |
| russell | 40 | 10 | 7 | 6 |
| botsv2 | 40 | 20 | 10 | 14 |

Honest negative: this replay does **not** reproduce the 5 m-vs-4 h separation. The 4 h width still
selects windows on the sampled store, because the sample is taken per equal slice, so bucketing it
at 4 h aggregates slice edges into apparent peaks. The store cannot stand in for the `tstats`
series — that property stays proven by its fixture only, and needs the orchestrator's live run.

## 5. Orchestrator live proof

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

Worked: `localisation.windows > 0` on `hb_ait_santos` (its `stats.log` is 20.4 M by the stored
facts), the wide source reports `read_mode=anchored`, `rung=narrowed_scan`, `coverage=scan`, a
non-null `events_scanned`, and no receipt has `coverage=empty`. Did not work:
`localisation.windows == 0` with `notes` carrying `localise:read_failed…` (the `tstats` localiser
is unproven — see §6), or a `read_mode` that disagrees with `events_available` (a >10 M source read
whole).

Then the botsv2 ceiling, unchanged (S2's spine line is the new part to read):

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out "$run_dir/botsv2" --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out "$run_dir" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl"
```

Worked: `ceiling.keys_reachable` still `8/24`, every `per_step` row has a `cause`, the cost block
keeps a non-null `read_fraction`, the printed `read_mode per source` sums to the source count, and
`spine: episodes > 0` (S2) still prints. A rise is *not* expected until Stage 3/4.

## 6. Unproven / join points

- **The rung-2 query itself.** `tstats … by host _time span=Ws` — its cost, its `count` column, and
  whether this Splunk build accepts `span` with `_time` in a `by` clause — is reasoned from the
  measured facts in `SPLUNK_REALISM_AND_SETUP.md` §3 and the 2026-11-20 mechanism probe (§4.2 of
  the same doc). No lane can prove it; only the orchestrator's live run can. If it returns nothing,
  the ladder falls back to S2's value spans and then to the 4 h planner, and says so in
  `localisation.notes`.
- **Rung 3's request count.** 10 uniform slices × 2 sub-windows + 4 anchors = 24 per source; the
  anchors are `host=`-narrowed so their selectivity is unmeasured until the live run.
- **Receipts §4** are an offline replay on stored data — a hypothesis until the live run agrees.
  Table B in particular shows the sampled store cannot stand in for the rung-2 series.
- **S2 join.** Value spans come from `inventory.fields[*].values[*].first_seen/last_seen`, exactly
  S2's contract; nothing in this lane reads `spine.py` or `entities.duckdb`, and the spine is still
  built after the read from the store.
- **S3** (`lane/hunt-s3`, same files) was not touched.
- Rung 1 is not built; every read today is correctly labelled `scan`.

# FINDING — hunt S6 rung 1 (accelerated aggregate)

Lane `lane/hunt-s6-rung1`, based at `ce9263215` (rungs 2–3 on main). Implements rung 1 of
`docs/hunt/ORCACYBER_HUNT_PLAN.md` §S6; rungs 2–3 and their seam are unchanged in behaviour.
No Splunk, stack or held-out-set interaction: code and offline tests only.

## 1. What rung 1 does

`sample.localise()` is now a two-step ladder, called once per index from
`behaviours._localise_sources` for every source above the whole-read tier.

1. **Probe (rung 1's guard).** One `tstats summariesonly=true count min(_time) as first
   max(_time) as last from datamodel=<Model> where index=<I>` per model in `ACCEL_MODELS`
   (the six models the setup app accelerates — runbook stage 3). The probe returns the window
   the model's summaries actually hold for that index, measured rather than assumed from
   `-10y`. A model is a rung-1 candidate only when the searched range lies inside it
   (`coverage_label`).
2. **Accelerated aggregate.** For each candidate, `tstats summariesonly=true count from
   datamodel=<Model> where index=<I> by host _time span=<w>s` over the searched range. Non-empty
   buckets are the same `LocalWindow` rows rung 2 produces; the receipt says
   `mechanism=accelerated`, `coverage=accelerated`, `model`, `accel_window=<summary window>`.
3. **Fallback.** A range outside every window, a model that covers the index but returns no
   buckets for the source, or a failed probe all fall through to rung 2's index aggregate
   unchanged. The receipt says `mechanism=indexed`, `coverage=scan` and still records
   `accel_window` (the window that was found, if any), so a partial-coverage read is visibly
   partial and never reported as `empty`.

The read itself stays rung 3 (`read_anchors`, `rung=narrowed_scan`, `coverage=scan`); rung 1
only changes how the where/when windows were obtained. The source receipt now carries the
`accel_window` that localised it; the stage receipt's `localisation.indexes[*]` carries
`mechanism`, `model`, `coverage`, `accel_window` and the probe notes.

## 2. Acceptance properties and their proofs

| property | proof |
|---|---|
| a model covering the whole range localises from its summary, with no rung-2 scan | `tests/unit/test_hunt_notables_sample.py::test_a_model_covering_the_range_localises_from_its_summary_not_a_scan` |
| a range outside the acceleration window is localised by a scan, labelled `scan`, window recorded, result not empty | `tests/unit/test_hunt_notables_sample.py::test_a_range_outside_the_acceleration_window_is_localised_by_a_scan_not_empty` |
| the localisation receipt records mechanism, coverage and `accel_window` | `tests/unit/test_hunt_notables_behaviours.py::test_the_localisation_receipt_carries_the_window_a_range_outside_it_is_a_scan` |
| no build-family regression (rungs 2–3 decide exactly as before) | the rungs 2–3 suite unchanged and green: `test_read_mode_reads_whole_only_below_the_wide_source_ceiling`, `test_twenty_minute_burst_is_selected_by_five_minutes_and_missed_by_four_hours`, `test_narrowed_scan_reads_one_host_window_and_reports_events_scanned`, `test_collect_behaviours_keeps_s2_value_spans_when_localisation_finds_nothing` |

Net test lines: **+72 / −5** (`test_hunt_notables_sample.py` +46/−5, one test replaced by two;
`test_hunt_notables_behaviours.py` +26). Net +2 tests, no new test file.

## 3. What is unproven and only the live run can settle

- **The probe query.** `min(_time)`/`max(_time)` with `from datamodel=` is reasoned from
  `tstats`' documented aggregation over summaries, not observed on this Splunk build. If it is
  rejected, every probe records `accel:<Model>:read_failed…` in `localisation.notes` and the
  ladder falls back to rung 2 — the run still works, but rung 1 never fires.
- **`where index=<I>` inside `from datamodel=`.** Reasoned from tstats' `where` filter;
  unmeasured. Same fallback note if accepted-but-empty.
- **`host` in a data-model `by` list.** CIM models inherit `host`; the summary must carry it for
  `by host _time span=` to answer. Unmeasured on this build.
- **Coverage/window semantics.** The recorded `accel_window` is the summary's event coverage
  (min/max of `summariesonly=true` counts), not `acceleration.earliest_time` from
  `datamodels.conf`. It is the stricter of the two: a range the summary cannot answer is called
  a scan.
- **Cost.** The probe is one summary read per model per index (6–7 requests, ~0.1 s each by the
  runbook's measurement); the accelerated aggregate is one more. No live timing here.
- **Rung 1 on `botsv2`.** Not expected to fire: the CIM allowlist excludes it (runbook stage 1).
  The six probes should return 0 rows and the run should report `mechanism=indexed`,
  `coverage=scan`, `keys_reachable` still 8/24.

## 4. Orchestrator live proof (after stage 3/4)

```bash
cd /Users/chris/projects/portal-5 && ./launch.sh rebuild && ./launch.sh up
run_dir=$(mktemp -d "$PWD/coding_task/scratch/s6-rung1.XXXXXXXX")
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out "$run_dir/santos" --stage all --family santos
jq '.stages.behaviours.localisation' "$run_dir/santos/progress.json"
jq -r '.stages.behaviours.receipts[]
  | [.source_id,.read_mode,.rung,.coverage,.accel_window,.events_scanned] | @tsv' \
  "$run_dir/santos/progress.json" | head
```

Worked: `localisation.indexes[0]` shows `"mechanism": "accelerated"`, `"model"` one of the six,
`"coverage": "accelerated"`, a non-null `"accel_window"`, `windows > 0`, and the wide sources'
receipts show `read_mode=anchored`, `rung=narrowed_scan`, a non-null `accel_window` nested under
the same window. Not worked: `mechanism: "indexed"` with `accel_window: null` (no model covers
the index — check stage 3), or `mechanism: "accelerated"` with `windows: 0` (the model covers
the index but not the source's events), or `notes` carrying `accel:<Model>:read_failed…`
(the probe query is wrong for this build). The same run against the un-promoted
`hb_ait_santos` is the negative control: the CIM allowlist covers only `_v2`, so it must report
`mechanism=indexed`, `coverage=scan`, `accel_window=null` and still localise by the index
aggregate. Then the unchanged botsv2 ceiling run:

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out "$run_dir/botsv2" --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out "$run_dir" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl"
```

Expected: `keys_reachable` still `8/24` with a per-step `cause`, every read carries
`events_scanned`, and `localisation.indexes[0].mechanism == "indexed"` (botsv2 is the untuned
control). A `keys_reachable` rise here is *not* expected from rung 1 alone.

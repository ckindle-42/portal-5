# FINDING — hunt replan slice E6 (the estate-map reader)

Lane `lane/hunt-e6`, brief `coding_task/BRIEF_HUNT_E6.md`, spec
`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §3 (D0) and §6 (E6). Offline only: no Splunk, no
`launch.sh`, no `.env`, held-out indexes (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) never
opened. The proof reads the stored Round-2 runs and their keys on disk.

## What the slice changed

`portal/modules/security/core/hunt/notables/scoreboard.py`, `_index_paths`:

- **The shape guard is gone.** The reader no longer requires `len(/ -cells) == row["rows"]`.
  With a two-field `by sourcetype source` query each tuple row contributes exactly one path, so
  the counts matched; with three fields (`by sourcetype source host`) a path occurs once per host.
  The ledger stores a **deduplicated union of every cell** (`run.py:_extracted_values`), so a
  distinct-path count can never equal a row count. The reader now unions the `/`-cells of every
  uncapped matching row, which covers both shapes (`by sourcetype source` is a substring of
  `by sourcetype source host`).
- **The guard is now a real completeness test.** The path set must contain a path for every
  source the run's own `sources.json` declares (cards' `facts.sources`, the same set
  `_run_index` already builds). A capped row is still skipped, and a run with no ledger, no
  declared sources, no matching row, or a declared source missing from the map is still rejected
  (`index_map` = the reason, `evidence_absent` = `null`).

`tests/unit/test_hunt_scoreboard.py` — three tests, one per acceptance property:

- `test_the_estate_map_reads_a_three_field_sourcetype_source_host_row`
- `test_a_capped_estate_map_row_is_still_rejected`
- `test_a_complete_map_that_misses_a_declared_source_is_rejected`

Net test lines: **+81** in the file (three tests plus a 14-line `_estate_map` helper that writes the
three-field ledger row).

## Offline proof over the stored Round-2 runs

Command, per family (`<fam>` ∈ `santos`, `russell`, `kyoushi`; key corpus selected per family):

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r2_<fam>/v2/<fam> \
  --keys <fam>=<keys.jsonl for that family>
```

Keys: santos `/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl`,
russell `/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl`,
kyoushi `/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl`.

Observed output (full lines from the scoreboard):

```
===== santos
C0 ceiling  steps 11/20 reachable  labelled lines read verbatim 3353/47367
C0 evidence absent (excluded from the step denominator)  crack_passwords 44/44 labelled lines
C0 recall-of-reachable  line @50 6/11  @100 6/11  all 11/11
===== russell
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 3010/61862
C0 evidence absent (excluded from the step denominator)  crack_passwords 49/49 labelled lines
C0 recall-of-reachable  line @50 6/11  @100 9/11  all 9/11
===== kyoushi
C0 ceiling  steps 7/12 reachable  labelled lines read verbatim 287/408038
C0 recall-of-reachable  line @50 6/7  @100 7/7  all 7/7
```

`santos` before the change (same command, old reader) printed
`C0 ceiling  steps 11/21 …` and `C0 evidence absent  n/a (the run recorded no complete per-source
index map)` — i.e. 44 labelled crack lines counted against the denominator that no index can
reach. After the change the same run prints `44/44` and steps `11/20`.

The JSON block behind those lines (from `score(...)` directly):

| family | index map | evidence_absent | steps |
|---|---|---|---:|
| santos | `ledger estate map, 89 source paths` | `[{"step": "crack_passwords", "absent": 44, "lines": 44}]` | 20 of 21 |
| russell | `ledger estate map, 91 source paths` | `[{"step": "crack_passwords", "absent": 49, "lines": 49}]` | 21 of 22 |
| kyoushi | `ledger estate map, 80 source paths` | `[]` (map accepted, no absent step) | 12 of 12 |

Independent check that the declared set is exactly what the estate map holds (so the new guard is
a completeness test, not a loosened one): on all three runs the union of `sources.json`
`cards[].facts.sources` equals the `/`-cell union of the matching ledger row — santos 89 = 89,
russell 91 = 91, kyoushi 80 = 80, zero missing and zero extra.

## Not done here

- No live Splunk run and no fresh hunt: the proof re-scores the stored Round-2 runs unchanged.
  E6's live matrix row (`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §7, D3) is the orchestrator's.
- The kyoushi block prints no `C0 evidence absent` line because `evidence_absent` is `[]`; that
  is the existing render contract for "map accepted, no absent step", unchanged by this slice.

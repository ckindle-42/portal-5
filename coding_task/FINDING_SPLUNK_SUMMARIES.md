# FINDING — the CIM summaries never built because the corpus was never re-ingested (2026-11-21)

Lane: `lane/splunk-summaries`. Brief: `coding_task/BRIEF_SPLUNK_SUMMARIES.md`.
Live diagnosis against the lab (10.0.1.30, Splunk 10.2.5) with only the five named
`LAB_SPLUNK_*` keys exported from `.env`; SSH (read-only, then `apply`/`reindex`) through
`host.py`'s own transport.

## Root cause (the box's own receipts, quoted)

The summaries were not failing to build. **There was no data to summarize.** The D6 rebuild
sequence deletes the `_v2` indexes and re-ships the corpus — but nothing recreates the index
between the `DELETE` and the reship, and `reindex --ship` did not check that its target existed.
On 2026-11-21, at 09:30:09 UTC, the three indexes were deleted; 28 seconds later the reship
started, and HEC accepted every batch while the indexer threw it all away:

```
11-21-2026 09:30:09.048 INFO  IndexProcessor - idx=hb_ait_santos_v2 Removing; IP::deleteIndex
11-21-2026 09:30:09.048 INFO  IndexProcessor - idx=hb_ait_santos_v2 Deletion approved, start dir removal
11-21-2026 09:30:37.131 WARN  IndexerService - Received event for unconfigured/disabled/deleted
    index=hb_ait_santos_v2 with source="source::/apache2/error.log" host="host::cloud_share"
    sourcetype="sourcetype::apache:error". Dropping them as lastChanceIndex setting in
    indexes.conf is not configured. So far received events from 1 missing index(es).
```

`index=_internal component=IndexerService "Received event for unconfigured/disabled/deleted
index"` counts **3 warnings, one per `_v2` index, 09:30:37 → 09:38:10 UTC** — the whole reship
(7,260,795 events) went into the void, while the ship receipts read `shipped == expected`
because HEC 200-acks a batch for an index the box no longer has. **A receipt can never prove
landing; only the live index can.** (The first, 03:34 UTC reship did land, but its data was
deleted again at 03:51:59 by the same sequence's `DELETE` — `ConfigChange` log:
`indexes.conf stanza hb_ait_santos_v2 … deleted=true … 03:51:59.335`.)

Everything the brief listed as "working but mysteriously not building" was genuinely healthy
and simply had an empty substrate:

| candidate from the brief | live answer |
|---|---|
| macro/index allow-lists after the D6 apply | `cim_*_indexes` parser expansion names all three `_v2` indexes (verify `ok`) |
| acceleration time range vs event `_time` | six models report `enabled` over `-10y` (verify `ok`); events are 2021–2022, inside the window |
| `_ACCELERATE_` search errors | scheduler says `status=success, result_count=0, run_time≈3s` every 10 min — a base search over three indexes that do not exist scans nothing and fails nothing |
| permissions/sharing of the models | models live in `Splunk_SA_CIM`, tags/eventtypes are `export = system` (stage-5 fix), reachable as `nobody` |
| `summaries_complete` check itself | correct: the summarization REST really did report `complete=0 size=0` — the property, not a parse artefact |

Decisive evidence the indexes were gone (not merely empty): `/services/data/indexes?count=-1`
lists **no `_v2` index at all**; `dbinspect` returns no buckets; the container filesystem has
no `$SPLUNK_DB/hb_*_v2` directories; the `per_index_thruput` series for the `_v2` names go
silent after 09:41.

## Second defect found, reported not fixed: the KV store is down

`/services/kvstore/status` answers `"status": "failed"`, and mongod dies at every start:

```
WiredTiger file version: this build only supports versions up to 4, and the file is
version 5: WT_ERROR: non-specific WiredTiger error
Fatal Assertion 28595 at wiredtiger_kv_engine.cpp 928
```

That breaks `Splunk_Security_Essentials` (3.8.3, enabled)'s global automatic lookup —
`props.conf` line 2 applies `LOOKUP-splunk_security_essentials` (a KV-store lookup) to every
sourcetype — so every search logs `Could not load lookup=LOOKUP-splunk_security_essentials`
(`splunk_search_messages`: 13,002 since 02:44 UTC) and `summary.last_error` carries it. **It is
not what kept the summaries empty**: after the repair below, the summaries build with the
message still present (measured: `datamodel_summary` tsidx grew to tens of MB per index while
`summary.last_error` still named the lookup). The KV store repair (WiredTiger format vs
binary mismatch, from the Splunk upgrade) is an operator decision — `splunk migrate kvstore`
cannot upgrade a store that is *newer* than its binary; the options are re-upgrading Splunk to
the version that wrote the files or clearing `kvstore/` (SSE demo content only, nothing of this
lab's own) — left to the orchestrator.

## The fix

1. **`scripts/lab/splunk_setup/cli.py`** — `cmd_reindex --ship` now constructs the REST client
   for every ship (not only the duplicate-guard branch) and calls `_require_target_index`,
   which refuses to ship into an index the box does not have:
   `"hb_ait_santos_v2 does not exist on the box — run 'apply' first: a DELETE is not undone by
   shipping, and every event sent to a missing index is dropped on arrival"`. The guard runs
   on `--ship` and `--resume`, before the first HEC post; `--force` skips only the
   already-holds-events check, never the existence check.
2. **`docs/hunt/SPLUNK_SETUP_RUNBOOK.md`** — the two rebuild recipes that told the operator to
   `DELETE` then reship with no `apply` in between are corrected (the stage-2 fail-if note and
   the stage-2 rollback), with the measured incident (7,260,795 events, HEC 200 + IndexerService
   drops, 09:30:37–09:38:10 UTC) as the reason.
3. The live lab was repaired **through the fixed tooling**:
   `apply --no-restart` (recreated the three indexes; macros already matched; HEC token allows
   all indexes) → `reindex --ship` ×3 → the `*/10` accelerate cron rebuilt the summaries.

## The repair's receipts

- `reindex --ship` guard passed (indexes exist) and shipped:
  **santos 2,573,164 / kyoushi 2,425,851 / russell 2,261,780** (`shipped == expected`).
- Live readback, not the receipt: `| eventcount summarize=false` answers
  **hb_ait_santos_v2 2,573,164 / hb_kyoushi_s1_v2 2,425,851 / hb_ait_russellmitchell_v2
  2,261,780** — the exact D6 totals, on the box this time.
- The first post-repair accelerate tick (15:10 UTC) did real work:
  `Authentication 14.6s result_count=5`, `Network_Traffic 45.5s result_count=9`,
  `Network_Resolution 34.7s`, `Web 27.2s`, `Intrusion_Detection 18.2s` — versus
  `run_time≈3s result_count=0` on every tick for the previous 11 hours.
- Summary tsidx on disk (`$SPLUNK_DB/<index>/datamodel_summary/`): santos 81 MB, kyoushi 80 MB,
  russell building — the summaries had never had a single byte to write before this.

## Verify (the live lab)

`splunk_setup verify` (default, all 14 rows) after the `*/10` cron completed the backfill
(15:26:32 UTC poll: `complete 6/6`, sizes Authentication 2,572,288 / Endpoint 12,288 /
Intrusion_Detection 8,269,824 / Network_Resolution 43,540,480 / Network_Traffic 94,502,912 /
Web 49,090,560 bytes):

```
summaries_complete  ok  "complete 6/6; size {Authentication: 2572288, Endpoint: 12288,
  Intrusion_Detection: 8269824, Network_Resolution: 43540480, Network_Traffic: 94502912,
  Web: 49090560}"
… all 13 other rows ok (macros, acceleration_window -10y on 6 models, summary_index ×3,
  control probes ×3)
EXIT=0    # 14/14, versus 13/14 before the lane
```

## Adjacent defects found while proving it — reported, not fixed (other lanes' live proof)

`verify --index santos --accelerate` (extra, not part of the 14) reads 20/28; the three
real items behind it:

1. **The reship ran under pre-D6 index-time conf.** The D6 app *files* were only installed by
   this lane's 15:01 `apply --no-restart`; the running indexer still held the pre-D6
   transforms, so the fresh `_v2` tsidx lacks `auid` (`auid_indexed` rows=0, scan=24042).
   Baking it in needs the D6 finding's own orchestrator rebuild: restart (loads the
   now-installed D6 transforms), delete + recreate + reship. `user_clean` passes either way
   (the JSON-shaped shipper copies were routed out at plan time, so the old regex never sees
   them).
2. **`service_log_absent` can never pass on live Splunk as written** (`plan.py`): its tstats has
   no `by`, and live tstats answers a no-match bare `count` with one row `count=0` (measured:
   `[{"count": "0"}]` — the property holds; the probe counts rows and `max_rows=0` fails it).
   Needs the count read, not the row count.
3. **`rest.datamodel_acceleration` cannot parse this version's model endpoint** (`rest.py`):
   Splunk 10.2.5 returns `acceleration` as a JSON *string*
   (`{"enabled":true,"earliest_time":"-10y",...}`), and the parser handles only a dict or flat
   `acceleration.*` keys, so every `acceleration:<Model>` row false-fails with
   `reports enabled=False ?`. The acceleration is in fact enabled over `-10y` — the default
   verify's `acceleration_window` row (the `/data/models` endpoint) proves it, and so does the
   raw endpoint quoted above.

None of the three touches `summaries_complete`, which is the property this lane was asked to
make pass.


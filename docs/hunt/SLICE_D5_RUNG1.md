# Slice D5 — rung 1 fires: the summarization payload's own keys, and a covering window

Replan slice D5 of `ORCACYBER_DEEP_DIVE_2.md` §5 (root cause RC7 in §3.7). Code:
`portal/modules/security/core/hunt/notables/inventory.py`, tests `tests/unit/test_hunt_inventory.py`.

## The property

`accelerated` is non-empty whenever a complete summary covers the window, and rung 1 (the
accelerated aggregate) is chosen before rung 2 (the indexed-field aggregate) when it answers.
A model is kept only if its `summary.earliest/latest` covers the range the lists describe.

## What changed

- `ACCEL_QUERY` no longer names `datamodel_name`, which the endpoint does not have, and no
  longer carries a `| fields` list — one unknown name there empties the answer. It reads the
  whole payload: `| rest /services/admin/summarization by_tstats=1`.
- The accelerator is mapped from `title`/`summary.id` — `tstats:DM_<app>_<Model>` and
  `DM_<app>_<Model>` both resolve to `<Model>`, the name `from datamodel=` accepts. Child
  accelerators (`DM_…_Endpoint.Processes`) are not model roots and are dropped.
- A model is kept only when `summary.complete = 1` **and** its window covers the cards' own
  event span (`_span`). The span is the cards' `first`/`last`, not the query's all-time bound:
  the stored runs carry `sources.start = 0.0`, `end = <now>`, which no summary can cover. The
  reported window is whole seconds, so the comparison admits a sub-second tail (`_covers`).
- `_enumerate_fields` asks rung 1 first for every selected field, whatever the indexed route
  would answer, and falls through to `tstats`/`stats` only when no model answers. The record
  names the mechanism `accelerated` (was `datamodel`), with `events_scope: summary`,
  `accel_window`, `searched_window`, `events_scanned` and `seconds`; a capped accelerated list
  takes D3's tail read through the model as well.
- `INVENTORY_ACCEL_MIN_EVENTS` (250 k) is gone: it gated rung 1 on source size, which kept
  rung 1 unreachable for every narrow source — the case the slice's live proof names.

## Measured, read-only against the lab index `hb_ait_santos_v2`

Job API, basic auth from the live checkout's `.env` by key name (never sourced), training
index only, nothing written to the lab:

```
| rest /services/admin/summarization by_tstats=1
  -> 10 rows; fields include title, summary.id, summary.complete,
     summary.earliest_time, summary.latest_time; no datamodel_name
  -> 6 model roots complete, window 1616425561 .. 1643094189

| rest ... | fields datamodel_name summary.complete      (the old query)
  -> 6 rows with summary.complete only: every model was skipped, accelerated: []

_Prober(...).accelerated()   (span 1616425561 .. 1642487481)
  -> Authentication, Endpoint, Intrusion_Detection, Network_Resolution,
     Network_Traffic, Web; 1 query, 0 failures
_Prober(...).accelerated()   (span 1616425561 .. 1794203043)
  -> []                                     (the control index's stray 2026 event)
```

One list through rung 1, real cards, real window — the stored `linux_secure` card with the
estate's `user` field:

```
queries: 2 name probes + 1 rest probe + 1 model aggregate   (no field probe, no scan)
| tstats summariesonly=true count min(_time) as first max(_time) as last
  from datamodel=Authentication where index="hb_ait_santos_v2"
  sourcetype="linux_secure" by Authentication.user
  | eventstats count as inventory_distinct | sort 0 -count | head 5001
-> status complete  mechanism accelerated  events_scope summary
   events_scanned 896  seconds 0.30-0.40
   values root ait www-data gmorgan cscott unknown
```

`user` **is** indexed on that sourcetype (`| tstats count … sourcetype="linux_secure" by user`
answers over 9,864 scanned events), so pre-change the same field would have taken the `tstats`
route — and that route's values are the RC10 blob (`ait","@version":"1","log":{…`). The
accelerated list is clean. That bonus is observed, not the slice's target; the reason the
summary's `user` differs from the indexed field was not established.

## Cost — the finding of this slice

Running the whole `collect_inventory` stage on the stored santos `_v2` cards, post-merge with
D3 and **before D2 merged**, read-only:

```
228 searches + 57 probes = 285 queries, 88.0 s of server time, 99.9 s wall
model_probes 192          (6 models x 32 selected fields)
mechanisms  stats 24, tstats 8, accelerated 0
accelerated 6 model roots
stored run, same stage, pre-change: 35 searches, 57 probes, 49.6 s wall, model_probes 0
```

So rung 1 tried before rung 2 doubles the stage's wall time and multiplies its searches by 6.5
on this corpus, for **zero** answered lists — because the stored cards' field names are parser
slots (`template`, `program`, `v1..v6`), which is D2's defect, not this one. Against the whole
run (785 searches on santos `_v2`) the increase is +24 %.

That receipt predates D2's merge: D2 replaces the parse-slot selection with the estate's
41-name vocabulary and one presence probe per source, so a re-run on the merged tree selects
different fields and pays a different rung-1 cost. The direction is unchanged — one blind model
aggregate per selected field before the indexed probe — and the receipt above must be re-taken
to price it; this slice's own proof (a covering summary answered first, on a real card whose
field is indexed) does not depend on the selection.

A cheap mitigation exists and was proved with three queries, not implemented here (out of this
slice's files): the summary answers `by sourcetype`, so one probe per model gives the
sourcetype→model map and would replace 192 blind probes with ~6 + one per field.

```
| tstats summariesonly=true count from datamodel=Authentication where index=hb_ait_santos_v2
  by sourcetype  -> linux_audit 1, linux_secure 896, syslog 1839
| ... from datamodel=Web ...        -> suricata 7819
| ... from datamodel=Intrusion_Detection ... -> suricata 50028
```

## Deviation from the slice text, stated

The build says "record `mechanism: accelerated`, `scanCount`, `seconds`". `scanCount` is a
Splunk job-content field the hunt never carries: `HuntExecutor.Read` holds rows only, and the
job content is discarded in `_collect`. The record carries the project's existing
`events_scanned` (the aggregate's matched total; for the list above it is 896, which happened to
equal that job's `scanCount` of 896) plus `events_scope: summary` and `seconds`. A real
`scanCount` needs a transport change in `executor.py`/`window.py`, outside this slice.

## What a live run should show

`inventory.accelerated` = the six complete model roots, `model_probes > 0`, at least one field
record with `mechanism: accelerated` and `events_scope: summary`, and the CIM list for the
source's user field complete — on a card whose field selection (D2) selects an estate name.

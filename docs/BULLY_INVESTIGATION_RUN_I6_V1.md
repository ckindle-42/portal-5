# BULLY_INVESTIGATION_RUN_I6_V1.md


> **Errata (2026-08-21, `TASK_BULLY_FULL_ASSEMBLY_V1` F.0):** this run exercised 5/16 of the bully modules over 213,311 records (0.076% of the 281,069,416-record corpus) and is a partial assembly at proxy scale (see `docs/DESIGN_BULLY_FULL_ASSEMBLY_V1.md`); its findings describe that subset, not the system.
Live run of the anchor-pivot investigation engine (I.1-I.5) against real
BOTS data. Raw output: `BULLY_INVESTIGATION_RUN_I6_V1.json`, produced by
`scripts/bully_investigation_run_i6.py`.

## Discovered index time ranges

`| tstats min(_time) max(_time)`, live against the installed corpus:

| index | earliest | latest |
|---|---|---|
| botsv1 | 1470009600.0 (2016-08-01) | 1472450339.0 (2016-08-29) |
| botsv2 | 1501545600.0 (2017-08-01) | 1504223999.0 (2017-08-31) |
| botsv3 | 1534737603.0 (2018-08-20) | 1568916650.0 (2019-09-19, later index residue -- the scenario itself is the single day at the start of this range) |

Every investigation and every planned cousin in this run was clamped to its
own dataset's real discovered range (I5), never an assumed one.

## Five live-fidelity bugs found and fixed while building this run

Getting one honest, working live run surfaced five real defects, each
committed ahead of this report with its own seeded regression test:

1. **`_time` silently corrupted to "now".** This lab's Splunk renders
   `_time` as a locale string (`"2018-08-20 15:17:58.000 GMT"`), not an
   epoch; `SplunkBackend._run_search`'s `float(_time_raw)` raised and fell
   back to `time.time()` for every ordinary `search`-based capture. Fixed
   by requesting `time_format=%s` in the export request.
2. **Fields not extracted unless referenced in the search.** This lab only
   surfaces a field (e.g. `EventCode`) in the exported JSON when the search
   string itself names it. Fixed by having `_dig` fall back to parsing
   `_raw`'s line-oriented `key=value` text.
3. **A single bounded query's own result could exceed `MAX_EVENTS`** in one
   round trip (one query returned 26k+ rows against a 20k cap) --
   `max_queries` stopping was not the same as `max_events` bounding what
   was actually read. Fixed by trimming the batch itself.
4. **Cousins shipped under a synthetic host, not their real
   `anchor_entity`.** I.4 added `CousinSpec.anchor_entity` so a cousin is
   reachable by a pivot, but `inject_cousins` ignored it, always shipping
   under `corpus-cousin-<id>`. Fixed to ship under the real entity.
5. **Entity-scoped SPL matched by free text only.** A bare keyword phrase
   searches `_raw`'s tokenized text, which finds an entity a real schema
   embeds inline (a hostname inside Windows message text) but not one that
   lives only in Splunk's `host` metadata field -- exactly the shape of an
   injected cousin. Fixed by also matching `host="<entity>"` explicitly.
6. **`_dig` needed to parse a JSON-shaped `_raw`, not just `key=value`
   text.** An injected cousin's JSON body, shipped under a real sourcetype
   whose own extraction rules expect a different wire format
   (`wineventlog:security`'s classic-text rules), never gets HEC's
   automatic JSON field extraction -- the JSON sits untouched in `_raw`.
   Without this, 0/20 cousins registered as recovered even though they
   were genuinely present and reachable. Fixed by parsing a JSON-shaped
   `_raw` directly.

Bugs 4-6 were found specifically by trying to measure real cousin
recovery -- each one, uncaught, would have silently reported a 0%
`product_cousin_recall` that looked exactly like a genuine discovery
failure rather than a plumbing gap. That is the same shape of mistake this
task's own errata (I.0) calls out in T.3.

## Investigations run

One data-intrinsic anchor and one truth-targeted anchor per answer-key
technique -- every anchor entity real, none fabricated:

| anchor | provenance | dataset | queries | events | entities | sourcetypes | span (s) | reach_recall |
|---|---|---|---|---|---|---|---|---|
| a-discovered-failed-logon | discovered | botsv3 | 1 | 20000 | 1 | 13 | 1234 | -- |
| a-truth-T1558.004 | truth_targeted | botsv3 | 1 | 24 | 1 | 5 | 1500 | 1.0 |
| a-truth-T1071.001 | truth_targeted | botsv3 | 1 | 16 | 1 | 3 | 1500 | 1.0 |
| a-truth-T1496 | truth_targeted | botsv2 | 1 | 20000 | 4 | 20 | 11736 | 1.0 |
| a-truth-T1190 | truth_targeted | botsv1 | 1 | 20000 | 2 | 10 | 14662 | 1.0 |

- **`a-discovered-failed-logon`**: a real repeated-failed-logon event
  (`EventCode 4625`, host `MKRAEUS-L`, 2018-08-20 11:57:01 UTC), found
  directly in the corpus, not looked up from an answer key.
- **The four truth-targeted anchors** are each a real host discovered
  live from that technique's own real sourcetype in its own dataset
  (`_DISCOVERED_ANCHORS` in the run script) -- e.g. T1071.001 (C2 over
  HTTP) anchored on `gacrux.i-0920036c8ca91e501`, drawn from genuine
  `stream:http` traffic in botsv3.
- **`reach_recall 1.0`** for every truth-targeted anchor: the reconstructed
  investigation reached the technique's own real entity. This run's
  `BOTS_ANSWER_KEY` entries carry a single entity each (not a documented
  multi-stage pivot chain), so this is a narrower floor measurement than
  I.1's synthetic BOTSv3-shaped fixture (which reconstructed a five-entity
  chain with `reach_recall 1.0`); extending the answer key with real
  multi-entity stage chains is the natural next step (residual risk).
- **Why the wide-window investigations hit `max_events` on the very first
  query**: `PivotQuery.to_intent()` scopes an entity as a full-text-or-host
  term, which against real, noisy telemetry matched far more broadly than
  a single host's own activity (background records mentioning the
  hostname, or coincidentally hosted on it). This is the "pivot explosion"
  risk this task's design anticipated for a high-degree entity, now
  confirmed live.

## Throughput: bounded queries vs. the T.3 scan figure

| | records/sec |
|---|---|
| **This run (bounded, entity-scoped, no `head`)** | **950** |
| T.3 (`earliest=0 \| head`, unbounded scan truncated) | 53 |

**~18x faster**, on the same lab hardware, over genuinely different data
(bounded queries reach further per second because Splunk's own time-bucket
pruning -- exactly what `earliest=0` defeated -- is finally in play).

## Classifier coverage (real captured records, this run)

- `n_records 60040`, `n_classified 24550`, **coverage 0.4089**
- `class_entropy_bits 1.85` -- **not degenerate**
- **`concentrated: true`** -- no single class exceeds the 0.40 class-share
  ceiling (`c2_exfil` is highest at 0.36), but seven classes are 100%
  single-sourced in this capture window (`auth`/`collect`/`escalate`/
  `execute` all only from `WinEventLog`; `evade` only from
  `symantec:ep:agent:file`; `lateral` only from `stream:smb`; `persist`
  only from `WinRegistry`) -- exactly what the source-concentration check
  exists to surface.
- `unmapped_sourcetypes` (19): `Perfmon:*` (7 variants), `PerfmonMk:Process`,
  `MSAD:NT6:*` (2), `stream:dhcp`, `stream:igmp`, `stream:ip`, `suricata`,
  `symantec:ep:packet:file`, `symantec:ep:traffic:file`,
  `wineventlog:security` (lowercase -- `WinEventLog` is this lab's real
  naming, a live naming-variant gap), `xmlwineventlog` (bare, no `:sysmon`
  suffix), `xmlwineventlog:sysmon`.

## `inference_report` -- the universal path, no table consulted

```json
{
  "actions_profiled": 14,
  "schemas_seen": 2,
  "classes_inferred": 4,
  "cross_schema_classes": 1,
  "cross_schema_fraction": 0.25,
  "largest_class_members": 10
}
```

**Honest limitation (I9):** this run's `action_of` extractor reads
`EventCode`/`event_type` only, so most of the captured sourcetypes
(`Perfmon:*`, `stream:*`, `WinRegistry`, ...) were never profiled at all --
`schemas_seen: 2` badly undercounts the 20+ real sourcetypes this run
actually read. `behavior_inference`'s clustering itself is unchanged and
still table-free; widening `action_of` to cover more real per-sourcetype
action fields (a `query`/`answer` field for DNS, a registry-path field for
`WinRegistry`, ...) is the direct next step for a representative
`cross_schema_fraction`, tracked as a residual risk rather than worked
around in this run.

## Cousins: planted inside each technique's real range, under real anchor_entity, and RECOVERED

`plan_cousins` produced **20 cousins** (4 `BOTS_ANSWER_KEY` entries x 5
transformations), each `injected_at` inside its own dataset's real range
(none at "now" -- the T.3 defect this task closes), each shipped under its
technique's real, live-discovered `anchor_entity` host (bugs 4-6 above).

**Per-transformation recovery -- pivoting from the same real entity the
cousin was shipped under:**

| transformation | reached | total |
|---|---|---|
| REVOCABULARY | 4 | 4 |
| RESCHEMA | 4 | 4 |
| REIDENTITY | 4 | 4 |
| **SCATTER** | **4** | **4** |
| REORDER_MINOR | 4 | 4 |

**20/20 (100%) recovered**, including SCATTER -- a cousin whose spine is
split across several real sourcetypes and identities, the transformation
this task specifically called out for special attention.

## Scoreboard (I.4-standard correctness axis)

```json
{
  "hunt_id": "i6-live-investigation-run",
  "n_records": 20,
  "catch_count": 20,
  "catch_rate": 1.0,
  "trust_mean_rank": 2.0,
  "false_flag_count": 0
}
```

Ground truth is known here (this run planted every scored cousin itself):
`relationship=SAME`/`candidate_state=PROMOTED` when a live investigation
pivoting from the cousin's own real anchor_entity found that cousin's
`cousin_id`, `DIFFERENT`/`KILLED` otherwise (none, this run).
`known_benign=False` throughout, so `false_flag_count` is structurally 0 --
this scoreboard measures cousin recovery, not background false-positive
rate (full provenance published in `correctness_axis_provenance`).

## `bed_report`

```json
{
  "records_available": {"botsv3": 2030370},
  "records_read": 213311,
  "is_haystack": true,
  "reasons": [
    "partial_read:213311/2030370 -- a capped read of a real corpus biases every downstream statistic toward whatever the cap selected",
    "scored_sample_too_small:0<10000 -- recall/FP figures computed on this scored population do not generalise"
  ]
}
```

## Comparison against the exit criteria

| criterion | this run |
|---|---|
| Every corpus query time-bounded and entity-scoped; `earliest=0` raises | yes (I.2, live-verified) |
| Investigations reconstruct chains from symptom anchors, `reach_report` as floor | yes -- `reach_recall 1.0` x4, single-entity floor (see residual risks) |
| Cousins inside corpus time range, reachable by pivot | yes -- 20/20 recovered, 0 refused |
| Throughput published beside scan figure | yes -- 950 vs 53 rec/sec |
| Classifier health fails on concentration, not just entropy | yes -- `concentrated: true`, entropy alone said healthy |
| Every investigation publishes bounds and truncation state | yes |
| Behaviour inferred, not looked up; `cross_schema_fraction` published | yes -- 0.25, with the extractor's own coverage gap reported alongside |
| No discovery path touches a curated table or an answer key | enforced structurally (I.1b's `infer_behaviors` takes no curated input); I.7 adds the import-scan proof |
| Unreadable fraction published beside every recall figure | yes -- 19 unmapped sourcetypes listed beside 0.4089 coverage |

## Residual risks surfaced by this live run

- **`BOTS_ANSWER_KEY` needs real multi-entity stage chains** to measure
  `reach_report` the way I.1's synthetic fixture does (pivot depth actually
  exercised); this run's entries are single-entity, so `reach_recall 1.0`
  here is a narrower claim than I.1's.
- **`behavior_inference`'s `action_of` needs broader real per-sourcetype
  field coverage** to profile schemas beyond Windows EventCodes.
- **Several real naming variants remain unmapped**: `xmlwineventlog` (bare),
  `wineventlog:security` (lowercase, vs. this lab's real `WinEventLog`),
  `suricata` (deliberately unmapped per I.5 unless a confident category is
  present -- none were in this window).
- **Entity-substring/host matching over-matches on real data**, exhausting
  the event budget on one broad query before recursion can run for a
  high-degree entity -- confirmed live, matching the task's own anticipated
  "pivot explosion" risk.

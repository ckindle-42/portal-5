# DESIGN_BULLY_INVESTIGATION_V1.md

## The defect this replaces

Every capture to date (`inject_plane.capture_records`, `live_connect.
_search_from_intent`) issues:

```
search index=X | head {limit}
"earliest": intent.start if intent.start is not None else "0"
"latest":   intent.end   if intent.end   is not None else "now"
```

`earliest=0`/`latest=now` asks Splunk for the entire index across all time,
then `| head {limit}` discards everything past the first bucket returned.
Measured live against `botsv1` (T.3): **53 records/sec**, ~61 days to touch
the corpus once. That number describes an unbounded scan truncated by `head`,
not the pipeline -- it is simultaneously too broad (asks for 226M+ events)
and too narrow (what survives is one arbitrary slab with no investigative
structure: no anchor, no window, no pivot).

## How defenders actually reconstruct an incident

- **The anchor is where you start searching, not where the incident
  started.** Incidents surface at the symptom stage (a coin-miner alert, a
  public bucket, anomalous egress); the investigator works BACKWARD from
  visible damage toward initial access.
- **Expansion is bidirectional and asymmetric.** Backward pivots reveal
  delivery/auth/staging/parent-process; forward pivots reveal execution/
  persistence/lateral movement/exfil. A documented SOC pattern: all activity
  by this user in the preceding 24h, and in the superseding 1h -- backward
  reaches further than forward.
- **Pivoting is recursive across entities** -- IP -> process -> parent
  process -> user -> login time -- each query's results feeding the next.
  This is what links stages sharing no identifier.
- **An investigation is bounded work.** Nobody reads all the logs; they read
  what the pivots reach, and they publish that they stopped.

## BOTSv3's actual shape

Verified live at HEAD, `| tstats min(_time) max(_time)`:

| index | first | last | span |
|---|---|---|---|
| botsv1 | 1470009600 (2016-08-01) | 1472450339 (2016-08-29) | ~28d |
| botsv2 | 1501545600 (2017-08-01) | 1504223999 (2017-08-31) | ~31d |
| botsv3 | 1534737603 (2018-08-20) | 1568916650 (2019-09-19) | scenario is a single day, 20 Aug 2018, ~0900-1600, ~2.03M events; the tail beyond that is later lab/index residue and is NOT the scenario window |
| portal5_lab | 1285858417 | 1787316013 (~today) | Lane B/C live index; carries whatever has been shipped into it, including prior cousin injections |

BOTSv3 is a multi-stage Taedonggang intrusion against Frothly crossing
`aws:cloudtrail` (IAM abuse, `null_admin`, public `frothlywebcode` bucket),
`symantec:ep:*` (Monero miner), Windows endpoints, VPN and Linux. **The
stages share no identifier**: `web_admin` (AWS IAM) and `BSTOLL-L` (endpoint)
are different entities in one incident -- entity resolution cannot link
them, only a pivot chain can. Backward reach for this corpus is
hours-to-a-day, not the 14-day median real-world dwell; that is a
per-corpus setting, and it is exactly why BOTS is testable at all: the whole
chain sits inside a known, published window.

## The injection defect this exposes

`cousin_inject.inject_cousins` shipped every cousin at `now = time.time()`
-- 2026 -- while BOTS is 2016-2019. The needles were never in the haystack;
they sat in the same index roughly eight years away. A time-bounded
investigation over the corpus's own range cannot reach a 2026 cousin at all,
so T.3's `product_cousin_recall 0.2` measured cousins floating in their own
time bubble, not recovery inside real data.

## Errata on BULLY_REAL_TELEMETRY_RUN_T3_V1.md

- Its **53 rec/sec** figure measured an unbounded `earliest=0` scan truncated
  by `| head`, not the anchor-pivot engine this task adds. It is not a
  capability ceiling.
- Its **`product_cousin_recall 0.2`** measured cousins injected at "now"
  (2026), ~8 years outside every BOTS index's real range. No time-bounded
  investigation over the corpus could ever have reached them; the figure
  measures temporal disjointness, not recovery.

Neither figure describes the product built here.

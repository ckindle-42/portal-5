# OrcaCyber Hunt — Deep Dive 3: the Round-2 verdicts' five shortfalls, root-caused

**Date:** 2026-11-21 · **Base:** `main` at `e522dfa47` (D0–D10 merged, D6 rebuild live) · **Lane:**
`lane/orcacyber-deep-dive-3` · **Scope:** diagnosis and replan only. No production code, no Splunk
configuration, no `launch.sh`, no held-out set (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`).
`.env` was never read by this lane; every receipt below comes from a stored run directory or from
code on this commit.

**Inputs.** The four Round-2 verdict reports (`coding_task/REPORT_HUNT_VERDICT_R2_{santos,kyoushi,russell,botsv2}.md`),
the three botsv2 findings (`coding_task/FINDING_HUNT_R2_BOTSV2_{RUN_A,NOTABLES_CRASH,WIDE_ESTATE}.md`),
the prior plan (`docs/hunt/ORCACYBER_DEEP_DIVE_2.md`), the stored runs on
`/Volumes/data01/portal5_hunt/hunt_proof_r2_{santos,kyoushi,russell}/v2/<family>/`, the botsv2
run C in the botsv2 lane's scratch (`/Users/chris/projects/portal-5-hunt-proof-r2-botsv2/coding_task/scratch/hunt_proof_r2_botsv2/run_c/botsv2`),
and the code at `portal/modules/security/core/hunt/`.

**Headline.** None of the five shortfalls is a tuning problem. Each is a **contract mismatch
between two layers that each behave as written**:

| # | shortfall | the invariant that is violated | where |
|---|---|---|---|
| 1 | D1 per-file read returns 0 rows on the graded web files | "a file read is placed where *that file* has events, on *that file*'s host, with a cap that reflects *that window*" | the estate map carries no time; windows, hosts and heads are all source/index-level |
| 2 | D5 `mechanism: accelerated` never fires | "rung 1 fires when one model's summary *covers the range being read*" | the range is the union of every wide source in the index; one CIM model is a subset of the index |
| 3 | D0 `evidence_absent` prints `n/a` | "the ledger's estate-map row names one path per row" | the D1 map row is `by sourcetype source host`, and the ledger stores a *deduplicated cell set*, so paths ≠ rows by construction |
| 4 | botsv2 `--stage all` reads nothing; `notables` aborts | "a stage's clock starts at its own work"; "every behaviour belongs to a card that consumes `similar_to_known`" | one job clock spans the model-bound cards stage; the notables stage injects inventory candidates after behaviours and the assertion covers them |
| 5 | judge AUC 0.151 / 0.403 / 0.332 on the `_v2` families | "the AUC measures the judge" | `bad` is term/window coincidence, `good` is dominated by a generator the prompt saturates at p≈1.0; the pooled AUC is an arithmetic bounded by that composition |

The judge did **not** invert. §5 shows the metric is arithmetically incapable of exceeding 0.41 on
santos while the `similar_to_known` population sits at p≈1.0, and that with that stratum removed
russell scores 0.628 — above chance. The model behaves sanely on the content it is given.

---

## 0. Method, and which claims are verified here

Three kinds of evidence appear below, labelled inline:

- **[VERIFIED]** — re-derived by this lane from a stored run directory or from this commit's code.
  The command or query is given so it can be re-run. No live Splunk query was issued.
- **[REPORTED]** — quoted from a Round-2 verdict/finding, not re-measured here.
- **[REASONED]** — an inference from verified code and verified receipts, with the inference chain
  written out.

Scratch scripts that produced the [VERIFIED] numbers are in `coding_task/scratch/d3/`
(`judge_auc.py`, `auc_cap.py`, `gen_mix.py`, `botsv2_judge.py`, `prompts.py`, `similar_margin.py`,
`bad_label.py`, `covered_evidence.py`, `d0_paths.py`, `d5_span.py`, `deviation_detail.py`). They
read stored run dirs and the labelled corpus trees only; none writes to `/Volumes`.

---

## 1. Defect 1 — D1: per-file routing landed; placement, host and head did not

### 1.1 What does work

The per-file route is real. `sample.read_files` issues one read per indexed file:

```python
# portal/modules/security/core/hunt/notables/sample.py:654
"""One read per indexed file with its own `head`: a pooled `head` returns arrival order."""
```
```python
# sample.py:703-708
        futures = [
            pool.submit(
                _read_range,
                executor,
                f"search index={_quoted(facts.index)} {file_route(facts, item.path, host)}"
                f" | head {head}",
```

and the receipt names the graded files, e.g. **[VERIFIED]** from
`/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos/progress.json:stages.behaviours.files`:
`/apache2/intranet.smith.santos.com-access.log` has 8 `(file,window)` rows; routing receipts say
`files_indexed 21 / files_routed 21 / files_omitted 0` **[REPORTED]**.

### 1.2 Root cause A — the estate map has no time for a file, so a file cannot be placed

```python
# sample.py:51-58
@dataclass(frozen=True)
class IndexFile:
    """One indexed source path under a sourcetype: its volume and the hosts it appears on."""

    path: str
    events: int
    hosts: tuple[str, ...] = ()
```
```python
# sample.py:469
sources, source_reason = _meta_rows(executor, index, "by sourcetype source host", start, end)
```

The estate map is `count` **by sourcetype source host** — volume and host only. Nothing in the run
knows when a given file has events. **[VERIFIED]** from the santos run's `sources.json`, the graded
file's fact is exactly:

```json
{"path": "/apache2/intranet.smith.santos.com-access.log", "events": 9462,
 "hosts": ["intranet_server"]}
```

Consequence: every later placement decision for that file must be borrowed from its sourcetype.
The 9,462 events of the graded file live `2022-01-17 10:00–19:00Z` with 7,894 of them in
11:00–12:00 **[REPORTED, live `tstats by _time span=1h`]**, while the source-wide schedule the run
actually used are 01-13T14:45, 01-14T16:39, 01-15T18:33 and one ending 01-17T01:38 (§1.4,
[VERIFIED] from the run's own `files` rows) — all of them before the file's 10:00Z start. A
source-span schedule cannot find the file's hour.

### 1.3 Root cause B — the file's windows are the source's even slices

```python
# sample.py:666-670
readable = [bounds for bounds in windows if bounds[1] > bounds[0]]
parts = max(1, sub_windows)
slice_bounds: list[tuple[float, float]] = []
for start, end in readable:
    slice_bounds.extend(window_bounds(start, end, parts))
```
```python
# sample.py:767-773
def _spread_windows(bounds: Sequence[tuple[float, float]], take: int) -> list[tuple[float, float]]:
    """`take` windows spread evenly across the schedule, keeping time coverage."""
    if take >= len(bounds):
        return list(bounds)
    step = len(bounds) / take
    picks = sorted({min(len(bounds) - 1, int(number * step)) for number in range(take)})
    return [bounds[number] for number in picks]
```

`windows` is always a *source-wide* schedule produced by `behaviours.source_windows(facts, N)`
(`behaviours.py:951`, `:980`, `:1001`, `:1080`). `read_files` subdivides and then **spreads evenly
over that source schedule** — never over the file's own range. An even spread over a 5.6-day
source span cannot land on a 1–2 hour burst, and `_spread_windows` actively removes windows
(`take < len(bounds)` drops the rest), so a burst-bearing window can be discarded.

### 1.4 Root cause C — the anchor host is index-level, and is applied to a file that has no such host

Localisation is computed **once per index**, over the union of all wide sources:

```python
# behaviours.py:1197-1206
by_index: dict[str, list[SourceFacts]] = {}
for facts in sampled:
    by_index.setdefault(facts.index, []).append(facts)
...
for index, facts_list in sorted(by_index.items()):
    start = min(facts.first for facts in facts_list)
    end = max(facts.last for facts in facts_list) + 0.000001
    located = localise(executor, index, start, end)
```

and every wide source in that index is then read against that one anchor set:

```python
# behaviours.py:1375-1391
            for source_id, _group, facts, _started in scheduled:
                located = _localisation_of(anchors_by_index, facts.index)
                futures.append(
                    pool.submit(
                        read_behaviour_source,
                        executor,
                        facts,
                        per_window,
                        burst_windows=burst_plan.get(facts.sourcetype, ()),
                        anchors=located.windows,
                        accel_window=located.accel_window,
                        value_spans=value_spans.get(source_id, ()),
                    )
                )
```

`read_files` then passes the anchor host into the file's route — including for files that are not on
that host:

```python
# sample.py:681-682
on_host = [item for item in facts.files if not host or not item.hosts or host in item.hosts]
for index, item in enumerate(on_host or facts.files):
```
```python
# sample.py:635-640
def file_route(facts: SourceFacts, path: str, host: str = "", shared: Sequence[str] = ()) -> str:
    route = f"source={_quoted(path)}"
    ...
    return f"{route} host={_quoted(host)}" if host else route
```

Read line 681–682 carefully: when the file is on **no** host of the anchor, `on_host` is empty and
the loop falls back to **all** files — but `host` is still passed to `file_route`, so every such
read carries a host filter the file cannot satisfy. The read is silently empty, not skipped. This is
not an edge case: **[VERIFIED]** santos's localisation has `hosts: 1` (`inet-firewall`) and **none**
of the 21 `access_combined` files is on `inet-firewall` (12 on `webserver`, 4 on `cloud_share`, 4 on
`intranet_server`, 1 on the three mail hosts), so every anchored read of that sourcetype — 4 anchors
× 21 files = 84 planned reads — is host-mismatched by construction.

**[VERIFIED]** santos: the localised windows are `{"hosts": 1, "windows": 4, ...}` and all four are
on the network host `inet-firewall`; the graded file's only host is `intranet_server`. Its receipt:

```
path=/apache2/intranet.smith.santos.com-access.log events_available=9462 hosts=['intranet_server']
  host=''              window 1642085133..1642103782  rows 0  reason ''
  host=''              window 1642178378..1642197027  rows 0  reason ''
  host=''              window 1642271623..1642290272  rows 0  reason ''
  host=''              window 1642364868..1642383517  rows 0  reason ''
  host='inet-firewall' window 1642172400..1642176000  rows 0  reason ''
  host='inet-firewall' window 1642244400..1642248000  rows 0  reason ''
  host='inet-firewall' window 1642420800..1642424400  rows 0  reason ''
  host='inet-firewall' window 1642428000..1642431600  rows 0  reason ''
```

Eight planned reads, all zero, all with no reason. The four uniform windows are
`01-13T14:45–19:56`, `01-14T16:39–21:50`, `01-15T18:33–23:44` and `01-16T20:27–01-17T01:38` — all
before the file's first event at 10:00Z. More telling, the anchored windows `01-17T12:00–13:00Z` and
`01-17T14:00–15:00Z` **are inside the file's active range** and still return zero — the host filter
alone empties them. **Zero rows from the file that carries 7,786 labelled lines.** That is exactly
the mechanism, and it is why `attacker_http, dirb, wpscan` are unreachable while the route is
correct.

### 1.5 Root cause D — the per-read cap is a source-share, not the window's density

```python
# sample.py:741-744
def _file_budget(events: int, total: int, per_window: int, windows: int) -> int:
    """One file's share of the rows one source-wide read schedule may return."""
    share = max(1, events) / max(1, total)
    return min(max(1, events), max(1, math.ceil(share * per_window * windows)))
```
```python
# sample.py:759-764
def _file_head(
    events: int, total: int, per_window: int, windows: int, take: int, per_read: int
) -> int:
    """One file's per-read cap: its budget over its windows, never above a pooled read's."""
    budget = _file_budget(events, total, per_window, windows)
    return max(1, min(per_read, math.ceil(budget / max(1, take))))
```

The cap is the file's share of the **source's total volume**, divided by the number of windows taken.
It is not a function of the events in the window being read.

**[VERIFIED] the cap is what every anchored read returned, to the row.** With `windows = 1` for an
anchored read (one anchor window, `_file_window_count` → `take = 1`), `_file_head` reduces to
`ceil(file.events / source.events × per_window)`:

| family | graded file events / sourcetype events | `ceil(share × 2,500)` | rows the anchored read returned |
|---|---:|---:|---:|
| russell | 8,530 / 148,329 = 5.75 % | **144** | **144** |
| kyoushi | 408,477 / 727,925 = 56.1 % | **1,403** | **1,403** |
| santos | 9,462 / 329,442 = 2.87 % | 72 | 0 (host filter, §1.4) |

So the anchored reads were *cap*-limited, not data-limited: kyoushi's correctly placed
attack-window read stopped at 1,403 rows while the file keeps 99.5 % of its 408,477 lines in that
burst **[REPORTED]**, and russell's stopped at 144 while the window held 7,698 **[REPORTED]**. The
one read that found the attack returned its cap, because the cap was a percentage of the wrong
denominator.

**[VERIFIED]** russell's eleven reads on the graded file, in full:

```
/apache2/intranet.smith.russellmitchell.com-access.log.2  events_available 8530
  host=''              window 1642686439..1642705190  rows 0
  host=''              window 1642723942..1642742694  rows 0
  host=''              window 1642780196..1642798948  rows 0
  host=''              window 1642836451..1642855202  rows 0
  host=''              window 1642892706..1642911457  rows 0
  host=''              window 1642948960..1642967712  rows 288   (head 411, one overlapping slice)
  host=''              window 1643005214..1643023966  rows 0
  host='inet-firewall' window 1642759200..1642762800  rows 0     (host mismatch)
  host='inet-firewall' window 1642845600..1642849200  rows 0     (host mismatch)
  host='intranet_server' window 1642993200..1642996800 rows 144  (right host, right hour, head 144)
  host='vpn'           window 1642993200..1642996800 rows 0     (host mismatch)
```

432 of 8,530 rows (5.1 %). Three of the eleven reads are structurally empty for host mismatch, six
land where the file has no events, one is cap-starved and one is the attack hour cap-starved.

### 1.6 Root cause E — a read that returns 0 rows is receipted as a success

```python
# sample.py:722-726
found.files.append(
    FileRead(
        item.path, host, item.events, start, end, len(rows), reason or "", item.hosts
    )
)
```

`reason` is only set when the transport refused. A read that completed and matched nothing is
recorded with `reason: ""`. **[VERIFIED]** planned file-window reads across the four stored runs:

| family / run | file-window rows | zero rows | zero rows with no reason | refusals declared |
|---|---:|---:|---:|---:|
| santos `_v2` | 875 | 688 | **688** | 0 |
| kyoushi `_v2` | 673 | 483 | **483** | 0 |
| russell `_v2` | 917 | 770 | **770** | 0 |
| botsv2 run B | 1,963 | 752 | **602** | 150 `request_budget_exhausted` |

79 % / 72 % / 84 % of every planned file read in the three `_v2` runs returned nothing and the
receipt says nothing. On kyoushi that is the whole reason the round read as "26/26 files routed, no
omissions" while 19 of 26 files yielded no row **[REPORTED]**: routing and reading are receipted as
the same event.


### 1.7 Root cause F — the per-file route multiplies the request count by the file count

`read_files` plans `_file_window_count(...)` windows **per file**, and the window count is derived
from the source's schedule length (up to `BEHAVIOUR_WINDOWS * BEHAVIOUR_SUB_WINDOWS = 24`):

```python
# behaviours.py:39-44
BEHAVIOUR_WINDOWS = 12  # effort budget: time slices read per activity source
BEHAVIOUR_BURST_WINDOWS = 4  # peak four-hour slices reserved inside BEHAVIOUR_WINDOWS
BEHAVIOUR_SUB_WINDOWS = 2  # each uniform slice read at midpoint and tail when no bursts planned
```

**[VERIFIED]** botsv2 run B: `stages.behaviours.searches = {"total": 2000, "by_kind": {"discovery": 180,
"localise_accel": 6, "localise": 1, "behavior_events": 1813}}` — 1,813 behaviour reads for 181 files,
i.e. ~10 per file, and the 2,000-request ceiling ended the read with `winhostmon` 1 of 9 files read
and 150 windows refused. D1's estimate of 473–651 reads for the tuned families holds only while the
large sourcetypes happen to have few files; the wide control has 181 **[REPORTED]**.

---

## 2. Defect 2 — D5: rung 1 cannot fire, and could not be observed if it did

### 2.1 Defect 2a — the guard asks one model to cover the union of every wide source

```python
# sample.py:168-172
def coverage_label(accel_window: Sequence[float] | None, start: float, end: float) -> str:
    """`accelerated` only inside a model's window; everything else is a scan, never a miss."""
    if accel_window and float(accel_window[0]) <= start and end <= float(accel_window[1]):
        return "accelerated"
    return "scan"
```
```python
# behaviours.py:1203-1206
for index, facts_list in sorted(by_index.items()):
    start = min(facts.first for facts in facts_list)
    end = max(facts.last for facts in facts_list) + 0.000001
    located = localise(executor, index, start, end)
```

`localise` is called **once per index** with `[min(first), max(last)]` over every wide source, and
`coverage_label` requires **one** model's summary to contain that whole interval. A CIM data model
summarises a *subset* of sourcetypes, so its window is a sub-interval of the index by construction.
Containment is therefore impossible unless the estate's first and last events happen to fall in one
model's sourcetypes.

**[VERIFIED]** re-derived from each run's `sources.json` (`min(first)`, `max(last)` over wide
sources) against the `accel_window` the run recorded (which is `summaries[0].window`, i.e. the
Authentication model's):

| family | localise span | Authentication summary window | start short | end short |
|---|---|---|---|---:|
| santos | `[1616425561 .. 1642487481]` | `[1616425563 .. 1642485679]` | **2 s** | **1,802 s** |
| kyoushi | `[1616425561 .. 1616890440]` | `[1616425563 .. 1616890425]` | **2 s** | **15 s** |
| russell | `[1616425561 .. 1643094188]` | `[1616425563 .. 1643094167]` | **2 s** | **21 s** |

The **2 s** start shortfall on all three families is structural, not noise **[VERIFIED]**: the
earliest wide source is `syslog` at `1616425561` in all three runs, and the Authentication model's
earliest summarised event is `1616425563` — 2 s later — so that model does not hold the index's first
events. The same holds at
the end on two families — santos's and russell's **latest** wide source is `syslog` (`1642487481`,
`1643094188`) while the summary ends `1,802 s` / `21 s` earlier; kyoushi's latest is `suricata`
(`1616890440`) against a summary ending 15 s earlier. So on every family the union interval is
bounded by sources that at least one of the two ends does not summarise. `summary_window` cannot
help — it adds a microsecond to `max(_time)` and nothing to `min(_time)` (`sample.py:257`).

The guard is not the fixable part; **the operand is**. **[VERIFIED]** per-source, how many wide
sources are already *wholly inside* the Authentication window — an upper bound on how many could fire
rung 1 under a per-source operand, since a source summarised by a different model must be inside
*that* model's window:

| family | wide sources | wholly inside the Authentication window | outside |
|---|---:|---:|---|
| santos | 15 | **14** | `syslog` (ends 1,802 s after the summary) |
| kyoushi | 16 | **9** | seven `suricata` partitions (end 15 s after) |
| russell | 16 | **15** | `syslog` (ends 21 s after) |

So per-source operands make rung 1 *possible* for most of the estate **with the guard unchanged**;
the exact count is a property of which model owns which sourcetype and must be read off the run. The
sources that remain outside need a declared partial-coverage path (§6, E3), not a tolerance constant.

### 2.2 Defect 2b — the read receipt cannot carry `accelerated`, even on success

```python
# sample.py:814-818  (read_anchors)
found.read_mode = "anchored"
found.rung = "narrowed_scan"
found.events_scanned = sum(anchor.events for anchor in readable)
found.coverage = "scan"
```
```python
# behaviours.py:925-929  (_merge_anchored, the path every rung-3 read takes)
found.read_mode = "anchored"
found.rung = "narrowed_scan"
found.events_scanned = anchored.events_scanned + kept_uniform
found.coverage = "scan"
found.accel_window = anchored.accel_window
```

`grep '"accelerated"' portal/modules/security/core/hunt/` returns only `sample.py`'s
`Localisation` assignments and the inventory's own mechanism labels. **No `RowSet.coverage` can ever
be `"accelerated"`.** The `accel_window` is carried alongside, so the receipt *knows* the covering
model, and still prints `coverage: scan`. The acceptance property "a read receipt carries
`coverage: accelerated`" was unsatisfiable on every family regardless of index quality.

### 2.3 Defect 2c — localisation is per index, so a source inherits a foreign host's peaks

Same code as §1.4 (`behaviours.py:1197-1206`). Every wide source in an index shares one anchor set,
so on a multi-host estate the peaks of the loudest host are read against sources that are not on it
— the other half of §1.4's zero rows.

---

## 3. Defect 3 — D0: the estate-map reader still expects the pre-D1 row shape

### 3.1 Code

```python
# scoreboard.py:630-652
def _index_paths(directory: Path) -> tuple[frozenset[str] | None, str]:
    """The source paths the run's own estate map counted in its index, or None when unknown."""
    ...
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ...
        if str(row.get("stage") or "") != "cards" or row.get("capped"):
            continue
        if "by sourcetype source" not in str(row.get("query") or ""):
            continue
        found = {
            str(cell) for cell in row.get("values_extracted") or () if str(cell).startswith("/")
        }
        if len(found) != int(row.get("rows") or 0):
            continue
        paths |= found
    if not paths:
        return None, "the run recorded no complete per-source index map"
```

The guard `len(found) == rows` encodes "one path cell per aggregate row". But the ledger does not
store rows — it stores a **deduplicated union of every cell**:

```python
# run.py:91-106
def _extracted_values(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    values: dict[str, None] = {}

    def visit(value: Any) -> None:
        ...
        elif value is not None and str(value):
            values.setdefault(str(value), None)

    for row in rows:
        visit(row)
    return list(values)
```

With two fields (`by sourcetype source`) each row contributed exactly one path and the count
matched. With three fields (`by sourcetype source host`) a path appears once per host, the cell set
deduplicates them, and `len(found) != rows` **always**. The guard is not rejecting a malformed map;
it is comparing a set of distinct paths against a count of tuples.

### 3.2 Receipts, and what the reader is throwing away

**[VERIFIED]** from each run's `ledger.jsonl` (the single matching cards row) and the key files:

| family | ledger `rows` | `values_extracted` | distinct `/`-cells | guard | `evidence_absent` with the path set |
|---|---:|---:|---:|---|---|
| santos | 4,626 | 4,707 | **89** | 89 ≠ 4,626 → reject | `crack_passwords 44/44` |
| kyoushi | 6,848 | 6,916 | **80** | 80 ≠ 6,848 → reject | none (correct) |
| russell | 2,487 | 2,569 | **91** | 91 ≠ 2,487 → reject | `crack_passwords 49/49` |

So the ledger **does** hold a complete per-source index map on all three families, and the reader
accepts none of them. The live consequence is exactly as the verdicts recorded **[VERIFIED]** by
re-running the scoreboard over the santos run:

```
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 3353/47367
C0 evidence absent  n/a (the run recorded no complete per-source index map)
```

With the path set the same run yields `crack_passwords 44/44`, which moves the step denominator
21 → 20 and is the D0 property the plan promised.

### 3.3 Why the unit suite stayed green

`tests/unit/test_hunt_scoreboard.py:116-133` writes the estate-map row as

```python
"query": '| tstats count where index="idx" by sourcetype source',
"rows": len(listed),
"values_extracted": listed,
```

i.e. it asserts the old two-field shape *against itself*. No test ever feeds the three-field row the
pipeline now produces, so the drift was invisible to `tests/unit/`.

---

## 4. Defect 4 — botsv2's three run-path defects

### 4.1 L1 — one job clock spans a model-bound stage

```python
# executor.py:26-32
DEFAULT_BUDGETS: dict[str, float] = {
    "query_seconds": 30.0,  # effort budget: server-side duration for one query
    "job_seconds": 720.0,  # effort budget: shared hunt wall time across every worker
    "requests": 2000,  # effort budget: total Splunk requests, including parallel calls
    ...
}
```
```python
# executor.py:149-151
@property
def deadline(self) -> float:
    return self.started + self.limits["job_seconds"]
```
```python
# executor.py:550-554
if budget.remaining() <= 0:
    budget.exhausted = budget.expired_reason() or "job_deadline_exceeded"
    if budget.exhausted == "job_deadline_exceeded":
        raise HuntDeadlineExceededError(budget.exhausted)
```

`HuntBudget.started` is set when the executor is constructed, and `__main__.main` builds **one**
`search` and runs every stage in one process (`__main__.py:333-402`). The cards stage is model-bound
— it issues no Splunk read — but the wall time it spends is charged to the same clock. **[REPORTED]**
run A: cards 573.239 s + inventory 147.273 s = 720.5 s before the first behaviour read, hence
`events_read = 0`, `files_omitted 181`, every file row
`reason: job_deadline_exceeded`, and `HuntDeadlineExceededError` at `relate`.

The budget was never meant to bound model work (`MODEL_WORK_SECONDS = 300.0` is the judge's own
clock, `judge.py:21`). The defect is that a stage with no Splunk reads shares a read clock.

### 4.2 L2 — the notables contract: inventory candidates from an alert card abort the stage

Three independent facts compose into the crash:

```python
# cards.py:38-43
CARD_KIND_CONSUMERS = {
    "activity": frozenset({"behaviours", "peer_rare", "similar_to_known", "manifest"}),
    "alert": frozenset({"alerts"}),
    "measurement": frozenset(),
    "other": frozenset(),
}
```
```python
# inventory.py:1554-1557
    for joint in document.get("joints") or ():
        if not isinstance(joint, Mapping) or joint.get("status") != "complete":
            continue
```
```python
# run.py:575,580
    behaviours = load_behaviours(store)
    ...
    behaviours, source_facts, inventory_receipt = _stored_inventory(out, cards, behaviours)
```
```python
# run.py:606-608
        similar, detail = generate_similar(
            behaviours,
```
```python
# similar.py:291-305
    invalid = sorted({item.source_id for item in behaviours} - eligible_sources)
    if invalid:
        ...
        raise SimilarityError(
            "behaviour sources need an activity card with roles: " + "; ".join(invalid_details)
        )
```

`_unseen_candidates` filters on `status == "complete"` only — it does not ask whether any generator
consumes the source. The notables stage then adds those candidates to the in-memory behaviour list
**before** `generate_similar`, which asserts that *every* behaviour's source has a card consuming
`similar_to_known`. An alert card never does. So **any** complete inventory list on an alert-kind
source aborts the whole notables stage — no `notables.jsonl`, therefore no relate, judge or score.

**[REPORTED]** the crash, and the one row that triggers it:
`SimilarityError: behaviour sources need an activity card with roles: botsv2:pan:threat (kinds: alert)`,
`store behaviours 18668 / after inventory 18700 replaced 0 candidates 32 / sources only after
inventory: {'botsv2:pan:threat': 1}`. **[VERIFIED]** the code path: `_ranked_notables` is called on
the whole list handed to `generate_similar`, and the only filter is `card_consumers(card)`.

Two orthogonal sub-defects, either of which fixes the crash (E5 does both, they are one line each):
a candidate must not be minted for a card no generator consumes; and `similar` must skip a
non-consuming source rather than fail the run for it.

### 4.3 L3 — the request ceiling ends the read, and refused reads never reach the ledger

```python
# executor.py:555-557
            if budget.queries >= budget.limits["requests"]:
                budget.exhausted = "request_budget_exhausted"
                raise HuntBudgetExceededError(budget.exhausted)
```
```python
# executor.py:382-396
            rows, reason, retry_error, error, spend, query_deadline = self._read_attempt(
                query, start, end, kind, row_cap, query_deadline
            )
            if retry_error is None:
                if isinstance(error, (SearchBudgetExceededError, HuntSearchFailedError)):
                    if self.read_observer is not None and self.budget.queries > queries_before:
                        self.read_observer(...)
                    raise error
```

`_reserve` raises **before** `budget.queries += 1`, so in `read()` `self.budget.queries > queries_before`
is false and the observer never fires — and because `_read_attempt` raises rather than returning, the
observer call after the loop (`executor.py:411`) is never reached at all. A budget-refused read
therefore leaves **no** ledger row, while the same refusal *is* visible in the `files` receipt
(where `_read_range` catches the exception). **[REPORTED]** botsv2 run B: 150
`request_budget_exhausted` file rows, zero such ledger rows, "2,000 behaviour-stage rows, all issued
queries".

---

## 5. Defect 5 — the judge metric inverted. The judge did not.

### 5.1 What the number is

```python
# scoreboard.py:716-730
def _judge_block(notables: Sequence[Notable], cache: Mapping[str, Any]) -> dict[str, Any] | None:
    scored = _judged(notables, cache)
    if not scored:
        return None
    bad = [value for notable, value in scored if notable.covered]
    good = [value for notable, value in scored if not notable.covered]
    return {
        ...
        "auc": _auc(bad, good),
        ...
        "labelling": "bad = the notable covers a labelled line; good = it covers none",
    }
```

`bad`/`good` is **generator-blind**: every notable is pooled into one binary class. Two properties
of the Round-2 populations then decide the number before the judge is consulted.

### 5.2 The `good` class is dominated by a stratum the prompt saturates at p≈1.0

`similar_to_known` emits a fixed **300** rows by *relative rank* with no absolute margin
(`similar.py:14 SIMILAR_NOTABLE_BUDGET = 300`), merged first (`run.py:74 MERGE_PRIORITY`), and
almost none of them covers a labelled line.

**[VERIFIED]** per-family composition of the judged set (stored `notables.jsonl`, coverage computed
through `scoreboard._coverage` over the labelled corpus tree):

| family | judged | bad | good | of the good: `similar_to_known` | of those, p ≥ 0.99 |
|---|---:|---:|---:|---:|---:|
| santos | 531 | 36 | 495 | **291** | **290** |
| kyoushi | 438 | 29 | 409 | **235** | **199** |
| russell | 576 | 42 | 534 | **288** | **288** |

So on santos, 291 of the 495 "good" rows are pinned at p ≈ 1.0. The pooled AUC cannot exceed
`(495-291)/495 = 0.414` no matter what the judge does with every other row; on kyoushi the ceiling
is 0.513, on russell 0.461. **[VERIFIED]**:

```
santos : AUC 0.151   pooled ceiling-if-saturated 0.414   non-similar-only AUC 0.300
kyoushi: AUC 0.403   pooled ceiling-if-saturated 0.513   non-similar-only AUC 0.417
russell: AUC 0.332   pooled ceiling-if-saturated 0.461   non-similar-only AUC 0.628
```

russell's non-similar population separates **above chance**. The judge is not inverted; the pooled
statistic is a mixture of a saturated stratum and the stratified one.

### 5.3 The prompt tells the judge the answer

```python
# judge_notables.py:111-125  (notable_body)
    return "\n".join(
        part
        for part in (
            str(notable.get("what") or "")[:JUDGE_STATEMENT_CHARS],
            f"entities: {entities}" if entities else "",
            f"generator: {notable.get('generator')} / {notable.get('basis')}",
            reliability_line,
            f"why raised: {notable.get('why')}",
            "nearest known items:",
            *_known_lines(notable),
            "examples:",
            *[f"- {line}" for line in _lines(notable)],
        )
        if part
    )
```

`_known_lines` renders `label_kind` verbatim (`known_bad` / `known_good`) at the nearest cosine,
and `why` for this generator reads `nearest known-bad <label> from <family> at cosine 0.986
(AUC)`. The **decision statistic is not in the prompt** (`measure` is never rendered), so the model
sees "a known-bad attack step matched at 0.99" and never sees the margin that made the row rank —
nor a threshold it failed. **[VERIFIED]** full prompt for santos's `similar_to_known` row 8:

```
NOTABLE:
actor 1003 did USER_CMD
entities: actor=1003; action=USER_CMD
generator: similar_to_known / nearest_known_behaviour
generator reliability (measured AUC): 0.443
why raised: nearest known-bad escalate from kyoushi at cosine 0.986; measured AUC 0.443
nearest known items:
- escalate (known_bad, basis=attack_step, similarity=0.9855695962905884, family=kyoushi)
- escalated_command (known_bad, basis=attack_step, similarity=0.9855695962905884, family=kyoushi)
- escalated_sudo_command (known_bad, basis=attack_step, similarity=0.9855695962905884, family=kyoushi)
examples:
- type=USER_CMD msg=audit(1642321658.493:8290): pid=5004 uid=1003 ... cmd=7461696C202F7661722F6C6F672F7379736C6F67 ...
```

(the audit line's hex command is `tail /var/log/syslog`; this row's `measure` is
`known_bad_minus_good = 0.1085`). p_yes = 0.99998.

**[VERIFIED]** the response is insensitive to the margin: every similar row in these runs has a
*positive* margin (the budget keeps the top 300 by rank), and the yes-rate is flat across margin
bands —

| family | margin 0–0.05 (n / yes) | 0.05–0.1 (n / yes) | > 0.1 (n / yes) |
|---|---|---|---|
| santos | – | 288 / 1.000 | 8 / 0.875 |
| kyoushi | 219 / 0.977 | 19 / 1.000 | 10 / 1.000 |
| russell | – | 293 / 1.000 | 7 / 1.000 |

A stratum that answers "yes" 97.7–100 % of the time carries no separation, and because it is 52–57 %
of the judged pool (296/531, 248/438, 300/576) and 54–59 % of the `good` class, it decides the
pooled number.

Note also `nearest_known` is unconditional: the nearest known-bad of *any* behaviour is reported at
median cosine 0.865 (santos), 0.844 (kyoushi), 0.855 (russell) — i.e. every behaviour in every index,
benign or not, has a "known-bad match at 0.86" to show the judge.

### 5.4 The `bad` class is term coincidence, not the attack

```python
# scoreboard.py:275-280
def _covers(claim: Claim, folded: str, moment: float | None) -> bool:
    if claim.folded:
        return all(term in folded for term in claim.folded)
    if claim.window is None or moment is None:
        return False
    return claim.window[0] <= moment < claim.window[1]
```

When a notable's evidence query names literal terms, **the window is ignored** and coverage is "all
claim terms occur somewhere in the line". A notable whose query names a generic program therefore
covers every labelled line that mentions it.

**[VERIFIED]** santos, the lowest-p `bad` notables (rank 236, p_yes 0.001):

```json
{"generator": "deviation",
 "what": "program systemd-logind to 144. first appeared 301.8 days in",
 "why": "first hour this behaviour was observed, relative to the index start",
 "evidence": [{"earliest": 1642485676.0, "latest": 1642485676.0,
   "line": "Jan 18 06:01:16 inet-dns systemd-logind[780]: Removed session 144.",
   "query": "search index=\"hb_ait_santos_v2\" (source=\"/auth.log.1\" OR source=\"/auth.log\") \"systemd-logind\" \"systemd\" | head 5"}]}
```

Its claim terms are `('systemd-logind', 'systemd')`; the labelled line it "covers" is

```
Jan 17 11:58:17 intranet-server systemd-logind[987]: New session c1 of user gmorgan.
   labels: attacker_change_user, escalate
```

A Jan-18 "Removed session 144" notable from a different host is scored **bad** because a Jan-17 line
also contains the word "systemd". The judge's `p_yes 0.001` is correct about the content; the label
is wrong.

**[VERIFIED]** how much of each family's `bad` class is claim-content-free (window-only, no literal
terms): santos 6/36, kyoushi 1/29, russell 1/42 — and those rows carry the extreme low p_yes values
(0.001–0.075). The bulk of the label error is the broader term-coincidence effect above: a
`deviation` notable whose evidence query names a field value (as the `systemd` one does) covers every
labelled line that carries that value, regardless of host, time or the notable's own content.

The judge's content judgement is sane on both sides **[VERIFIED]**, santos `deviation`:

```
covered   lowest p:  "program systemd-logind to 144 ..."        p 0.001
covered   lowest p:  "program systemd-logind to 142 ..."        p 0.001
uncovered highest p: "actor 172.21.131.50 did flow to 169.254.169.254 ..."  p 0.999
uncovered highest p: "actor 172.21.128.54 did flow to 169.254.169.254 ..."  p 0.999
```

Flow to `169.254.169.254` (the instance-metadata address) is a genuine SSRF/credential-access lead
and the model scores it 0.999 — while it is counted `good` because no key names it. A routine
`systemd-logind` session is scored 0.001 — while it is counted `bad` because a labelled line shares
a word. The signal is there and the labels invert it.

### 5.5 The botsv2 control proves the metric, not the model

**[VERIFIED]** botsv2 run C: 725/725 judged, no `similar_to_known` (dropped after the L2 crash),
`nearest_known` present on 0 of 725 rows, and the coverage pass finds 4 covered notables:

```
judged 725  bad 4  good 721  AUC 0.840
bad by generator {'deviation': 3, 'misfit': 1}   bad p_yes [0.864, 0.998, 1.0, 1.0]
```

The AUC is high because the saturated stratum is absent and the `good` class is small enough for
four correct "yes" answers to separate. Same seat, same prompt, same code — different composition.
`judge AUC` is therefore currently a **population statistic**, not a measure of the judge.

### 5.6 Also recorded (not the driver)

- The 720 s judge stage budget leaves 189–374 notables unjudged (`model_budget_exhausted`) and the
  unjudged tail is not sampled — it is the *end* of merged order (`judge_notables.py:366-371`
  `ask = pending[:budget]`). Since merge order is generator-priority, the judged set is a
  generator-biased sample; that is the mechanism by which §5.2 happens at all.
- `notable_body` renders the literal header `nearest known items:` even when the list is empty
  (visible in every non-similar prompt), and `what` for a card whose roles resolve to `*` is
  `"to * * * * * * burst to 2734 events in one four-hour bucket"` — a content-free statement the
  judge cannot act on (D2's parse vocabulary, not the judge's).

---

## 6. The E plan — eight orthogonal slices

Each slice owns **one layer** and one invariant, is independently testable offline, and has a live
acceptance line. Order E0 → E6 may land in any order; E1 → E2 is sequential (E2 consumes E1's data).
E3, E4, E5, E7 are independent of each other and of E1/E2.

| slice | invariant it restores | owner file(s) | depends on |
|---|---|---|---|
| **E0** receipt honesty | a planned read that returned nothing, or was refused, is declared with a reason in **both** the receipt and the ledger; a read's `coverage` reflects the localisation that produced it | `sample.py`, `executor.py`, `behaviours.py` | — |
| **E1** estate map carries time | every indexed file's fact carries its own `first`/`last`, not only its volume and hosts | `sample.py` (`IndexFile`, `index_facts`, `_files_of`), `cards.py` (`_facts`) | — |
| **E2** file-driven placement | a file is read where that file has events, on that file's host, with a cap that reflects that window's density | `sample.py` (`read_files`, `_file_budget`, `_file_head`), `behaviours.py` (`_read_anchor_files`) | E1 |
| **E3** per-source localisation | rung 1 fires per source over that source's own span, and a partially covered source declares which part it accelerated | `behaviours.py` (`_localise_sources`), `sample.py` (`localise`, `coverage_label`) | — |
| **E4** budget scope | no stage's wall clock is charged to another stage's Splunk budget; the request ceiling is planned, not discovered | `executor.py`, `run.py`/`__main__.py`, `behaviours.py` (planner) | — |
| **E5** notables contract | a candidate exists only for a source some enabled generator consumes; a non-consuming source is skipped, never fatal | `inventory.py` (`_unseen_candidates`), `similar.py` (`_ranked_notables`) | — |
| **E6** estate-map reader | the scoreboard reads a path set from the aggregate the run actually wrote, and `evidence_absent` adjusts the denominator | `scoreboard.py` (`_index_paths`) | — |
| **E7** judge measurement | the reported separation is computed within comparable strata, and the prompt carries the decision statistic rather than the label | `scoreboard.py` (`_judge_block`), `judge_notables.py` (`notable_body`) | — |

### E0 — receipt honesty (measurement plumbing)

**Property.** For every planned `(source, file, window)` read: `rows == 0` ⇒ `reason` is non-empty
(`empty_window`); a read refused by the shared request budget emits one `ledger.jsonl` row with
`reason: request_budget_exhausted`; a `RowSet` produced from a covering summary carries
`coverage: accelerated` (and `accel_window`), from a scan carries `coverage: scan`.

**Change.** `read_files` sets `reason = reason or ("empty_window" if not rows else "")` on the
`FileRead`; `HuntExecutor.read` moves the observer call into a `finally` so a raised budget error
still records, and `_reserve` increments `queries` before the ceiling check (or records the refusal
through `record_skipped_read` when it refuses); `read_anchors`/`_merge_anchored` take `coverage` from
the `Localisation` they were given instead of hardcoding `"scan"`.

**Unit tests.** `tests/unit/test_hunt_notables_sample.py`:
`test_a_zero_row_file_read_declares_an_empty_window`,
`test_a_budget_refused_read_writes_a_ledger_row`,
`test_a_read_from_a_covering_summary_reports_accelerated_coverage`.
`tests/unit/test_hunt_executor.py`: `test_the_observer_sees_a_request_budget_refusal`.

**Live proof.** After a family run, `progress.json:stages.behaviours.files` has no row with
`rows == 0` and empty `reason`; `ledger.jsonl` contains a row with `reason: request_budget_exhausted`
whenever the searches block reports one.

### E1 — the estate map carries a time range per file

**Property.** `sources.json:cards[].facts.files[]` carries `first` and `last` for every file, and for
the top file they equal a live `| tstats min(_time) as first max(_time) as last where index=<i> by
sourcetype source` within 1 s.

**Change.** `index_facts` reads `by sourcetype source host` with `min(_time) as first max(_time) as
last` (one query, same cost); `IndexFile` gains `first`/`last`; `_files_of` keeps the
`total == events` completeness test; `cards._facts` serialises the new fields; `_fact_dict` reads
them back. Old runs without the fields stay readable (`first=0.0,last=0.0` ⇒ fall back to the
source's span, i.e. current behaviour).

**Unit tests.** `test_estate_map_carries_each_files_own_time_range`,
`test_a_file_without_a_time_range_falls_back_to_its_source_span`,
`test_the_estate_map_still_declares_no_files_when_the_counts_do_not_add_up`.

**Live proof.** `python -c` over `sources.json` prints the graded file's `first`/`last`, and they
must match the live `| tstats min(_time) as first max(_time) as last where index=<i> by sourcetype
source` for that path within one second — and must **not** equal the sourcetype's own range. On
santos the graded file's range is the 2022-01-17 window the verdict measured live (10:00–19:00Z
**[REPORTED]**), while the sourcetype's range starts 01-13.

### E2 — file-driven placement, host and head

**Property.** For every graded file, and for every file a key names:
1. at least one read's window contains the file's `last` (its tail is always read), and at least one
   contains the file's densest hour;
2. every read for the file filters on a host **the file is on** (`FileRead.host` ∈ `FileRead.hosts`,
   or empty);
3. the file's total rows ≥ `min(file.events, per_window)`.

**Change.**
- windows: when a file has `first`/`last`, compute `slice_bounds` from the **file's** range
  (`window_bounds(file.first, file.last, FILE_READ_MIN_WINDOWS + …)`) and always include the tail
  slice `[last - width, last + ε)`; keep the source schedule only for files without a time range.
- host: in `read_files`, `on_host` empty ⇒ **no host filter** (pass `""`), never the inherited
  anchor's host; a file read for an anchor host it is not on is skipped with `reason:
  host_mismatch` instead of issued empty.
- head: `_file_head` becomes density-based — `head = min(per_read, events_in_this_window)`, using the
  file's own estimate for that window (`tstats` count for `source=<path>` in the window, one extra
  discovery request per planned file-window at most, cached per file), instead of the source-share
  budget.
- ordering: the head is applied after an explicit newest-first ordering so the tail is never the
  arbitrary N.

**Unit tests.** `test_a_files_windows_land_on_the_files_own_burst_not_the_sources`,
`test_a_file_is_never_read_with_a_host_it_is_not_on`,
`test_a_files_head_reflects_the_windows_density_not_its_source_share`,
`test_the_last_slice_of_a_file_is_always_planned`.

**Live proof (the round's core measurement).** For each family, `progress.json`:
(a) the graded file's rows ≥ `per_window` (2,500 on these estates), and every `FileRead` for it has
`host in ("", *hosts)`; (b) `behaviours.duckdb` `select count(*) from events where
source_id like '%:access_combined' and host='intranet_server'` ≥ 1,000 / 1,700 / 725
(santos/kyoushi/russell); (c) the scoreboard's `C0 ceiling` reachable set ⊇ the control's
(12/21, 11/12, 15/22) — i.e. `attacker_http, dirb, webshell_cmd, webshell_upload` reachable again.

### E3 — per-source localisation, per-read coverage label

**Property.** `progress.json:stages.behaviours.localisation.indexes` is keyed by **source** (or
carries a per-source array), and a source whose own `[first,last]` is inside its model's summary
window gets `mechanism: accelerated`. On the stored estates the *upper bound* for the santos estate
is 14 of 15 wide sources, 9 of 16 for kyoushi, 15 of 16 for russell (§2.1) — the realised count is
read from the run, because it depends on each sourcetype's model.

**Change.** `_localise_sources` moves `localise()` inside the per-source loop, passing
`(facts.first, facts.last + 1e-6)`; `coverage_label` keeps exact containment as its only
`accelerated` test; a source that is only **partly** covered gets
`mechanism: accelerated_partial` with `covered_window` + `scanned_window` recorded, and its reads are
the summary read for the covered sub-range plus a scan for the remainder. `accel_window` is
per-source. No tolerance constant is introduced.

**Unit tests.** `test_a_source_inside_one_models_window_localises_accelerated`,
`test_a_sources_span_is_never_compared_to_the_index_union`,
`test_a_partially_covered_source_declares_the_covered_and_scanned_ranges`.

**Live proof.** `localisation.indexes` is one entry per wide source (not one per index), the count
of `mechanism: accelerated` entries is > 0 on at least one family, and at least one read receipt
carries `coverage: accelerated` (E0 makes that possible). A run that still shows one index entry
with `mechanism: indexed` fails the slice.

### E4 — budget scope and a planned request ceiling

**Property.** A stage that issues no Splunk read cannot consume another stage's read budget:
`progress.json:stages.behaviours` issues its first read with `remaining_s ≥ job_seconds - 5`
regardless of how long cards took. And the behaviour read plan is *budgeted before it is issued*:
`len(planned requests) ≤ remaining requests`, with the shortfall named per file.

**Change.** `HuntBudget` gains `restart_clock()`; `run.py` calls it at the head of `behaviours` (or
`__main__` builds a fresh budget per stage while keeping the request counters global);
`read_files`' plan is filtered against `budget.remaining_requests()` in a deterministic priority
order (graded/wide/peaked files first — by `count_cv` and file size) and every filtered-out window is
declared with `reason: request_budget_exhausted` (E0 makes that ledger-visible).

**Unit tests.** `test_a_slow_model_stage_does_not_consume_the_read_clock`,
`test_the_read_plan_never_exceeds_the_remaining_request_budget`,
`test_a_window_dropped_by_the_planner_is_declared`.

**Live proof.** botsv2 `--stage all`: `stages.behaviours.events_read > 0`, no
`HuntDeadlineExceededError`, and `searches.total ≤ 2000` with `winhostmon` either fully read or
declared per file.

### E5 — the notables contract

**Property.** `notables` completes on an estate with a complete inventory list on an alert-kind
source; the candidates it adds are only those a generator consumes; no behaviour source can abort
the stage.

**Change.** `_unseen_candidates` takes the enabled consumers (or `card_consumers`) and skips joints
whose card consumes none of them; `_ranked_notables` computes `invalid` as a *skip set* and drops
those behaviours with a receipt tally (`skipped_sources: {source: behaviours}`) instead of raising;
`run.py` records the tally in the notables receipt.

**Unit tests.** `test_a_complete_list_on_an_alert_card_mints_no_candidate`,
`test_similar_skips_a_source_no_generator_consumes_and_records_it`,
`test_notables_completes_with_an_alert_card_candidate_present`.

**Live proof.** botsv2: the full-generator notables run completes, `notables.jsonl` exists,
`progress.json:stages.notables.similar_to_known` is present, and `skipped_sources` is empty on the
tuned families (santos/kyoushi/russell) — i.e. the alert-card skip is exercised only where it should
be.

### E6 — the estate-map reader

**Property.** `evidence_absent` is computed for every family whose ledger holds a complete estate
map, with the denominator adjusted: santos prints `crack_passwords 44/44` and steps 20; russell
`crack_passwords 49/49` and steps 21; kyoushi prints the block with no absent step.

**Change.** `_index_paths` accepts any row whose query contains `by sourcetype source`, and derives
the path set from the `/`-cells of `values_extracted` — the guard becomes "the cell set contains a
path for every source the run's own `sources.json` declares" (a real completeness test) instead of
`len(paths) == rows`. Keep the rejection when a row is `capped` or when neither side is available.

**Unit tests.** `test_the_estate_map_reads_a_three_field_sourcetype_source_host_row`,
`test_a_capped_estate_map_row_is_still_rejected`,
`test_a_complete_map_that_misses_a_declared_source_is_rejected`.

**Live proof.** Re-run the scoreboard over the stored Round-2 runs unchanged:
`C0 evidence absent  crack_passwords 44/44 (excluded from the step denominator)` on santos,
`49/49` on russell, and `C0 ceiling steps 11/20`, `11/21` respectively.

### E7 — judge measurement and prompt

**Property (metric).** The scoreboard reports separation **within** strata and a pooled figure only
over a declared comparable stratum:
`judge.auc_by_generator` (or by `(generator, basis)`), plus `judge.auc_pooled` computed over the
generators that can cover a labelled line (`deviation`, `misfit`, `peer_rare`, `alerts`, `set_novelty`)
— `similar_to_known` excluded from the pooled figure and reported separately, because it is a ranked
list whose coverage rate is ~1 %.

**Property (prompt).** `notable_body` renders the decision statistic — `measure.name = value` and,
for the similar generator, `margin = <known_bad_minus_good> (threshold 0)` — and renders nearest-known
items as numbers and family only (`known-bad 0.986 (kyoushi)` → `matched item 0.986 (kyoushi)`),
never the literal label words or the attack-step names.

**Change.** `_judge_block` gains the stratified block (the existing pooled figure stays for
continuity, renamed); `notable_body` gains a `measure` line and `_known_lines` drops
`label_kind`/`label`; `similar._make`'s `why` states the margin.

**Unit tests.** `test_judge_separation_is_reported_per_generator`,
`test_the_pooled_judge_auc_excludes_a_rank_list_generator`,
`test_the_notable_prompt_carries_the_measure_and_not_the_label`.

**Live proof.** Scoreboard on a fresh `_v2` run prints `judge auc_by_generator …` with a
per-generator table, `judge auc_pooled` over the declared stratum, and the `similar_to_known`
yes-rate as its own line. Acceptance: the pooled figure is stable when the similar generator's
budget changes (re-run with `--generators` without `similar_to_known`; the pooled figure must not
move by more than 0.02 — on the stored runs it currently moves from 0.151 to 0.300 on santos).

### Optional E8 — the unjudged tail (only if E7 shows it matters)

`judge_all` asks `pending[:budget]`, i.e. the head of merged order, so the judged set is
generator-biased by merge priority. If a measurement depends on the unjudged tail, sample it
stratified (per generator, proportional) instead of prefix. **Not required by any Round-2 acceptance**
— listed so it is not mistaken for part of E7.

---

## 7. Live proof matrix — what the orchestrator runs

Each row is one full hunt plus one scoreboard. Paths are the Round-2 ones; substitute the family.

```bash
# environment (names only; never source .env)
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables

# 1. the run (after E1/E2/E3/E4/E5 land)
uv run python -m $hunt --index hb_ait_santos_v2 --out coding_task/scratch/d3_proof/santos \
  --stage all --family santos \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,russell                       # expect EXIT=0, events_read > 0

# 2. the verdict
uv run python -m $hunt.scoreboard --out coding_task/scratch/d3_proof/santos \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --weights --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos

# 3. E0/E2 receipt facts (no Splunk)
uv run python - <<'PY'
import json, duckdb
p=json.load(open("coding_task/scratch/d3_proof/santos/progress.json"))["stages"]["behaviours"]
f=[r for r in p["files"] if r["path"].endswith("intranet.smith.santos.com-access.log")]
print("rows", sum(r["rows"] for r in f), "of", f[0]["events_available"])
print("hosts off-file", [r for r in f if r["host"] and r["host"] not in (r.get("hosts") or [])])
print("silent empties", [r for r in f if r["rows"]==0 and not r["reason"]])
con=duckdb.connect("coding_task/scratch/d3_proof/santos/behaviours.duckdb", read_only=True)
print("store intranet access rows", con.execute(
 "select count(*) from events where source_id like '%:access_combined' and host='intranet_server'").fetchone()[0])
PY

# 4. E3 (rung 1)
uv run python -c "import json;l=json.load(open('coding_task/scratch/d3_proof/santos/progress.json'))['stages']['behaviours']['localisation'];print(l['indexes'])"
```

**Pass/fail lines, per defect:**

| defect | line that must change | today (stored run) | target |
|---|---|---|---|
| D1 | `C0 ceiling … reachable` (+ the 3 lost web steps) | 11/21, 3,353 lines read | ≥12/21 with `attacker_http, dirb, wpscan` reachable; the line count rises as a consequence |
| D1 | store `access_combined` rows on `intranet_server` | 184 (santos) / 1,134 (kyoushi) / 204 (russell) | ≥1,000 / ≥1,700 / ≥725 |
| D1 | `progress.json` file rows with `rows==0 and reason==""` | 688 santos, 483 kyoushi, 770 russell, 602 botsv2 | **0** |
| D2 | `localisation.indexes[*].mechanism` | one entry per index, `indexed` | one entry per source; `accelerated` present on ≥1 family |
| D2 | any read receipt `coverage` | `scan` only | `accelerated` on ≥1 read |
| D3 | `C0 evidence absent` | `n/a` | `crack_passwords 44/44` (santos), `49/49` (russell) |
| D3 | step denominator | 21 / 22 | 20 / 21 |
| D4 | botsv2 `--stage all` | `events_read=0`, EXIT 1 in 721 s | `events_read>0`, EXIT 0 |
| D4 | botsv2 `notables` | `SimilarityError` | completes, `notables.jsonl` written |
| D4 | `searches.total` | 2,000 (ceiling hit) | ≤2,000 with every file read or declared |
| D5 | `judge auc_by_generator` | absent | printed per generator |
| D5 | pooled judge AUC without `similar_to_known` | 0.300 (santos), 0.628 (russell) | must equal the with-generator pooled figure ±0.02 |

---

## 8. What this plan does not do, and what would falsify it

**Not in scope / not claimed.**

- No production code, no Splunk configuration, no rebuild: this is the replan. The D5 half that is
  operator-owned (whether the acceleration summaries *should* cover the index's corners) is not
  settled here — E3 makes the guard honest per source and declares partial coverage; it does not
  change what Splunk summarised.
- The `_v2` war-room numbers are quoted from the four verdicts; this lane re-derived only what its
  own scripts read (composition, AUC bounds, span shortfalls, estate-map shapes, store row counts).
- The store-row targets (1,000 / 1,700 / 725) are the Round-2 verdicts' acceptance numbers
  **[REPORTED]**, not independently chosen here.
- The graded-file hour histograms (7,894 in 11:00–12:00, etc.) are the verdicts' live `tstats`
  results **[REPORTED]**; they are consistent with the 0-row receipts this lane verified.
- `linux_audit:exe` (D2's fourth example list) is untouched — a documented inventory budget
  decision, not a defect.

**What would falsify the diagnosis.** Each is checkable before writing code:

1. If `min(first)`/`max(last)` over wide sources were *inside* the recorded `accel_window`, defect 2
   would be a mis-built index, not a guard mismatch. It is outside by 2 s on all three families
   (§2.1).
2. If `similar_to_known` rows covered labelled lines at a normal rate, the AUC ceiling argument
   would not hold. They cover 5/300 (santos), 13/300 (kyoushi), 12/300 (russell) (§5.2).
3. If the graded file were on the anchor's host, santos's anchored rows would not be structurally
   empty. The localisation receipt says `hosts: 1` and the anchor is `inet-firewall`; the graded
   file's `hosts` is `['intranet_server']`, and no `access_combined` file is on `inet-firewall` at
   all (§1.4).
4. If the ledger's estate-map row's `rows` counted **paths**, E6 would be unnecessary. It counts
   `(sourcetype, source, host)` tuples — 4,626 against 89 paths (§3.2).
5. If `coverage` could be `"accelerated"` anywhere on the read path, defect 2b would be an
   observation problem only. `grep '"accelerated"'` over `hunt/` has no `RowSet` assignment (§2.2).

**Risks the reviewer should weigh.**

- E2 increases per-file discovery (one `tstats` per planned file-window) — ~90 requests on santos,
  ~180 on botsv2. That is cheap against 2,000 but it must be counted in E4's planner.
- E2's tail-slice guarantee is only as good as the file's `last`; a file appended after the run
  starts is bounded by the `end` of the index facts as before.
- E7 changes the *reported* number, not the model. It will make the Round-2 `_v2` judges look better
  than 0.151 without a single new call — that is the point, and it must be stated when the round is
  graded so the change is not read as a regression fix.
- E5 makes `similar` skip sources; on the tuned families the skip set must be empty, or a real
  coverage hole is being hidden. The receipt (`skipped_sources`) is the check.

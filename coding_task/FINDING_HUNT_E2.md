# FINDING — hunt replan E2: file-driven placement, host and head

Lane `lane/hunt-e2`, 2026-11-21. Implements slice E2 of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md`
§6 (`### E2`). No Splunk query and no hunt run was issued by this lane: every number below is a
plan replay through a fake executor over the **live E1 estate map** the orchestrator produced
(`/Volumes/data01/portal5_hunt/e1proof/santos/sources.json`, 21 `access_combined` files, all 21
carrying `first`/`last`), or a unit-test fixture. The live comparison is the orchestrator's.

Scratch (gitignored): `coding_task/scratch/e2/` — `replay_plan.py` and a `git archive HEAD`
extract (`head/`) used for the failing-first run.

## What changed (`portal/modules/security/core/hunt/notables/sample.py`)

- **Windows.** A file with its own `first`/`last` is now sliced over **its own** range:
  `_file_windows` → `_span_windows(item.first, item.last, count)` with `count =
  _file_window_count(...) = max(FILE_READ_MIN_WINDOWS, ceil(min(events, per_window)/per_read))`.
  `_span_windows` is the helper `source_windows` already used (same `+1e-6` tail widening), so the
  file's tail slice is `[last - width, last + ε)` — its last event is always inside a planned
  read. The caller's source schedule is used only when the file has no range (`last == 0.0`).
- **Host.** `_plan_files` decides per file: a file whose `hosts` are known and do not contain the
  anchor host is **not issued** — it is receipted `reason: host_mismatch` with `host: ""` and
  recorded through `_omit_file` so the ledger sees it. A file whose `hosts` are unknown cannot be
  proven off the anchor host, so it is read with **no host filter** (`""`); the old
  `on_host or facts.files` fallback — which re-read every file with the anchor host they are not
  on — is gone. `FileRead.host` is now always `""` or a host in `FileRead.hosts`.
- **Head.** `_file_head` is density-based: `min(per_read, events_in_window)`, where
  `events_in_window` is a `tstats count where index=<i> source=<path>` over that window's bounds
  (`_window_events`), cached per `(path, window)` so a repeated window costs nothing. For a file's
  **own** windows the cap is `per_window` (one read per distinct slice, no subdivision); for the
  fallback source schedule it stays the subdivided `per_read = per_window // sub_windows`. A count
  that cannot be read leaves the cap open (`per_read`) rather than starving the read. The
  source-share budget (`_file_budget`) is deleted — it was the 144 / 1,403-row cap in §1.5.
- **Ordering.** Each file read is `... | sort - _time | head <n>`, so the cap keeps the newest
  rows of the window instead of arrival order.
- `_spread_windows` (fallback path only) now always keeps the tail window.

`behaviours.py` is **unchanged**, and I want that on the record: `_read_anchor_files` supplies the
anchor host and the anchor window, and both rules it depends on are enforced inside `read_files`,
which it calls. With a file that has its own range, the anchor window it passes is now superseded
by the file's own slices (E2's Change list, item 1) — only its host is used. Tests for both host
outcomes are in `tests/unit/test_hunt_notables_sample.py`.

## Offline proof

### 1. Failing first — HEAD and this lane on the same four fixtures

`coding_task/scratch/e2/failing_first.py` against `git archive HEAD portal config`
(`coding_task/scratch/e2/head`) and against this tree, same script, same fakes:

```
HEAD (pre-E2)                                  lane (E2)
1 windows: [(0,1666),(1666,3333),(3333,5000)]  [(3000,3333),(3333,3666),(3666,4000)]   file first=3000 last=4000
2 receipts: [('/a','web1',''), ('/c','web1','')]  [('/a','web1',''), ('/b','','host_mismatch'), ('/c','','')]
2 issued:   ['"/a"', '"/c"']                      ['"/a"', '"/c"']
3 heads:    [20, 20, 20]  3 rows: 0              [1, 1, 2500]  3 rows: 2500
4 windows:  [(0, 4000.000001)]                   [(1000,2000),(2000,3000),(3000,4000.000001)]
4 fallback starts: [0]                           [0,1333,2666,3333]
```

Four failures, one per property: the windows are the source's (all before the file's `first`), the
off-host file gets **no receipt at all** while a file with unknown hosts inherits the anchor host
(`'/c','web1'`), the head is the share (20 = `ceil(6000/1e6 × 2500 × 4) / take`, zero rows
reached), and the read is one whole-source-span read instead of the file's own slices.

### 1b. HEAD on the live E1 estate map

`coding_task/scratch/e2/replay_plan.py` over the live santos `access_combined` facts
(`per_window=2500`, `sub_windows=2`, fake executor records the plan and returns no rows):

```
HEAD  uniform schedule (4 source slices x 2): requests=66
  graded host='' window=1642085133..1642131755
  graded host='' window=1642178378..1642225000
  graded host='' window=1642318245..1642364868      <- all three end before the file's first event
HEAD  anchored read on inet-firewall (4 real R2 anchor windows): requests=63
  graded host='inet-firewall' window=1642172400..1642176000 hosts=['intranet_server']
  ... 63 receipts, 63 with a host the file is not on, 0 host_mismatch skips
```

The graded file's own range on that live map is `1642400738..1642451200`; every HEAD window above
ends at or before `1642364868`.

### 2. This lane's tree, same real map

```
uniform schedule: row reads=55 count queries=51
  graded 1642400738.0 .. 1642417558.6666667
  graded 1642417558.6666667 .. 1642434379.3333333
  graded 1642434379.3333333 .. 1642451200.000001   <- tail ends at last + 1e-6
  distinct windows per file: [1, 3];  receipts with an off-file host: 0

anchored read on inet-firewall: row reads=0 receipts=21 host_mismatch skips=21
  graded host='' reason='host_mismatch' hosts=['intranet_server']
```

So on the live santos map: the graded file's windows move from the source's (four of which end
before it starts) onto its own 06:25–20:26 range; the 63 host-mismatched reads become 0 reads and
21 declared `host_mismatch` skips; and `FileRead.host ∈ ("", *hosts)` holds for every receipt.

### 3. What the replay cannot show

The fake answers no data, so `rows` and the density counts are 0 there — the plan and the request
count are the only things read from the live map. Property 3 (`rows ≥ min(events, per_window)`) is
pinned by `test_a_files_head_reflects_the_windows_density_not_its_source_share`: a 6,000-event file
inside a 1,000,000-event sourcetype with all of it in one window reads at `head 2500` and returns
2,500 rows, where the share formula gives `ceil(6000/10⁶ × 2500 × 4) / 3 = 20` per read (HEAD's
observed `[20, 20, 20]`, 0 rows).

### 4. Tests — 4 added (one per acceptance property), net **+171/−1** (`tests/unit/`, ~35 of it the
shared `_DensityExecutor` fake that answers `source=`, `host=`, time bounds and `| tstats count`)

| test | property pinned |
|---|---|
| `test_a_files_windows_land_on_the_files_own_burst_not_the_sources` | read windows start at the file's `first`, stay inside its `last + ε`, and one contains its burst |
| `test_a_file_is_never_read_with_a_host_it_is_not_on` | a file not on the anchor host is skipped `host_mismatch` with `host: ""`; a file with unknown hosts is read with no host filter; no read carries an off-file host |
| `test_a_files_head_reflects_the_windows_density_not_its_source_share` | the dense window's cap is its own count capped at `per_window`, and the file's rows reach `min(events, per_window)` |
| `test_the_last_slice_of_a_file_is_always_planned` | the file's own tail slice `[3000, 4000+ε)` is planned, and a no-range file keeps the source schedule's last window |

`_FileExecutor` now answers `| tstats count`, so the existing per-file read test exercises the
density head instead of silently reading a 0-count. Its old "source share" row assertion
(`<= per_window × windows + files × 2`) became the per-read cap bound (`<= per_window × windows ×
files`) plus a per-file check (`a00` = 200 rows over its two windows).

### 4b. Gates

```
uv run pytest tests/unit/ -q                      -> 3067 passed, 22 skipped
uv run ruff check .                               -> All checks passed!
uv run ruff format --check .                      -> 1737 files already formatted
python3 scripts/complexity_report.py --gate       -> GATE OK (all gated totals within ceilings)
uv run mypy portal/modules/.../sample.py          -> 0 errors in sample.py (27 pre-existing in
                                                     tests/benchmarks reached transitively)
```

`read_files` is 95 lines (was 96 before the change; the plan loop moved to `_plan_files`).

## Live proof (orchestrator)

**1. Rebuild one family's estate map (E1's map already lives at the path below) and run
behaviours.** Reuse the stored santos window (`start 0`, `end 1795279317`):

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out /Volumes/data01/portal5_hunt/e2proof/santos \
  --stage cards,behaviours --start 0 --end 1795279317
```

**2. Read the graded file's receipts and its rows — the round's core measurement.**

```bash
python3 - <<'PY'
import json
p = json.load(open('/Volumes/data01/portal5_hunt/e2proof/santos/progress.json'))
b = p["stages"]["behaviours"]
graded = "/apache2/intranet.smith.santos.com-access.log"
rows = [r for r in b["files"] if r["path"] == graded]
for r in rows:
    print(r["host"], int(r["window_start"]), int(r["window_end"]), r["rows"], repr(r["reason"]), r["hosts"])
print("graded rows:", sum(r["rows"] for r in rows), "per_window:", b["per_window"])
print("off-host receipts:", [r for r in b["files"] if r["host"] and r["host"] not in r["hosts"]])
PY

uv run python - <<'PY'
import duckdb
con = duckdb.connect('/Volumes/data01/portal5_hunt/e2proof/santos/behaviours.duckdb', read_only=True)
print(con.execute("select count(*) from events where source_id like '%:access_combined' and host='intranet_server'").fetchone())
PY
```

Worked: `sum(rows)` for the graded file ≥ `per_window` (2,500 on these estates; it carries 7,786
labelled lines), every receipt's `host` is `""` or in its own `hosts`, `off-host receipts: []`, and
the duckdb count for `access_combined` on `intranet_server` is ≥ 1,000. Did not work: rows still in
the old `72`-row range, or any receipt carrying `host='inet-firewall'` for that file.

**3. The scoreboard reachability** (§6 E2 live proof (c)): `C0 ceiling` reachable ⊇ the control's
12/21 with `attacker_http, dirb, webshell_cmd, webshell_upload` reachable again.

## UNPROVEN

- That a live `tstats count where index=… source=<path>` returns one row per window (rather than
  no row when the window is empty). If it returns none, `_window_events` treats the window as
  unknown and the cap stays at `per_window` — safe, but the density then does no work on sparse
  windows. Only a live run shows which.
- That Splunk accepts `| sort - _time | head n` on a file-scoped search at the volumes here
  (2,500 rows) inside `query_seconds`.
- That `sum(rows) ≥ per_window` holds live for all three graded files — the plan replay shows the
  windows land on their ranges, not that the rows come back (santos's burst straddles a slice
  boundary; see OPEN).
- Every number in the replay is the *plan* the changed code produced from the live E1 map; no row
  count, `searches` total or scoreboard figure was produced by this lane.

## OPEN / RISK

- **`behaviours.py` untouched.** `_read_anchor_files` supplies the anchor host and window; the new
  rules live in `read_files`. If E2 intended the anchored read to stop passing an anchor window at
  all (it is now ignored for files that have a range), that is a two-line follow-up, not a defect I
  could see a property for.
- **Request cost and timing rise where the map has ranges.** santos `access_combined`: 55 row reads
  + 51 density counts = 106 requests, against 66 at HEAD — the density count is ~one per
  file-window, which is what §6 budgets for but E4 has not bounded yet. Where the map has **no**
  ranges (every stored Round-2 run, botsv2 included) the plan *shrinks*: 3 windows per file instead
  of the old budget-driven 3–24, so botsv2's 181 files project to ≈1,086 requests (181 × (3 reads +
  3 counts)) against the 1,813 behaviour reads of run B — arithmetic from the stored file count,
  not a measurement.
- **The density counts are issued serially, before the first row read.** `_plan_files` resolves
  every window's count in the calling thread, so botsv2's 181 files mean ~543 discovery requests in
  sequence (measured ratio: 51 counts for 21 santos files) ahead of any evidence read; at a 0.5 s
  Splunk round trip that is ~4.5 min of the 720 s job clock, and if the request budget runs out
  mid-plan every later read is receipted with the budget's reason. Parallelising the plan counts
  (the executor already takes concurrent reads) or folding them into one per-file `span` query is
  the obvious next move — I did not take it because E4 owns the request budget and the brief did
  not ask for it.
- **The densest *hour* can straddle a slice.** On the live santos map the graded file's 14h02m
  range cuts into 3 slices of 4h40m; the reported burst 11:00–12:00Z sits 358s in slice 1 and the
  rest in slice 2. A window contains the burst, but no single window contains the whole hour, so
  §6's property 1 ("a read contains the file's densest hour") is met only in the rows sense, not
  literally. Guaranteeing it needs one extra `tstats … by _time span=3600` per file (which would
  also replace the per-window counts at ~1/3 the requests) — a deliberate trade I did not take
  without the brief's word.
- Empty-window heads are `1` when the live count comes back as a zero row; on a zero-row window
  that is one wasted search per file-window, not a lost row.
- The 4 new tests use a fake that honours `source=`, `host=` and time bounds; they do not model
  `sort - _time` ordering (the fake already returns newest-first), so the ordering clause is covered
  only by inspecting the emitted query string.

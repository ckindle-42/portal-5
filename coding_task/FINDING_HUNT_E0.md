# FINDING — Hunt E0: receipt honesty (measurement plumbing)

**Lane:** `lane/hunt-e0` · **Slice:** E0 of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6 ·
**Base:** `main` at `614368b30`, merged with `origin/main` at `0b63ea782` (E1, E3, E5, E6),
then at `444bed720` (E7), then at `9bf141ef6` (E2) · **Scope:** `sample.py`, `executor.py`,
`behaviours.py`, two unit test files. No live Splunk run, no `launch.sh`, no `.env`, no held-out
set.

**Merge (E1/E3/E5/E6, then E7, then E2):** the conflicts were the `sample.py` import list
(E1–E7 merge), one test hunk in `test_hunt_notables_sample.py` (E1–E7 merge), and — for E2 —
the `FileRead` construction in `read_files` plus the tail of the same test file; every conflict
kept every side. Against `origin/main` this lane's diff is the six files named at the top, and the
added/removed lines of `sample.py` and `test_hunt_notables_sample.py`
outside those hunks are byte-identical to the pre-merge patch — nothing of E1's per-file ranges,
E2's file-driven placement (`file_host`, `host_mismatch`, density head, `sort - _time`), E3's
per-source localisation (`accelerated_partial`, `covered_window`, `scanned_window`), E5/E6's
notables contract or E7's judge separation was dropped.

## What the slice asked for, and what the code now does

| # | acceptance property | change |
|---|---|---|
| 1 | every planned `(source, file, window)` read with `rows == 0` carries a non-empty `reason` (`empty_window`) | `sample.py:863` `FileRead(..., reason or (EMPTY_WINDOW if not rows else ""), ...)` |
| 2 | a read refused by the shared request budget emits one `ledger.jsonl` row with `reason: request_budget_exhausted` | `executor.py:378-417`: the observer call and `record_rows` moved into a `finally`, with a `refused` flag set by the budget exception; `_reserve` keeps raising with `budget.exhausted` as the reason, so `str(exc)` is `request_budget_exhausted` |
| 3 | a `RowSet` from a covering summary reports `coverage: accelerated` (+`accel_window`), from a scan `coverage: scan` | `sample.py:1021-1044` `read_anchors(..., coverage=...)`; `behaviours.py:904-1040` `_merge_anchored(..., coverage, accel_window)`; `read_behaviour_source`/`_read_anchored_source` take `coverage`; the scheduled caller passes `located.coverage`/`located.accel_window` (`behaviours.py:1437`) |

Three consequences handled rather than left implicit:

- **`files_omitted` keeps its old meaning.** A zero-row read is still a read; only a declined
  read is omitted. `sample.file_omitted()` and `behaviours._files_omitted()` exclude
  `empty_window` from the omission count, so a routed-but-empty file does not turn
  `files_routed 21 / files_omitted 0` into `files_omitted 21`.
- **A mid-stream budget error keeps `reason: censored`.** `executor.py:405` records
  `censored` when rows had already arrived and the budget reason when nothing was returned;
  `executor.py:390` keeps the same label for a failed read whose observer now runs in the
  `finally`. This preserves
  `tests/unit/test_hunt_run_injection.py::test_ledger_records_partial_rows_before_a_search_budget_error`.
- **A refused file read can be two ledger rows after E2.** E2's plan issues a per-file,
  per-window `| tstats count` density probe before each read, and that probe is a read too:
  under an exhausted budget it is refused and declared like any other, so
  `test_a_budget_refused_read_writes_a_ledger_row` now expects one row per issued read
  (probe + window read, both `request_budget_exhausted`). No request is silent; the count of
  refusal rows tracks the count of issued reads, not the count of files.

## Tests (the regression net — one per property, plus the executor property)

- `tests/unit/test_hunt_notables_sample.py::test_a_zero_row_file_read_declares_an_empty_window`
- `tests/unit/test_hunt_notables_sample.py::test_a_budget_refused_read_writes_a_ledger_row`
- `tests/unit/test_hunt_notables_sample.py::test_a_read_from_a_covering_summary_reports_accelerated_coverage`
- `tests/unit/test_hunt_executor.py::test_the_observer_sees_a_request_budget_refusal`

Net test lines: E0's own four tests plus the shared `_wide_file_facts`/`_RefusingSearch`
helpers; E2's blocks sit beside them unchanged.

## Offline proof (the only evidence this lane can produce)

```
$ PYTHONPATH=. uv run python coding_task/scratch/e0/offline_proof.py
property_1_empty_window:
  files: [{"path": "a", "rows": 0, "reason": "empty_window", ...}]
  files_indexed: 1, files_omitted: 0, property: true
property_2_budget_ledger:
  file_rows: [{"path": "a", "rows": 0, "reason": "request_budget_exhausted", ...}]
  ledger: [{"reason": "request_budget_exhausted", "rows": 0,
            "query": "| tstats count where index=\"ix\" source=\"a\"", ...},
           {"reason": "request_budget_exhausted", "rows": 0,
            "query": "search index=\"ix\" source=\"a\" | sort - _time | head 100", ...}]
  every_issued_read_declared: true, rows_for_density_probe: 1, rows_for_window_read: 1
property_3_coverage:
  coverage: "accelerated", accel_window: [0.0, 600.000001], from_localisation: true
```

(Scratch is gitignored under `coding_task/scratch/`; it drives the real production functions
through a fake `Search`, not a hand-built record shape.)

Gates, on this merged tree (post `origin/main` @ `9bf141ef6`):

```
$ uv run pytest tests/unit/test_hunt_notables_sample.py tests/unit/test_hunt_notables_behaviours.py tests/unit/test_hunt_executor.py -q
55 passed in 0.66s

$ uv run pytest tests/unit/ -q
3079 passed, 22 skipped, 2 warnings in 75.32s (0:01:15)

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
1737 files already formatted

$ python3 scripts/complexity_report.py --gate
[complexity] GATE OK — totals within the declared ceilings:
  data_lines: 12,291 <= 13,370 (headroom 1,079)
  god_lines: 68,657 <= 71,202 (headroom 2,545)
  unwired_scripts: 25 <= 25 (headroom 0)
  identical_pairs: 0 <= 0 (headroom 0)
  committed_blob_bytes: 1,792,894 <= 1,873,616 (headroom 80,722)
```

`uv run mypy portal/` on this shared venv reports 650 pre-existing errors in followed
`scripts/`/`portal_channels/`/`tests/` imports (via `portal/modules/security/core/_data.py` →
`tests.benchmarks…`); **zero errors are in `portal/`** (`uv run mypy portal/ | grep -c '^portal/'`
→ `0`) and none are in a changed file. That is an environment/pre-existing condition, not this
diff (worker contract §10: a count of hundreds means the venv, not the repo).

## ORCHESTRATOR RUNS — live proof

Run any family as usual, then read the run directory. `OUT` is the family run dir, e.g.
`/Volumes/data01/portal5_hunt/hunt_proof_r3_santos/v3/santos`.

```bash
OUT=/Volumes/data01/portal5_hunt/<run>/<family>
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
progress = json.loads((out / "progress.json").read_text())
stage = progress["stages"]["behaviours"]
files = stage.get("files") or []
silent = [r for r in files if not r.get("rows") and not r.get("reason")]
print("file rows", len(files), "| zero-row with no reason", len(silent))
print("files_omitted", stage.get("files_omitted"), "| searches", stage.get("searches"))
print("coverage by source", sorted({r.get("coverage") for r in stage.get("receipts") or []}))
print("localisation", [(i.get("index"), i.get("mechanism"), i.get("coverage"))
                        for i in (stage.get("localisation") or {}).get("indexes") or []])
reads = [json.loads(line) for line in (out / "ledger.jsonl").read_text().splitlines()]
print("ledger rows", len(reads), "| refused by request budget",
      sum(1 for r in reads if r.get("reason") == "request_budget_exhausted"))
PY
```

**It worked** when:
- `zero-row with no reason` is **0** on every family (property 1);
- `refused by request budget` is **≥ 1** whenever `searches.total` (or the progress
  `exhausted_reason`) reports `request_budget_exhausted` — and those rows are the only ledger
  rows with `rows: 0` + that reason, both the `| tstats` density probes and the `search … | head`
  window reads counted (property 2);
- at least one `receipts[].coverage` is `accelerated` on a family where
  `localisation.indexes[].coverage` is `accelerated`, and `accel_window` is non-null there
  (property 3). On santos/kyoushi/russell rung 1 currently fires 0 wide sources (deep dive
  §2.1 says the upper bound is 14/15, 9/16, 15/16 only under per-source localisation, E3), so
  today the honest expected reading is `accelerated` only where the index-wide localisation
  itself was accelerated; if it never is on the graded estates, property 3 is proven by the
  unit test and the live line should read `scan` consistently rather than a false
  `accelerated`.

**It did not work** if any `file rows` entry still has `rows == 0, reason == ""`, if the
ledger has no `request_budget_exhausted` row in a run whose `behaviours.searches` hit the
ceiling, or if a receipt says `coverage: accelerated` with a null `accel_window`.

Note for reading the cost block: refused reads are now ledger rows, so `ledger.jsonl` rows
(`scoreboard:search_requests`) can exceed the issued-request count in `stages.behaviours.searches`
by exactly the number of budget refusals. That is the E0 contract ("a refused read is
declared"), not a second request; the budget's own `requests` counter remains the cost. After
E2 the ledger also carries one density probe (`| tstats count where …`) per file and window;
those were issued requests, so they are both a row and a cost.

## Unproven

- Every live line above: this lane ran no Splunk query and no family run.
- `coverage: accelerated` on a real family: depends on rung 1 firing for an index; only the
  propagation from `Localisation` is proven here. E3's per-source localisation is merged, so a
  live receipt can now also read `accelerated_partial`, which this slice carries through
  unchanged.
- The ledger row count/ordering under concurrency: the test drives one file; the live run
  drives thousands through `ThreadPoolExecutor`. The observer path is the same, but ordering
  and counts at scale are unverified here.
- The merged read schedule adds one `| tstats count` probe per file and window (E2), so a live
  ledger's row counts now include those probes and a budget-exhausted family will emit roughly
  two refusal rows per planned file read rather than one. That arithmetic is reasoned from the
  code, not measured.
- `files_omitted` on a live run: unit-shaped only; the live receipt must be read to confirm it
  stays `0` for routed-but-empty files.

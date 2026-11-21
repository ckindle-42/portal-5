# FINDING — Hunt Replan E4: budget scope and a planned request ceiling

Slice **E4** of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6 (`### E4 — budget scope and a planned
request ceiling`), read together with §4 (`Defect 4 — botsv2's three run-path defects`, L1/L3).

Lane branch: `lane/hunt-e4`. Nothing here is a live result: the code is complete and the offline
gates are green, and the orchestrator owns the botsv2 run below.

## The two properties, and where each now holds

**P1 — one stage's wall clock is not another stage's read budget.**
`HuntBudget.restart_clock()` (`executor.py`) re-bases `started` to `time.monotonic()` and clears
a spent **deadline** sentinel (`job_deadline_exceeded` or `<stage>_stage_deadline_exceeded`).
`behaviours_stage` (`run.py`) calls it at the head of the stage, before the inventory and
behaviour reads. The request, cell, event and discovery counters are untouched, so the 2,000
request ceiling and the row ceilings stay global — exactly the split §4.1 asks for. `cards` is
model-bound and issues no read, so its wall time no longer lands in behaviours' read clock.

The stage receipt now carries the measurement the live proof needs:

```json
"clock": {"job_seconds": 720.0, "remaining_s": 718.4, "requests_spent": 96}
```

**P2 — the behaviour read plan is budgeted before it is issued.**
`read_files` (`sample.py`) builds its per-`(file, window)` plan as before, then filters it:

```python
requests, dropped = plan_within_requests(
    requests,
    _remaining_requests(executor),
    priority=lambda request: (-request[0].events, request[0].path, -request[2]),
)
```

`plan_within_requests` (`executor.py`) is a pure function: it keeps the highest-priority
`remaining` entries (largest file first, newest window first, plan index as the tie-break) and
returns the rest **in plan order**. Each dropped window is declared twice, the way a refused read
already is:

- receipt: one `FileRead` row per dropped `(file, window)` with `reason:
  request_budget_exhausted` (`progress.json:stages.behaviours.files`), and
- ledger: one `ledger.jsonl` row through `executor.record_skipped_read(...)`, which is the
  observer path E0 makes visible.

The filter is exact — it counts the reads it is about to issue, not a file estimate — so the
ceiling is spent rather than guessed at, and `len(planned) ≤ remaining` holds by construction.
Across sources, `collect_behaviours` schedules peaked/wide sources first (`_read_priority`:
`-count_cv`, then total file bytes, then index+sourcetype), so a starved stage spends what is
left on the sources whose files are the evidence.

## What changed

| file | change |
|---|---|
| `portal/modules/security/core/hunt/executor.py` | `HuntBudget.restart_clock()`, `HuntBudget.remaining_requests()`, `REQUEST_BUDGET_EXHAUSTED`, pure `plan_within_requests()` |
| `portal/modules/security/core/hunt/notables/sample.py` | `read_files` filters its own plan against the unspent ceiling and declares each dropped window (`_omit_window`, `_remaining_requests`); `_omit_file` kept and delegating to `_omit_window` |
| `portal/modules/security/core/hunt/notables/behaviours.py` | `_read_priority` + the schedule sorted by it |
| `portal/modules/security/core/hunt/notables/run.py` | `restart_clock()` at the head of `behaviours_stage`, and the `clock` receipt block |
| `tests/unit/test_hunt_executor.py` | `test_a_slow_model_stage_does_not_consume_the_read_clock` |
| `tests/unit/test_hunt_notables_behaviours.py` | `test_the_read_plan_never_exceeds_the_remaining_request_budget`, `test_a_window_dropped_by_the_planner_is_declared` |

Net test lines over `origin/main`: **+139** (35 executor, 104 behaviours — the behaviours file
carries the shared `_BudgetExecutor` / `_budget_facts` harness used by both of its tests). Three
tests, one per §6 E4 acceptance property.

**Scope note.** §6 E4 names `read_files`' plan, and `read_files` lives in `sample.py`, which the
brief's file list does not include (it says `behaviours.py` — read planner). The filter has to sit
where the plan is built, so `sample.py` is touched: one import, one two-line filter, and the
`_omit_window` generalisation/`_omit_file` delegate. No other behaviour of `read_files` changes.
Rows E2 rewrite the same function; after the rebase the filter sits on E2's flattened
`(file, host, start, end, head)` request list and the hunks here are the filter/`dropped` loop and
the omit helpers only.

## Rebase onto `origin/main` (E0–E3, E5–E7)

Two textual conflicts, both on the E2 rewrite of the read planner:

- `behaviours.py` — E4's `sorted(..., key=_read_priority)` on the schedule, E2's
  `anchors_by_index` → `anchors_by_source` rename and per-source localisation. Resolved by keeping
  E2's `anchors_by_source` block and E4's sort (`_read_priority` itself auto-merged).
- `sample.py` — E4's inline plan/filter vs E2's extracted `_plan_files`/`_file_reads` plan with a
  per-request `file_host`. Resolved by keeping E2's `_plan_files` structure and applying E4's
  `plan_within_requests` step to the flattened 5-tuple request list; the omit helper keeps E4's
  `_omit_window(..., start, end, ...)` and `_omit_file` now delegates to it (E2 calls it for
  `host_mismatch` / `read_files_cap`).

**E2's density probe shares the request counter (open, see below).** `_file_reads` issues one
`| tstats` probe per planned window to size its `head` *before* the filter runs, so the probes are
spent from the same 2,000-request ceiling first. The filter is still exact over the evidence reads
it keeps and each drop is still declared, but a starved file source can spend what is left on
probes and then have every evidence window dropped. Priced properly, the probe is a cost of the
plan and must be restricted to kept windows — that is a change to E2's planner, not a rebase
resolution, so it is reported rather than made here.

## Offline proof (run by this lane, post-rebase onto `origin/main`)

```bash
uv run pytest tests/unit/test_hunt_executor.py tests/unit/test_hunt_notables_behaviours.py \
  tests/unit/test_hunt_notables_sample.py -q
# 58 passed

uv run pytest tests/unit/ -q
# 3082 passed, 22 skipped

uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 1737 files already formatted
python3 scripts/complexity_report.py --gate
# [complexity] GATE OK — data_lines 12,291 <= 13,370; god_lines 68,678 <= 71,202;
#   unwired_scripts 25 <= 25; identical_pairs 0 <= 0; committed_blob_bytes 1,792,894 <= 1,873,616
```

What the three tests actually pin down (offline, mocked executor — a merge gate, not evidence):

- `test_a_slow_model_stage_does_not_consume_the_read_clock` — a budget whose clock is 600 s
  stale, whose deadline sentinel is already spent, and whose request counter is at 17; after
  `restart_clock()` the read succeeds, `job_remaining() > 59`, and `queries == 18` (the ceiling
  advanced by exactly one request, it did not reset).
- `test_the_read_plan_never_exceeds_the_remaining_request_budget` — a 20-file source (4 windows
  per file after E2's `_spread_windows`, an 80-read plan) at remaining 0/10/20/30/40/200 keeps at
  most that many evidence reads each time, and at 40 the ten largest files are the ones kept.
  Density probes are excluded from the count because they are spent before the filter sees the
  ceiling (see the rebase note).
- `test_a_window_dropped_by_the_planner_is_declared` — at remaining 40 the ten smallest files'
  windows come back as receipt rows with `reason: request_budget_exhausted`, and the executor's
  `record_skipped_read` observer saw exactly one row per dropped window with the same reason.

## ORCHESTRATOR live proof (botsv2, `--stage all`)

```bash
# names only — never source .env
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY

uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out coding_task/scratch/e4_proof/botsv2 --stage all
```

Read the receipt (no Splunk):

```bash
uv run python - <<'PY'
import json
p = json.load(open("coding_task/scratch/e4_proof/botsv2/progress.json"))["stages"]["behaviours"]
print("clock", p.get("clock"))
print("events_read", p.get("events_read"), "searches", p.get("searches", {}).get("total"))
files = p.get("files") or []
print("files", len(files), "budget-dropped", sum(1 for r in files if r.get("reason") == "request_budget_exhausted"),
      "cap-dropped", sum(1 for r in files if r.get("reason") == "read_files_cap"))
print("winhostmon", [(r["path"], r["rows"], r["reason"]) for r in files if "winhostmon" in r["path"]])
PY
grep -c '"request_budget_exhausted"' coding_task/scratch/e4_proof/botsv2/ledger.jsonl
```

**Pass** — EXIT 0; `stages.behaviours.clock.remaining_s ≥ 715` (job_seconds 720, −5 tolerance)
whatever the cards stage took; `events_read > 0`; no `HuntDeadlineExceededError` in the run log;
`searches.total ≤ 2000`; every `winhostmon` row either has `rows > 0` or a non-empty `reason`; the
ledger's `request_budget_exhausted` count equals the receipt's budget-dropped count (before E0
lands, refusals raised inside the executor still leave no ledger row — a count of 0 there with a
receipt count of 0 is the expected shape, a receipt count > 0 with a ledger count of 0 is not).

**Fail** — `clock.remaining_s` near 0 or absent, `events_read == 0`, `searches.total > 2000`, a
`winhostmon` row with `rows == 0` and an empty `reason`, or a file row whose reason is
`job_deadline_exceeded` (the clock never restarted).

## Not claimed / limits

- **Planning is per `read_files` call, not a global reservation.** Sources are read concurrently
  (up to `HUNT_SPLUNK_CONCURRENCY`, default 8); two calls that plan at the same instant each see
  the same `remaining_requests()` and may over-plan by up to one source's plan each. The
  executor's per-read refusal still bounds what is actually issued, so the ceiling is never
  exceeded — but the declaration is exact per call and best-effort in aggregate. Making it a hard
  reservation would need a counter reservation inside the executor; not done here.
- **Fileless sources are not filtered.** `read_files` falls back to `read_windows` when a source
  has no indexed file rows, and that path is untouched (it is E2's, and it issues a bounded
  12×2 windows per source). A stage spent to the ceiling by such a source would still be refused
  mid-read rather than planned out.
- **`restart_clock` is called only for `behaviours`** (§6 E4 says "at the head of behaviours").
  `notables`, `relate` and `judge` keep the shared clock; the judge has its own budget
  (`JUDGE_STAGE_DEADLINE_SECONDS`).
- **The 0-request case is silent in the ledger.** A source whose whole plan is dropped declares
  every window in the receipt and in the ledger, but `events_read` for it is 0 with no separate
  "source dropped" row; the per-window rows are the record.
- **`RowSet.windows` still counts the planned schedule**, not the issued windows, so a partly
  dropped plan reports the planned count while `files` names what was actually read. E0 owns the
  receipt-honesty pass over those fields.
- `plan_within_requests` is written in PEP 695 generic syntax because ruff's `UP047` forbids the
  `TypeVar` form here; `notables/stage2.py` already uses the same syntax in this tree, while both
  Dockerfiles are `python:3.11-slim`. Pre-existing, not introduced here, flagged for the reviewer.
- The file-size priority uses `IndexFile.events` as the size proxy (the only size `read_files`
  has). E2's density-based head does not change the ordering.

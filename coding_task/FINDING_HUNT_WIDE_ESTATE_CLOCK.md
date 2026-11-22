# FINDING: Wide-Estate `botsv2 --stage all` Deadline Overflow — E2 Serial Density Probes + Sticky `relate` Clock

Lane: `lane/hunt-wide-estate-clock` · 2026-11-21 · status: fix implemented, offline-verified, live run pending (orchestrator).

## Symptom (measured live, pre-fix)

Solo uncontended `botsv2 --stage all` on a quiet Splunk box exited 1 at `relate` with
`HuntDeadlineExceededError: job_deadline_exceeded` (`behaviours` read only 15,969 events,
`wall=468.5s` + `inventory ~260s` > the 720 s job clock).

## Root causes

1. **E2 serial density probes** — `sample.py::_plan_files` → `_file_reads` → `_window_events`
   issued one serial `| tstats count where index=… source=<path>` per `(file, window)`
   **before** `plan_within_requests` filtered the plan and before any evidence read ran.
   On a 181-file estate that is 221–543 serial Splunk queries (~300+ s of the 720 s clock)
   and request budget spent ahead of evidence reads: with the old ordering, a ceiling of N
   requests could be consumed entirely by counts, leaving zero evidence reads.
2. **Sticky clock into `relate`** — `restart_clock()` was called at `behaviours` only, so a
   `behaviours` stage that touched 720 s left `budget.exhausted="job_deadline_exceeded"`
   sticky; `relate`'s first read raised at `executor._reserve` before `judge` could run.

## Fix

1. `executor.py::plan_within_requests` gains an optional `cost:` callable. The plan is now
   priced in requests (a probed read costs 2: its density probe plus the evidence read) and
   filtered against `budget.remaining_requests()` **before** any probe is issued. With all
   costs 1 it is byte-for-byte the old behaviour.
2. `sample.py::read_files` rebuilds its flow: `_plan_files`/`_file_reads` now produce a
   bounds-only plan `(start, end, cap, needs_probe)`; dropped windows are declared
   (`request_budget_exhausted`) with no probe; `_density_counts` issues the kept windows'
   probes **concurrently** (one thread per window, bounded by `budget.concurrency`, the same
   `_read_range` error-tolerant idiom the evidence reads use); `_headed_requests` turns the
   probed counts into the final density heads. `executor.read_many` was considered and
   rejected: it propagates one `HuntBudgetExceededError` through the whole batch, discarding
   every other probe's result, where the old serial path recorded a per-probe reason.
3. `relate.py::relate_stage` calls `executor.budget.restart_clock()` at the executor line
   (the head of the stage), mirroring `behaviours_stage`: relate's wall clock starts fresh,
   deadline-based exhaustion clears, and the global request counters stay untouched.

Note: the brief names `run.py`/`__main__.py` for fix 2; the stage function lives in
`relate.py::relate_stage`, which is the single entry both `__main__.py::_run_relate` and
`relate.py::main` go through — the fix sits where every relate invocation passes.

## Invariants preserved (E0/E1/E2/E4)

- `host_mismatch` / `read_files_cap` skips: unchanged, declared before any probe.
- `empty_window`: a read issued and returned nothing still declares `empty_window`.
- `request_budget_exhausted`: every window the priced plan drops is declared through
  `record_skipped_read` with `request_budget_exhausted`; the probe it would have spent is
  never issued (this is the changed ledger shape — see test notes).
- Newest-first `| sort - _time | head N` evidence reads: unchanged.
- Density-based head: unchanged — `_file_head(count, cap)`, unknown counts still fall back
  to the planned cap.

## Test evidence (offline; live proof is the orchestrator's)

- New: `test_windows_dropped_by_the_request_ceiling_issue_no_density_probe` — with a
  4-request ceiling over 6 probed windows, exactly 2 probes (both for the highest-priority
  file) are issued and 4 windows are declared dropped. Fails pre-fix (6 probes issued).
- New: `test_density_probes_batch_concurrently_instead_of_queueing_serially` — peak
  overlapping tstats probes ≥ 2 across one plan. Fails pre-fix (peak 1, serial).
- New: `test_relate_runs_after_a_behaviours_stage_whose_clock_expired` — a budget expired
  and exhausted by `behaviours` still lets `relate_stage` issue its read and complete;
  fails pre-fix with `HuntDeadlineExceededError: job_deadline_exceeded` at `_reserve`
  (the incident's exact stack).
- Updated: `test_a_budget_refused_read_writes_a_ledger_row` (sample) — the ledger now holds
  one refusal row, not two: the probe is priced away before it can spend, so only the window
  read is declared. The declaration invariant is unchanged; the issued-probe count is the fix.
- Updated: `test_the_read_plan_never_exceeds_the_remaining_request_budget` /
  `test_a_window_dropped_by_the_planner_is_declared` (behaviours) — the priced plan means
  40 remaining requests buy 20 probed evidence reads (top 5 files), not 40 probe-less
  evidence reads the old unpriced stub allowed. `issued <= remaining` still asserted and
  still holds.
- Net test lines: +163 / −5 across `test_hunt_executor.py` (+63), `test_hunt_notables_sample.py`
  (+97/−3), `test_hunt_notables_behaviours.py` (+3/−2).

## Gates

`uv run pytest tests/unit/ -q` → 3085 passed, 22 skipped · `uv run ruff check .` → clean ·
`uv run ruff format --check .` → clean · `python3 scripts/complexity_report.py --gate` →
GATE OK (all ceilings within budget; god_funcs reported 571 vs baseline 546 — `read_files`
grew by call plumbing, new logic lives in `_density_counts`/`_headed_requests`).
`uv run mypy portal/` reports 650 pre-existing errors on HEAD **and** on this tree (verified
identical via `git archive HEAD` scratch check); zero errors in the hunt subsystem or any
file this lane touched.

## Held-out sets

No query, read or fixture touches `hb_ait_wheeler`, `hb_cloudobs_aws` or `botsv1`; the
relate test's index is a synthetic `ix`. No live Splunk run, no `launch.sh`, no `.env`.

# FINDING — R2 botsv2: the wide estate (D1) reads, but it spends the whole request budget

Lane `lane/hunt-proof-r2-botsv2`, HEAD `26aee7eee`, 2026-11-21 18:28–18:41Z. Read-only run
against the lab Splunk; no code or Splunk change. Receipts are
`coding_task/scratch/hunt_proof_r2_botsv2/run_b/botsv2/progress.json`
(`stages.behaviours`), from the brief's run split by stage.

Deep dive §6 measured exactly four botsv2 sourcetypes with more than 8 indexed files
(independently re-checked live this session, one `oneshot` `| tstats … by sourcetype source |
stats dc(source) … by sourcetype | where files > 8`):

| sourcetype | files | events |
|---|---:|---:|
| `pan:traffic` | 32 | 1,883,556 |
| `pan:system` | 32 | 40,073 |
| `ms:o365:management` | 15 | 4,480 |
| `winhostmon` | 9 | 3,413,063 |

## What the D1 read did with them

`stages.behaviours.files` has **1,963 `(source, file, window)` rows** over 181 indexed files
(`files_indexed 181`): 1,813 read, **150 refused `request_budget_exhausted`**, 19 distinct
files carrying a reason (`files_omitted 19`).

| sourcetype | files indexed | files routed | events read | file-window rows | outcome |
|---|---:|---:|---:|---:|---|
| `pan:traffic` | 32 | 32 | 839 of 1,883,556 | 164 | every window read |
| `pan:system` | 32 | 32 | 659 of 40,073 | 256 | every window read |
| `ms:o365:management` | 15 | 15 | 4,476 of 4,480 | 45 | every window read |
| `winhostmon` | 9 | **1** | 1,752 of 3,413,063 | 78 | 8 windows of `driver` read; 16 windows of `driver` and **all 54 windows of the other 8 files refused** |

`winhostmon`'s refusal is the request budget, not the file cap: `driver` is the largest file
and was planned first; by the time the other eight arrived the executor had spent its 2,000
requests (`stages.behaviours.searches {"total": 2000, ...}`, `by_kind {"discovery": 180,
"localise_accel": 6, "localise": 1, "behavior_events": 1813}`). No crash; the stage exits 0
in 632 s with `seconds 228.3` of its own.

## The acceptance reading

**No crash, and the property is declared rather than silent**: every refused window has a
`stages.behaviours.files` row with `events_available`, `rows: 0` and
`reason: request_budget_exhausted`, and the source receipt says `files_routed 1,
files_omitted 9`. Three of the four wide sourcetypes are read completely.

**But the budget is what ended the read.** The behaviour stage consumed 100 % of the 2,000
requests and still left 8 of `winhostmon`'s 9 files unread. The D1 finding's own estimate
(§ "Behaviour-stage file reads across every activity source") was 473–651 reads for the tuned
families; botsv2 plans **1,813 behaviour reads + 180 discovery + 7 localise = 2,000**, i.e. on
the wide control the per-file route exactly fills the request ceiling. `events_read` is
259,769 against the pre-D1 run's 260,342 — the same volume, bought with ~14× the searches.

Two smaller defects visible in the same receipts, both pre-dating this lane and unchanged:

- `stages.behaviours.events_scanned` is ~4.81 M on each wide source (`pan:traffic` 4,807,328,
  `pan:system` 4,807,148, `ms:o365` 4,810,957, `winhostmon` 4,808,241) — the anchor window's
  population, not rows scanned. It still cannot be used as a scan cost.
- The omitted-by-budget windows appear in the **receipt** (`files`) but not in
  `ledger.jsonl`: the ledger holds 2,000 behaviour-stage rows, all issued queries (1,998 with
  `reason: null`, 2 `censored`), and no row with `request_budget_exhausted`. D1's build says a
  `(source, file, window)` read emits a ledger row; the `read_files_cap` path does
  (`_omit_file`), the budget path does not.

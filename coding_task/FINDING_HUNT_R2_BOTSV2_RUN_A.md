# FINDING — R2 botsv2, literal `--stage all`: the run dies before it reads anything

Lane `lane/hunt-proof-r2-botsv2`, HEAD `26aee7eee` (clean), 2026-11-21 18:16–18:29Z.
Grading only: no code or Splunk change, no `launch.sh`, no held-out set opened. Credentials
exported by key name from the live checkout's `.env`; `host.docker.internal` rewritten to
`localhost`.

This file records the **brief's own command** and what it did. The acceptance properties are
graded in `coding_task/REPORT_HUNT_VERDICT_R2_botsv2.md`.

## The command

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out coding_task/scratch/hunt_proof_r2_botsv2/botsv2 \
  --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell
```

## What happened

`exit=1` in **720.98 s**, `HuntDeadlineExceededError: job_deadline_exceeded` raised from
`relate.py:1530 → executor.py:548` (`_reserve`). Per-stage receipts from `progress.json`:

| stage | wall | searches | rows read | outcome |
|---|---:|---:|---:|---|
| cards | 573.239 s (model_seconds 887.148, 113 model requests) | 625 | 107,947 | 104 sources → 144 cards |
| behaviours | 147.273 s (inventory alone 146.788 s) | 131 | **0** | every behaviour read refused |
| notables | 0.468 s | 0 | 0 | 39 notables over an empty store |
| relate | — | — | — | **crashes** |

The 720 s shared `job_seconds` budget is consumed by **cards alone** (573 s) plus inventory
(147 s), so the first behaviour read is refused: `events_read=0`. `inventory` shows the same
cut from the inside — `fields={'complete': 8, 'failed:query_bound': 1,
'failed:read_failed:HuntDeadlineExceededError': 24, 'parse_only': 107,
'unavailable:mechanism': 7}`, `probe_failures` naming `field:<name>:read_failed:
HuntDeadlineExceededError` 24 times.

The D1 per-file read path is live and it is what is visible in the receipt: `files_indexed
181`, `files_omitted 181`, and **1,617 file-window rows** in `stages.behaviours.files`, all
with `reason: job_deadline_exceeded`:

```
pan:traffic  files 32  rows 101  events_returned 0  {'job_deadline_exceeded': 101}
pan:system   files 32  rows 224  events_returned 0  {'job_deadline_exceeded': 224}
ms:o365:management files 15 rows 15 events_returned 0 {'job_deadline_exceeded': 15}
winhostmon   files  9  rows  64  events_returned 0  {'job_deadline_exceeded': 64}
```

D5's probe now runs: `localisation.indexes[0]` carries six model roots
(`Authentication, Endpoint, Intrusion_Detection, Network_Resolution, Network_Traffic, Web`),
each `accel:<model>:job_deadline_exceeded`, and `localise:job_deadline_exceeded`. The
mechanism recorded is `indexed`, `coverage: scan`, `accel_window: null` — but nothing in this
run was actually localised (`windows 0`, `events 0`), so this run cannot grade the rung.

## Scoreboard over that run

```
C0 ceiling  keys 4/20 reachable  steps 4/14 (B+P 4/11)  stores {'ledger': 4}
steps      top50 0/14   top100 0/14   all 0/14
scenarios  top50 0/4   top100 0/4   all 0/4
C0 causes  censored 12, not_surfaced 1, unreached 1
cost cards=573.239s/113model-req/625searches/107947rows behaviours=147.273s/0model-req/131searches/453rows notables=0.468s ... total=720.98s
```

`keys 4/20` is below the post-audit floor of 5/20: the four reachable keys are reachable only
through the cards-stage `ledger` (`stores {'ledger': 4}`), not through any read store.

## What this run does establish

- `progress.json:honesty` is **non-null** even on a run that read nothing
  (`knowledge loaded, families [kyoushi, russell, santos], items 2431, weights_source
  default`). D10's honesty half holds.
- `C0 causes` is **non-empty** on line/entity families (`censored 12, not_surfaced 1,
  unreached 1`). D10's cause half holds.
- The D1 receipt shape is live: every planned `(source, file, window)` read has a row with
  `events_available`, `rows`, `reason`.
- `--stage all` is still not a runnable acceptance command, and this time it is worse than
  the 2026-11-21 morning run recorded in `REPORT_HUNT_VERDICT_botsv2.md` (Run A): that run
  managed 48,412 behaviour rows and 5/20 keys because cards took 526 s; this one took 573 s
  and read **zero**. Cards is model-bound and its cost is not part of any slice's acceptance,
  yet it alone exceeds the whole job budget.

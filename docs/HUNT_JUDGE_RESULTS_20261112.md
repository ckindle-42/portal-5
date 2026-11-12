# Hunt — judge composition: diagnosis, fixes, live result (2026-11-12)

Status: **built and live-run on the three dev environments; does not yet beat layer 1. No held-out
run. Not merged to main, not pushed.** Receipts are under `results/hunt/` (local, not tracked).

## Diagnosis (live receipts, scorer plane)

- Layer 1 ranks host-hours by "different from before" and is near chance past its first ranks.
  Keyed host-hours / ranked host-hours: kyoushi 6 / 1383, russellmitchell 91 / 1288, santos
  61 / 1285. Nothing in the composition measured "consistent with intrusion".
- Graph runner r2 output defects: one lead per entity (261 leads = 17 host-hours), 320–750 MB
  `leads.json` per run, evidence = 200 random events of the host-hour instead of the events that
  made the cell deviate.
- The Pipeline dropped `logprobs` / `top_logprobs` on the Ollama path.

## Fixes applied (`lane/hunt-judge`, merged into `lane/hunt-graph-int`)

| Commit | Change |
|---|---|
| `65b464865` | Pipeline: a non-streaming request with `logprobs: true` keeps the engine's logprobs on the Ollama path. Unit-tested only; not yet verified through a rebuilt live Pipeline. |
| `e13e293b0` | `hunt/evidence.py` (events behind a cell's own top observations, through the executor), `hunt/judge.py` (one fixed yes/no question, P(yes) from first-token logprobs, failures stay "unjudged"), `scripts/hunt_bed/judged_hunt.py` (one lead per host-hour, every layer-1 cell kept, bounded output). |
| `6933ea953` | Evidence read no longer discards a cell at its row cap (first live run lost 38 of 100 santos cells that way); volume observations no longer widen the read. |

Output size per run fell from hundreds of MB to about 7 MB.

## Live result (`results/hunt/judged_dev_r2/`, lab Splunk, judge `granite4.1:8b-ctx8k` on Ollama `/v1`)

100 of 100 budgeted cells judged on every environment, 0 censored reads, 0 Splunk jobs left.
Both orders are from the same run; keyed cells among the first 10 / 25 / 50 host-hours.

| Environment | Order | top 10 / 25 / 50 | First-hit ranks | Median keyed-cell rank | Wall |
|---|---|---|---|---|---|
| santos | layer 1 | 3 / 7 / 11 | 1, 3, 31 | 23 | |
| santos | judged | 5 / 6 / 11 | 2, 8, 10 | 13 | 631 s |
| russellmitchell | layer 1 | 3 / 7 / 8 | 1, 4, 16 | 16 | |
| russellmitchell | judged | 3 / 8 / 8 | 2, 15, 18 | 16 | 791 s |
| kyoushi | layer 1 | 1 / 1 / 1 | 3 | 3 | |
| kyoushi | judged | 1 / 1 / 1 | 2 | 2 | 594 s |

Read: the judge helps santos (third episode from rank 31 to 10), is neutral on russellmitchell and
moves kyoushi's hit from 3 to 2. First hit is worse by one rank on both AIT indexes. It does not
meet the bar in the problem statement §7 (first hit at least as good, fewer false cases above).

The earlier probe (`results/hunt/judge_probe_r1/`) showed a larger gain (santos keyed cells in top
25: 2 → 8) because it started from the 11 November layer-1 receipts; layer 1 on this branch
(with `stream` and `value` kinds) is already better than those.

## Open

- Wall time is 10–13 minutes: evidence reads 6.7 s per cell (12 appended sub-searches), judge
  4.3–6.3 s per cell. The probe's single read per cell cost 0.1 s.
- Recall is capped by the 100-cell budget: the fourth AIT episode and kyoushi's second sit below
  layer-1 rank 100.
- Layer 1 `coverage_complete` is false on every run (value grid censored).
- Run-twice identity not checked. Through-Pipeline logprobs not checked (needs merge + rebuild).
- Not tried: a different judge model, a campaign-level case (onset followed outward) as the unit
  judged instead of one host-hour.

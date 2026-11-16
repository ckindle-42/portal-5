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

---

## Round 2 (2026-11-12, later) — clean evidence, fair budget, fused order, cases, Pipeline only

All judge calls below went through the Portal Pipeline (`security-reviewer` unless stated). Nothing
was asked of an engine directly.

### What changed

| Change | Where | Why (measured live) |
|---|---|---|
| Chat logprobs carried on the native Ollama path | main `1c60bc7cb`, `be8e39346` (merge `bfa40d2f3`) | The first passthrough used the engine's `/v1` surface: `security-reviewer` failed with `time: missing unit in duration "-1"` and thinking models returned a reasoning marker as the first token. Now verified live on `security-reviewer` and five bench workspaces. `bench-foundation-sec-8b-reasoning` still returns no answer token. |
| Each event shown to the judge once | `6943358b2` | Shape and stream observations selected the same events, so every line appeared twice. Judge AUC (keyed vs unkeyed, 300 cells) 0.77 → 0.85. |
| One bounded evidence read per cell | `6943358b2`, `8a24facde` | 6.7 s → about 0.8 s per cell. The first form returned every shape of the hour and exhausted the executor's 5,000-event budget after 8–25 cells (`judged_dev_r3_eventbudget_fail/`). |
| Judge budget taken round-robin per host-day | `82b7c8ac5` | Layer 1 spends the budget on a few noisy hosts; episodes first appear at layer-1 cell 298–508. |
| Fused order (rank-sum of P(yes) rank and budget rank) | `82b7c8ac5` | P(yes) alone discards layer 1. |
| `cases.json` (one case per judged host-day) | `82b7c8ac5` | Product unit is a case. |

Tried and dropped: per-kind counts in the prompt (model answered yes to 81–99 of 89–99 unkeyed
cells); 160-character events (AUC 0.84, only 11 % faster); four other judge models through the
Pipeline — `gemma4:e4b` AUC 0.80 at 1.6 s per cell, `Qwen3.6-35B-A3B` 0.79 at 2.1 s,
`gemma4:26b-a4b` 0.80 at 3.3 s — none beat `granite4.1:8b` (0.85 at 3.9 s).

### Live dev result (`results/hunt/judged_dev_r3/`, 160 judged cells, 0 unjudged, 0 censored)

| Index | Order | Episode first-hit ranks | Keyed cells in top 10 / 25 / 50 | Wall |
|---|---|---|---|---|
| santos | layer 1 | 1, 3, 32, 508 | 3 / 7 / 11 | |
| santos | fused | 1, 7, 24, 562 | 3 / 5 / 6 | 628 s |
| russellmitchell | layer 1 | 1, 4, 17, 298 | 3 / 6 / 8 | |
| russellmitchell | fused | 1, 3, 19, 42 | 4 / 5 / 7 | 671 s |
| kyoushi | layer 1 | 3, 372 | 1 / 1 / 1 | |
| kyoushi | fused | 3, 34 | 1 / 1 / 2 | 743 s |

- First hit unchanged on all three. The last episode moves from 298 to 42 (russellmitchell) and
  372 to 34 (kyoushi). Santos: second episode 3 → 7; fourth episode not reached (one cell past
  the budget).
- Fewer keyed cells in the top 25 and 50 than layer 1, because the budget is spread over host-days.
- Cases: 98–120 per index; episodes' first case at 1/7/24, 1/3/19/40 and 3/34.
- Wall 10–12 minutes: judge 3.5–4.2 s per cell; evidence about 125 s per run; layer 1 about 38 s.
- Run twice (santos, same window): identical lead order and identical evidence; 2 of 160 P(yes)
  values differ by at most 0.0035, so the files are not byte-identical. Splunk running jobs
  after: 0.

**Verdict: not a clean beat of layer 1. Held-out indexes not run.**

### Open

1. The judge answers yes to 24–51 % of unkeyed cells; no local model tested does better.
2. Speed: about 3.9 s per judged cell.
3. Layer-1 `coverage_complete` is false on every run (value grid).
4. P(yes) is not bit-stable across runs.

---

## Round 3 (2026-11-12, evening) — the core cause: host-hours were ranked by one observation

### Core cause (traced in code)

Layer 1 emits about 340,000 scored observations per index and sorts them by single score
(`observations._sort_key`). Every consumer then reduced a host-hour to its one strongest
observation: `engine.hunt` takes `ordered[:15]` as seeds, `graph_hunt.py` the first 8 seed cells,
`evidence.evidence_cells` ranked cells by first appearance. `engine.host_hour_novelty` accumulates
per host-hour, but `observations._novelty` calls it one shape at a time. So every layer built
after layer 1 (investigator, graph, judge) was fed a handful of single observations and ranked
worse than layer 1, as the problem statement recorded.

### Fix (lane `hunt-accumulate`, `b8d418ffc`, merged `64147bf42`)

- Host-hour `risk` = sum of the positive scores of all its observations; order by risk
  (ties by the old order). No weights, no kind selection, no threshold.
- Judge only the first N cells of that order (`--judge-cells`, default 50); evidence is the
  hour's shapes rarest-on-this-host first (was: strongest deviation, which showed no keyed event
  in 9 of 23 keyed cells).
- Fused order among judged cells, the rest in accumulated order. `cases.json` covers every
  host-day.

### Live dev result (`results/hunt/judged_dev_r4/`, 20 judged cells, `security-reviewer` through the Pipeline; 0 unjudged, 0 censored, 0 Splunk jobs after)

| Index | Order | Keyed cells in top 5 / 10 / 25 / 50 / 100 | Episode first-hit ranks | Episodes' first case | Wall |
|---|---|---|---|---|---|
| santos | old layer 1 | 2 / 3 / 7 / 11 / 11 | 1, 3, 32, 508 | | |
| santos | accumulated | 3 / 8 / 20 / 39 / 48 | 1, 3, 16, 19 | | |
| santos | fused (output) | 4 / 9 / 20 / 39 / 48 | 1, 4, 10, 11 | 1, 3, 4, 5 | 159 s |
| russellmitchell | old layer 1 | 2 / 3 / 6 / 8 / 11 | 1, 4, 17, 298 | | |
| russellmitchell | accumulated | 3 / 8 / 22 / 33 / 60 | 1, 3, 16, 18 | | |
| russellmitchell | fused (output) | 4 / 9 / 22 / 33 / 60 | 1, 3, 7, 17 | 1, 3, 4, 6 | 147 s |
| kyoushi | old layer 1 | 1 / 1 / 1 / 1 / 1 | 3, 372 | | |
| kyoushi | accumulated | 0 / 1 / 2 / 2 / 3 | 6, 64 | | |
| kyoushi | fused (output) | 1 / 1 / 2 / 2 / 3 | 2, 64 | 2, 32 | 120 s |

Run twice (kyoushi, same window): same lead order, same evidence; 5 of 20 P(yes) values differ
by at most 0.01, so files are not byte-identical.

Role of the judge (combined probe, 50 cells, live): where the accumulated order is already dense
(santos 39 of 50 keyed, russellmitchell 33 of 50) the judge says yes to nearly everything and adds
little; on kyoushi it separates keyed from unkeyed perfectly in the top 50 and moves the first
hit from 6 to 1.

**Verdict: beats the old layer-1 order on all three dev indexes. Held-out indexes not run** — see
the limits below; the operator decides when to spend the single held-out run.

### Limits found by the same review (all measured live on dev)

1. **The shape signal only exists for free-text logs.** `eve.json` has 1.1 M events and 7
   shapes, `stats.log` 20 M and 39, `audit.log` 15; `dnsmasq.log` has 13,938 in santos. The
   ranking is mostly "how many unusual free-text strings did this host log this hour". Attacks
   that live in JSON, cloud or Windows event data are close to invisible.
2. **The value grid, the only content signal for structured data, is the weakest part**: four
   sample hours of 200 events, key budget exhausted, AUC 0.54–0.61 alone, and the reason
   `coverage_complete` is always false.
3. **The three dev indexes are one testbed family.** Two of the three held-out indexes are cloud
   JSON and Windows. Dev cannot predict them.
4. **Six days of history.** New host-shape pairs per day in santos: 12,172 / 13,355 / 8,281 /
   2,661 / 346 / 82. The top 50 cells sit mostly on days 2–3.
5. **Host aliases** (`a-b` and `a_b` for one machine) split evidence: 16–17 host names for 11
   machines. Merging lifted kyoushi's whole-index AUC from 0.76 to 0.84 in re-analysis.
6. The product path (`engine.hunt`, review MCP `hunt_*`) still uses the 15-seed order.

Tried and dropped this round: judging a whole host-day in one prompt (judge AUC 0.64, mixed
ranks, 5.5–7.5 min); scoring the judge relative to each host's own answers (worse); weighting a
new shape by its stream's new-shape rate (no gain).

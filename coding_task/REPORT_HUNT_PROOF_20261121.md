# REPORT — hunt live proof run on the training families (2026-11-21)

Grading run only. No code, Splunk configuration or held-out set was touched. Worktree
`/Users/chris/projects/portal-5-hunt-proof-run`, lane `lane/hunt-proof-run`, base
`35876168e` (S1 Tier A/B, S2 spine, S3 cases, S4 detections, S6 rungs 1–3 all merged).
S7 was **not** on main at start or end of the run (`git log --all --grep=S7` has no hunt
commit; `judge_notables.py` still judges notables, not cases).

Lab Splunk `https://10.0.1.30:8089` (10.2.5). Credentials exported by name from the live
checkout's `.env` (`LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`, `LAB_SPLUNK_PASSWORD`,
`LAB_SPLUNK_HEC_URL`, `LAB_SPLUNK_HEC_TOKEN`); `.env` was never sourced. `host.docker.internal`
rewritten to `localhost`. Pipeline `:9099` served the judge (`hunt-reasoning`, served
`gemma-4-26b-a4b-it-QAT-4bit`) and embeddings (`google/embeddinggemma-2`).

Index volumes (`| eventcount`, read-only): botsv2 226,337,781; hb_ait_santos_v2 4,474,600;
hb_ait_santos 25,143,873; hb_kyoushi_s1_v2 2,465,043; hb_kyoushi_s1 24,504,858;
hb_ait_russellmitchell_v2 4,191,003; hb_ait_russellmitchell 25,522,335.

Run dirs: `coding_task/scratch/hunt_proof_20261120T232700/{v2,control,botsv2}/<family>/`.
Stages were run in the `all` order (`cards → behaviours → notables → relate → judge`) so each
slice's timing is in `progress.json`.

## 1. Per-family, per-slice table

Slice acceptance is the plan's §4 property. `_v2` is the tuned index; the original index is the
negative control. `—` = not run yet.

| family / index | S0 measurement | S1 enumeration | S2 spine | S3 cases | S4 detections | S5 weights | S6 localisation | S7 judge |
|---|---|---|---|---|---|---|---|---|
| santos / `_v2` | pass (baseline reproduced) | **pass** — 11 complete lists, 1,495 values, `first_seen_replaced 22`; `tstats suricata src_ip` 126 values in 0.44 s | pass — 6,175 entities, 19,296 episodes, 25,037 links | **pass** — `scenario covered yes`, violations 0, `coverage_complete False`, uncapped 0.586; judged-only shape unproven | pass (`alerts existed 76`) | reported (C4 fold table, §2) | **fail** — `mechanism=indexed`, `model=""`; rungs 2–3 work (4 windows, 9 anchored, `events_scanned` on every read) | **fail** — judges notables, not cases; 813/822 judged, 9 budget-exhausted |
| kyoushi / `_v2` | pass (baseline reproduced) | **pass** — 16 complete lists, 4,515 values, `first_seen_replaced 20`; `tstats suricata src_ip` 134 values in 0.44 s | pass — 9,513 entities, 26,685 episodes, 39,097 links | **fail** — `case members top50 0/12`, `scenario covered no`; violations 0, `coverage_complete False`, uncapped 0.716 | pass (`alerts existed 27`) | reported | **fail** — `mechanism=indexed`, `model=""`, `accel_window` [2021-03-22, 2021-03-28] but range 2 s outside it; rungs 2–3 work (3 windows, 9 anchored, 6 whole) | **fail** — notables, not cases; 755/755 judged, AUC 0.413 (anti-correlated) |
| russell / `_v2` | — | — | — | — | — | — | — | — |
| santos / original (control) | pass | pass — 13 complete lists, 1,479 values, `first_seen_replaced 44`, `flows 17` | pass — 5,686 entities, 34,499 episodes, 62,928 links | pass — `scenario covered yes`, violations 0, uncapped 0.811, censored `{gap 5351, window 617, flow_roles 17}`; 3,467 cases | pass (`alerts existed 47`) | reported | **pass (negative control)** — four model probes `count=0`; `accel_window=null`, `mechanism=indexed`, `coverage=scan`; 1 window, 28 anchored / 20 whole | **fail** — notables; 800/881 judged, 81 budget-exhausted |
| kyoushi / original (control) | pass | pass — 9 complete lists, 1,454 values, `first_seen_replaced 31`, `flows 21` | pass — 6,529 entities, 30,375 episodes, 52,783 links | pass — `scenario covered yes`, violations 0, uncapped 0.801, censored `{gap 4899, window 492, flow_roles 21}`; 4,856 cases | pass (`alerts existed 27`) | reported | **pass (negative control)** — `accel_window=null`, `mechanism=indexed`, `coverage=scan`; 4 anchored / 12 sampled / 17 whole | **fail** — notables; 800/800 judged, AUC 0.699 |
| russell / original (control) | — | — | — | — | — | — | — | — |
| botsv2 (control) | — | — | — | — | — | — | — | — |

Control detail (santos, original `hb_ait_santos`): S6 negative control **passes** — the four
accelerated-model probes all returned `count=0`, so `accel_window=null`, `mechanism=indexed`,
`coverage=scan`; rung 2 produced 1 window, 28 sources `anchored`, 20 `whole`. S1 on the control:
13 complete lists, 1,479 values, `mechanisms {stats: 32}` (the original source names are file
paths, so `tstats by` is not available), `first_seen_replaced 44`, `flows 17`, `joints 8`.
S3 on the control: `scenario covered yes`, violations 0, `coverage_complete False`, uncapped
0.811, censored `{gap: 5351, window: 617, flow_roles: 17}`, 3,467 cases, `flows 17`.

## 2. Scoreboard vs baseline

| family | index | mode | @50 | reachable steps | recall of reachable @50 | §3 baseline (line / reach. / ROR) |
|---|---|---|---|---|---|---|
| santos | `hb_ait_santos_v2` | line | 16/21 | 11/21 | 8/11 | 18/21 / 12/21 / 11/12 |
| santos | `hb_ait_santos` (control) | line | 15/21 | 12/21 | **11/12** | 18/21 / 12/21 / **11/12** |
| kyoushi | `hb_kyoushi_s1_v2` | line | 11/12 | **7/12** | 7/7 | 11/12 / 11/12 / 11/11 |
| kyoushi | `hb_kyoushi_s1` (control) | line | 11/12 | **11/12** | **11/11** | 11/12 / 11/12 / **11/11** |

The controls reproduce the plan's recall-of-reachable exactly (santos 11/12, kyoushi 11/11; raw
@50 15/21 and 11/12). The tuned `_v2` indexes **lose reachable steps** — kyoushi 11→7, santos
12→11 — while raw line recall stays flat (11/12) or rises (16/21). The scoreboard's line mode
does not gate coverage on read reachability, so a step can be "covered" by a notable whose
supporting line was never read; the honest coverage number is the reachable ceiling, and that is
what fell. Read fractions: kyoushi `_v2` 10.0 % vs control 0.9 %; santos `_v2` 5.7 % vs control
1.4 %. Reading a larger share of the tuned index reached fewer keyed lines.

C4 marginal weights, stored-run LOFO (the only evidence available before all families finish):

| held out | deviation | misfit | similar_to_known | alerts | peer_rare | relate |
|---|---|---|---|---|---|---|
| all | 2 | 1 | 4 | 1 | 1 | 1 |
| botsv2 | 2 | 1 | 5 | 1 | 1 | 1 |
| kyoushi | 2 | 1 | 4 | 1 | 1 | 1 |
| russell | 1 | 1 | 3 | 1 | 1 | 1 |
| santos | 2 | 1 | 3 | 1 | 1 | 1 |

## 3. Timings

| family / index | cards | behaviours | notables | relate | judge | total wall |
|---|---|---|---|---|---|---|
| santos `_v2` | 34.4 s | 186.3 s | 267.4 s | 8.0 s | 730.4 s | 1,207.9 s |
| santos control | 352.2 s | 294.0 s | 213.0 s | 9.3 s | 746.1 s | 1,594.9 s |
| kyoushi `_v2` | 30.6 s | 150.7 s | 202.4 s | 9.0 s | 618.3 s | 992.5 s |
| kyoushi control | 50.6 s | 170.0 s | 273.7 s | 9.2 s | 636.8 s | 1,131.1 s |

`behaviours` wall includes inventory (49.6 s / 76.0 s) and spine; `_v2` read 137,574 events of
4,474,600 (5.7 %), the control 182,083 of 25,143,873 (1.4 %). `judge` is bounded by the 720 s hunt
job budget, not by notable count (813/822 and 800/881 judged; the rest `model_budget_exhausted`).

## 4. Verdict

Pending the remaining families.

## 5. Design-layer attribution

Pending the remaining families.

## 6. Evidence

### S0 — stored-run rescore reproduces the plan's §3 baseline

`uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out
/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon --weights ...` reproduced
every §3 row: botsv2 `steps top50 3/14`, `strict 2/14`, `C0 ceiling keys 5/20 reachable steps
5/14 (B+P 5/11)`; kyoushi `11/12` line, reachable 11/12; santos `18/21` line, reachable 12/21,
recall-of-reachable 11/12; russell `15/22` line, reachable 15/22, 14/15. The C4 fold table is
non-trivial (`deviation` 1–2, `similar_to_known` 3–5, others 1).

Note on the brief's baseline: the brief says `keys_reachable 8/24`; the scoreboard on the same
C0.1 run prints `keys 5/20 reachable`. The difference is the keys audit (3 artefacts
`admitted=false` and 1 shared value removed by the scoreboard's own rule), not a change in the
run. Both numbers are reported; `8/24` is the pre-audit count, `5/20` is the C0.1 ceiling the
current scoreboard measures.

### S1 — enumeration on santos `_v2`

`inventory.json`: `fields {capped: 1, complete: 11, empty: 20}`, `values 1495`,
`mechanisms {stats: 24, tstats: 8}`, `events_scanned 4,910,721`, `first_seen_replaced 22`.
Widest list: `tstats suricata src_ip` complete, 126 values, 0.44 s, 334,566 events scanned.
Direct probe `| tstats count min(_time) as first max(_time) as last where index=hb_ait_santos_v2
sourcetype=suricata by src_ip` → 1,524 rows, `runDuration` 0.66 s. Tier B indexed half passes.

`model_probes 0` / `accelerated []`: no selected field on a wide source was search-time only,
so the accelerated rung was correctly not entered (plan's expected case). This means Tier B's
`from datamodel=` half is **not exercised** by this run.

### S6 — rung 1 does not fire on the tuned `_v2` index

`localisation.indexes[0]` on santos `_v2`:

```
{"index":"hb_ait_santos_v2","width":3600.0,"hosts":1,"windows":4,"events":1169710,
 "mechanism":"indexed","model":"","coverage":"scan",
 "accel_window":[1616425563.0,1642485717.000001],"notes":[]}
```

The probe found a complete summary (`Authentication`, 2,736 events on this index) but
`coverage_label` requires the searched range to sit inside the summary window. The index-wide
sampled range is `[1616425561, 1642487481]`: 2 s before the summary's first summarised event and
1,764 s after its last. The range is the union over all sampled sources for the index, while the
summary only covers authentication events, so one late `syslog` event and one early event defeat
containment. Rung 1 falls to rung 2 (`tstats … by host _time`), which works: 4 windows, 1,169,710
events, 9 sources read `anchored`/`narrowed_scan`, every receipt carries `events_scanned`.

Negative-control probe on the original `hb_ait_santos` (same command, four models): every
`count=0`, so the control must report `accel_window=null`. That half of S6 is behaving as the
finding predicted.

### S3 — cases on santos `_v2`

`case members top50 3/21 (B/P steps in a case) scenario covered yes`; `case evidence pieces min 2
violations 0`; `coverage_complete False uncapped_fraction 0.586439 censored {'gap': 5419,
'window': 851, 'flow_roles': 0}`; `case promotion judged_only no lifted 12 unjudged_lifted 12`.
461 cases, 40 relate requests, 417 related events, 5.5 s. `flows 0` (no inventory flows on this
index). `unjudged cases 97` is stale with respect to the judge stage: cases.json is built before
judge, so the 813 rows judged afterwards are still marked unjudged in the case receipt.

# REPORT — hunt live proof run on the training families (2026-11-21)

Grading run only: no code, Splunk configuration or held-out set was touched. Worktree
`/Users/chris/projects/portal-5-hunt-proof-run`, lane `lane/hunt-proof-run`, base `35876168e`
(S1 Tier A/B, S2 spine, S3 cases, S4 detections, S6 rungs 1–3 merged). S7 was **not** on main at
start or end of the run: `git log --all --grep=S7` has no hunt commit and `judge_notables.py`
still judges notables, not cases, so S7's judge-over-cases proofs do not exist to include.

Lab Splunk `https://10.0.1.30:8089` (10.2.5). Credentials exported by name from the live
checkout's `.env` (`LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`, `LAB_SPLUNK_PASSWORD`,
`LAB_SPLUNK_HEC_URL`, `LAB_SPLUNK_HEC_TOKEN`); `.env` was never sourced; `host.docker.internal`
rewritten to `localhost`. Pipeline `:9099` served the judge (`hunt-reasoning`, served
`gemma-4-26b-a4b-it-QAT-4bit`) and embeddings (`google/embeddinggemma-2`).

Index volumes (`| eventcount`, read-only): botsv2 226,337,781; hb_ait_santos_v2 4,474,600;
hb_ait_santos 25,143,873; hb_kyoushi_s1_v2 2,465,043; hb_kyoushi_s1 24,504,858;
hb_ait_russellmitchell_v2 4,191,003; hb_ait_russellmitchell 25,522,335.

Run dirs: `coding_task/scratch/hunt_proof_20261120T232700/{v2,control,botsv2}/<family>/`; raw
logs and score outputs sit beside them. Stages ran in the `--stage all` order
(`cards → behaviours → notables → relate → judge`), so `progress.json` carries each slice's
receipt and seconds.

## 1. Per-family, per-slice table

Acceptance is the plan's §4 property. `_v2` is the tuned index; the original index is its
negative control.

| slice | santos `_v2` | kyoushi `_v2` | russell `_v2` | santos orig | kyoushi orig | russell orig | botsv2 |
|---|---|---|---|---|---|---|---|
| **S0** measurement | pass | pass | pass | pass | pass | pass | pass |
| **S1** enumeration | pass (11 complete, 1,495 values, `first_seen_replaced 22`; tstats 0.44 s) | pass (16 complete, 4,515 values, `first_seen_replaced 20`) | pass (13 complete, 846 values, `first_seen_replaced 17`) | pass (13 complete, 1,479 values, `first_seen_replaced 44`; `eve.json src_ip` 1,285 values) | partial (9 complete, 1,454 values, `first_seen_replaced 31`; none over a wide source) | partial (6 complete, 240 values, `first_seen_replaced 2`; all tiny sources) | **fail** (Tier A 13 complete / 538 values, but 6 wide lists `unavailable:mechanism`; Tier B not met) |
| **S2** spine | partial (6,175 ent / 19,296 ep / 25,037 links) | partial (9,513 / 26,685 / 39,097) | partial (7,931 / 21,935 / 27,587) | partial (5,686 / 34,499 / 62,928) | partial (6,529 / 30,375 / 52,783) | partial (6,277 / 66,421 / 127,997) | partial (15,921 / 125,016 / 219,230) |
| **S3** cases | **pass** (3/21 B/P @50, `scenario covered yes`, violations 0, uncapped .586) | **fail** (0/12, `scenario covered no`, violations 0, uncapped .716) | **pass** (3/22, `scenario covered yes`, violations 0, uncapped .543) | pass (3/21, yes, uncapped .811) | pass (3/12, yes, uncapped .801) | pass (8/22, yes, uncapped .899) | **fail** (0/4, pass bar wanted ≥3/4; baseline also 0/4) |
| **S4** detections | pass (alerts 76) | pass (27) | pass (22) | pass (47) | pass (27) | pass (14) | **pass** (existed 4 > 0) |
| **S5** weights | partial (C4 fold measured, §3; run used default) | partial | partial | — | — | — | — |
| **S6** localisation | **fail** rung 1 (`mechanism=indexed`, `model=""`, window 2 s short); rungs 2–3 pass (4 windows, 9 anchored, every read `events_scanned`) | **fail** rung 1 (window 2 s short at start, 9 s at end); rungs 2–3 pass (3 windows, 9 anchored / 6 whole) | **fail** rung 1 (2 s short at start); rungs 2–3 pass (4 windows, 10 anchored / 5 whole) | **pass** control (`accel_window=null`, `indexed`, 1 window) | **pass** control (`accel_window=null`, `indexed`, 0 windows; 4 anchored / 12 sampled / 17 whole) | **pass** control (`accel_window=null`, `indexed`, 1 window; 32 anchored / 31 whole) | **fail** acceptance (steps 6/14 vs ≥10/14) |
| **S7** judge | **fail** (notables; 813/822, 9 budget) | **fail** (notables; 755/755, AUC 0.413) | **fail** (notables; 753/753, AUC 0.967) | fail (notables; 800/881) | fail (notables; 800/800, AUC 0.699) | fail (notables; 392/873, 481 budget) | fail (notables; 392/876, 484 budget) |

Notes on the passes that carry a caveat:

- **S2** is graded from the spine receipts (entities, episodes, links, `events_without_entity`)
  and the scoreboard's use of the spine as a reach store (`stores {'spine': 4}` on botsv2). The
  plan's per-step property — *the carrier entity of every graded step has an episode containing
  its labelled line* — is not instrumented by the scoreboard; this run does not prove it.
- **S3's judged-only half** (`promotion cannot add an unjudged row to a judged-only view`) has no
  live shape: `promotion judged_only no` and the CLI has no `--judged-only`. The live run lifts
  12 rows and marks all 12 `unjudged`. The unit test is the only proof.
- **S7** is failed on the design, not on uptime: the stage ran and judged 813, 755, 753, 800,
  800, 392 and 392 rows (v2 → controls → botsv2). There is no case-level judge in the merged code.
- **S5** measurement exists and is marginal-based (§3), but the live runs merged with
  `weights_source: default` (`merge.weights {alerts 0, deviation 26, misfit 6, peer_rare 0,
  similar_to_known 31}`); the measured weights are not delivered to the run.

## 2. Scoreboard vs baseline

Baseline is the plan §3 C0.1 table, reproduced first by rescoring the stored run with this
scoreboard (`scoreboard --out /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon
--weights …`, log `scratch/hunt_proof_20261120T232700/s0_rescore.txt`): botsv2 `steps top50 3/14`,
`strict 2/14`, `C0 ceiling keys 5/20 reachable steps 5/14 (B+P 5/11)`; kyoushi 11/12, reachable
11/12; santos 18/21, reachable 12/21, ROR 11/12; russell 15/22, reachable 15/22, ROR 14/15. The
brief's
`keys_reachable 8/24` is the pre-audit botsv2 key count; the current scoreboard audits 3
artefacts out and de-duplicates 1 shared key, so it reports `7/20` on this run and `5/20` on the
stored baseline. Both numbers are given for botsv2.

| family | index | mode | @50 | reachable | recall of reachable @50 | §3 baseline (line / reach / ROR) |
|---|---|---|---|---|---|---|
| santos | `_v2` | line | 16/21 | 11/21 | 8/11 | 18/21 / 12/21 / 11/12 |
| santos | orig | line | 15/21 | 12/21 | **11/12** | 18/21 / 12/21 / **11/12** |
| kyoushi | `_v2` | line | 11/12 | **7/12** | 7/7 | 11/12 / 11/12 / 11/11 |
| kyoushi | orig | line | 11/12 | **11/12** | **11/11** | 11/12 / 11/12 / **11/11** |
| russell | `_v2` | line | 13/22 | **11/22** | 9/11 | 15/22 / 15/22 / 14/15 |
| russell | orig | line | 15/22 | **15/22** | **14/15** | 15/22 / 15/22 / **14/15** |
| botsv2 | botsv2 | entity loose | 2/14 | 6/14 (B+P 6/11) | 2/6 | 3/14 / 5/14 (B+P 5/11) / 3/5 |
| botsv2 | botsv2 | entity strict | 1/14 | 6/14 | 1/6 | 2/14 / 5/14 / 2/5 |

Per-key cause on botsv2: `censored 9, covered 1, instrument 1, not_surfaced 2, unreached 1`.
Cases: `case members top50 0/4` and `case recall 0/4`; `promotion effect promoted=12` (from
relate; scoreboard case promotion report `judged_only no lifted 12 unjudged_lifted 12`).

The controls reproduce the plan's recall-of-reachable **exactly** (santos 11/12, kyoushi 11/11,
russell 14/15). The tuned `_v2` indexes *lose reachable steps* (santos 12→11, kyoushi 11→7,
russell 15→11) while raw line recall is flat or higher. The scoreboard's line mode is not gated
by read reachability, so a step can be "covered" by a notable whose supporting line was never
read; the honest coverage number is the reachable ceiling and that fell.

## 3. S5 — measured marginal weights (live `_v2` runs)

`scoreboard --weights` over the three `_v2` family directories:

| held out | deviation | misfit | similar_to_known | alerts | peer_rare | relate |
|---|---|---|---|---|---|---|
| all | 6 | 1 | 2 | 1 | 1 | 1 |
| kyoushi | 7 | 1 | 2 | 1 | 1 | 1 |
| russell | 6 | 1 | 2 | 1 | 1 | 1 |
| santos | 4 | 1 | 3 | 1 | 1 | 1 |

Stored-run LOFO (S0 check) gave `all 2 / 1 / 4 / 1 / 1 / 1`; the live tuned runs move `deviation`
up and `similar_to_known` down. The fold table is non-trivial and marginal-based, so the S5
*measurement* property holds; the delivery (`PORTAL_HUNT_MERGE_WEIGHTS` into the run) is not
exercised — every live run reports `weights_source: default`.

## 4. Timings (seconds, wall)

| family / index | cards | behaviours | notables | relate | judge | total (incl. relate) |
|---|---|---|---|---|---|---|
| santos `_v2` | 34.4 | 186.3 | 267.4 | 5.5 | 719.8 | 1,213.5 |
| santos orig | 351.8 | 293.8 | 212.8 | 7.8 | 736.6 | 1,602.7 |
| kyoushi `_v2` | 30.6 | 150.7 | 202.4 | 6.9 | 608.8 | 999.5 |
| kyoushi orig | 50.6 | 170.0 | 273.7 | 7.8 | 636.8 | 1,138.9 |
| russell `_v2` | 37.8 | 162.0 | 288.7 | 5.8 | 766.3 | 1,260.6 |
| russell orig | 395.6 | 272.3 | 341.9 | 6.4 | 692.8 | 1,709.0 |
| botsv2 | 371.7 | 502.1 | 432.5 | 149.0 | 477.4 | 1,932.7 |

`behaviours` includes inventory (49.5–76.0 s) and the spine. Read fractions: santos `_v2` 5.7 % /
orig 1.4 %; kyoushi `_v2` 10.0 % / orig 0.9 %; russell `_v2` 5.3 % / orig 1.3 %; botsv2 0.19 %.
`judge` is bounded by the 720 s hunt-job budget, not by notable count; slow-seat runs judged only
392 rows (russell orig, botsv2).

## 5. Verdict

**Falls short.** The plan's Step 3 pass bar is not met:

1. *No build-family regression* — controls reproduce the baseline, but the tuned `_v2` indexes
   lose 1, 4 and 4 reachable steps (santos, kyoushi, russell); ROR falls 11/12→8/11 and
   14/15→9/11, and kyoushi's 7/7 is only because the reachable base collapsed to 7. Case coverage
   fails on kyoushi `_v2` (0/12, scenario no).
2. *Coverage* — botsv2 reaches 6/14 steps (B+P 6/11) against a required ≥10/14; keys 7/20
   (pre-audit equivalent 8/24) against ≥12/24. One step and two keys above the stored baseline
   is not the planned rise.
3. *Cases* — botsv2 0/4 scenarios have a case in the top 50 (required ≥3/4); kyoushi `_v2` 0/12
   B/P steps with `scenario covered no`.
4. *Honesty* — S5 reports measured marginals, and every S4 alerts counter is non-zero; but S7's
   case-level judge does not exist, and the run merges with default weights.

## 6. Design-layer attribution (each failure, its layer, its evidence)

- **S6 — localisation, rung 1 is dead on every tuned index.** `localisation.indexes[0]` is
  `mechanism=indexed, model=""` on all three `_v2` runs. The probe found complete summaries
  (`Authentication`; for santos 2,736 events, kyoushi/russell likewise), and `accel_window` is
  recorded, but `coverage_label` requires the searched range to be *inside* the summary window.
  Measured facts vs the window: santos `[1616425561,1642487481]` vs
  `[1616425563,1642485717]` (2 s early, 1,764 s late); kyoushi `[1616425561,1616890440]` vs
  `[1616425563,1616890431]` (2 s early, 9 s late); russell `[1616425561,1643094189]` vs
  `[1616425563,1643094189]` (2 s early). Every index has its first event 2 s before the first
  *summarised* event, and the guard has no tolerance and no per-source window, so the accelerated
  aggregate never runs. The rung's own acceptance ("a model covering the whole range localises
  from its summary") is therefore not met by the live system even though the summary is marked
  `complete=1`.
- **S1 — the accelerated value list is dead for a second reason, independent of S6.**
  `inventory.ACCEL_QUERY` is
  `| rest /services/admin/summarization by_tstats=1 | fields datamodel_name …`. On this Splunk
  the `rest` endpoint exposes `summary.*`, `id`, `title` but **no `datamodel_name` column**; the
  query returns 10 rows with only `summary.complete/earliest_time/latest_time`. `accelerated()`
  therefore yields an empty tuple (`model_probes 0` on every index, `accelerated []`), and a wide
  source whose role field is not in the tsidx becomes `unavailable:mechanism / events_budget`
  (botsv2: 6 lists incl. three `wineventlog:security` lists at 2,178,447 events). Tier B on
  botsv2 is unreachable through the code as merged.
- **S6/S2 — the narrow windows are not the labelled windows on the tuned indexes.** The controls
  (original indexes) reach more keyed lines than the tuned ones while reading a smaller fraction:
  kyoushi 1,944 labelled lines read of 408,038 (0.9 % read) vs `_v2` 287 (10.0 % read); santos
  12/21 reachable vs `_v2` 11/21; russell 15/22 vs 11/22. The `_v2` indexes have the same source
  paths and more of the huntable events (`hb_kyoushi_s1_v2` 2.46 M vs 24.5 M with `stats.log`
  excluded), so this is not missing data; it is the localiser selecting peak buckets that do not
  contain the attack activity. Reading *more* of the tuned index reached *fewer* graded lines.
- **S5 — the measured marginal weights are not delivered.** Every live run reports
  `weights_source: default` and the same constant merge weights; the scoreboard produces the
  marginal fold table only when asked (`--weights`), and nothing writes it back. The ranking loss
  on botsv2 (`steps 2/14 @50` vs baseline 3/14; `strict 1/14` vs 2/14) is consistent with a
  default-weighted merge, not the measured marginals.
- **S3 — cases fail where the read set changed, not uniformly.** kyoushi `_v2` has 0/12 B/P steps
  in a top-50 case (`scenario covered no`) while kyoushi original has 3/12 (`scenario covered
  yes`); botsv2 has 0/4 (baseline 0/4, but the bar wanted ≥3/4). The case rule itself produces
  2,314 / 849 / 4,856 / 5,866 cases with zero two-evidence violations, so formation is not
  broken; the product unit does not contain the graded activity on the tuned index. The 12 lifted
  members are all `unjudged` and there is no judged-only shape.
- **S7 — no case-level judge.** The stage judges 392–813 notables per run (not cases) with a
  720 s budget. On kyoushi `_v2` the judge's `p_yes` is *anti*-correlated with the label
  (`AUC 0.413`, bad yes-rate 0.645 vs good 0.780); on botsv2 it is near chance (`AUC 0.578`,
  only 3 bad rows); on russell/santos it separates (0.967/0.952) but those are also the runs with
  the most `bad` rows. The plan's "one call per case, ordering only, never a pass gate" is not
  what ran.
- **S0 — the instrument is better but still not a read gate.** The stored baseline reproduces
  exactly and the ledger/spine/inventory reach stores exist (`stores {'behaviour','events',
  'ledger','spine','misfit'}`), but raw line recall is not conditioned on reachability:
  santos `_v2` reports 16/21 covered against 11/21 reachable, botsv2 2/14 loose covered against
  6/14 reachable. `relate`'s own receipt says `coverage_complete=True` while the case receipt and
  the scoreboard say `False` (censored gap/window), and case `unjudged` flags are written before
  the judge stage (97 / 78 / 43 / 162 unjudged cases even though all but 9/0/0/484 rows were
  judged afterwards). A reader can take these numbers as coverage when they are not.

Minor, not a slice failure: two `suricata` partitions on santos `_v2` produce two receipts with
the same `source_id`, so `events_read` and read fraction double-count the source and the receipt
loses the partition key.

## 7. What was not run / limits of this report

- Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or
  read; no botsv1.
- S7 was not on main; no judge-over-cases proof exists. The brief's conditional ("if S7 lands on
  main mid-run, include its judge proofs") did not trigger.
- S2's per-step carrier-episode property is not instrumented; only spine counts and the
  scoreboard's spine reach store are reported.
- S1 Tier B's `from datamodel=` half never entered (dead `ACCEL_QUERY`); its acceptance is not
  tested positively, only shown unreachable.
- The judge budget capped several runs (9, 81, 481, 484 unjudged); judged-only and promotion
  effect are correspondingly partial.

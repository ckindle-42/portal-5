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
| kyoushi / `_v2` | — | — | — | — | — | — | — | — |
| russell / `_v2` | — | — | — | — | — | — | — | — |
| santos / original (control) | — | — | — | — | — | — | — | — |
| kyoushi / original (control) | — | — | — | — | — | — | — | — |
| russell / original (control) | — | — | — | — | — | — | — | — |
| botsv2 (control) | — | — | — | — | — | — | — | — |

## 2. Scoreboard vs baseline

## 3. Timings

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

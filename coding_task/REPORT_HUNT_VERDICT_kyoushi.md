# HUNT VERDICT — **kyoushi**

**kyoushi: falls short.**

Graded on code `83f72271e` (`lane/hunt-verdict-kyoushi`) from the stored runs in
`/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/`:
the tuned-index run `v2/kyoushi` (`hb_kyoushi_s1_v2`, 2026-11-21 00:22–00:36) and the
original-index negative control `control/kyoushi` (`hb_kyoushi_s1`, 00:40–00:57). Both runs
carry all five stages (`cards, behaviours, notables, relate, judge`); nothing was missing from
the run directories, so this dispatch re-scored and read them, and ran the one measurement the
stored runs did not carry (the S5 fold table).

The failing design layer is **S2 — spine and episodes**, at its input: the read rows never
become events. On the tuned index the family's dominant sourcetype (`access_combined`,
727,925 events, 99.6 % of the 408,038 graded lines) is a consolidation of five access files;
its card template basis (two templates mined from a 120-line sample of the merged source) does
not cover the graded dirb/webshell line shape, so the 2,500 rows the localiser correctly read
from the attack window never reach the events table — 0 events in 20:19–21:13, all 2,500
classified out of structure. The
consequences are measured in S3 (0/12 cases at top 50 against 3/12 in the control) and S6
(the localisation win never reaches a store). S1 (enumeration on the dominant source) and S7
(the per-notable judge's ordering) are secondary failures. S0's instrument works: the control
reproduces the plan's §3 baseline exactly, and the `_v2` label fix is proven on this family.

---

## 1. What was run (all read-only; no Splunk or repo changes)

```bash
# rescores, from the worktree at 83f72271e
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out .../v2/kyoushi --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out .../control/kyoushi --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl
# S5 fold table (the one measurement the run dirs did not carry)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out .../v2 --keys kyoushi=…/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=…/santos_ingest/keys.jsonl --keys russell=…/russellmitchell_ingest/keys.jsonl --weights
# the _v2 label fix, on this family
ln -sfn .../v2/kyoushi $TMP/kyoushi_v2   # scores, exit 0, "family kyoushi_v2  index hb_kyoushi_s1_v2"
ln -sfn .../v2/kyoushi $TMP/santos_v2    # refuses, exit 2, "excludes 'kyoushi', not 'santos_v2'"
```

Read-only Splunk probes (`LAB_SPLUNK_*` exported from the live checkout's `.env`, host by
name only) served three purposes: confirm what the localiser saw, replay its rung-3 query, and
check the raw-index field extraction. They changed nothing.

## 2. The two runs, side by side

| | `v2` (tuned `hb_kyoushi_s1_v2`) | `control` (original `hb_kyoushi_s1`) |
|---|---:|---:|
| cards / sources | 18 / 13 | 41 / 36 |
| notables | 755 | 800 |
| recall `line` @50 / @100 / all (of 12 steps) | **11/12 / 11/12 / 11/12** | **11/12 / 11/12 / 12/12** |
| median first rank | 19 | 1 |
| **reachable steps (C0 ceiling)** | **7/12** | **11/12** |
| labelled lines read verbatim | 287 / 408,038 | 1,944 / 408,038 |
| recall of reachable @50 | 7/7 | 11/11 |
| case members @50 / @100 / all | **0 / 0 / 2** (of 12) | **3 / 3 / 5** (of 12) |
| scenario covered @50 | **no** | **yes** |
| cases built | 2,314 | 4,856 |
| flow signal (`flows` / censored `flow_roles`) | 0 / 0 | 0 / 21 |
| judge AUC (755 / 800 judged notables) | **0.413** | **0.699** |
| judge yes-rate: covering vs non-covering | 0.645 / 0.780 | 0.811 / 0.565 |
| searches / rows read / wall | 736 / 246,595 / 992.5 s | 977 / 230,237 / 1,131.1 s |
| read fraction (index denominator) | 10.0 % | 0.94 % |

The headline recall is the same 11/12 on both runs and **does not distinguish them**; the
honest ceiling does. The control reproduces the plan's §3 baseline exactly (line 11/12,
reachable 11/12, recall of reachable 11/11). The tuned run keeps 11/12 only because the ceiling
fell to 7/12 and recall-of-reachable is trivially 7/7.

The 10× read-fraction difference is a denominator artefact, not ten times the reading: the
control index contains `stats.log` (22,039,815 events) which the tuned reindex drops as
measurement/noise. Against non-noise events the two ran at 9.3 % (control) and 10.0 % (v2),
with 230k and 247k rows read respectively.

## 3. Slice grading (acceptance property → verdict, receipt)

### S0 — truthful measurement and one path — **PASS (with two instrument gaps)**

- §3 baseline reproduces exactly on the control: `line 11/12 @50`, `C0 ceiling steps 11/12`,
  `C0 recall-of-reachable line @50 11/11`, `case members top50 3/12`, `scenario covered yes`.
- The `_v2` label fix is proven on kyoushi: the symlinked `kyoushi_v2` run scores (`family
  kyoushi_v2  index hb_kyoushi_s1_v2`, honesty `excluded kyoushi`, exit 0); the same run under
  `santos_v2` is refused (`exit 2`). Rescoring is stable: the v2 score is byte-identical to the
  stored 00:38 score on every field.
- C0.2 fields present: `case_member_recall`, `case_quality.promoted/promoted_unjudged/
  promotion_judged_only`, generator `candidates` (existed) + `attribution@50` + `marginal@50/
  @100`, cost/read receipts.
- Promotion is reported honestly: `promoted 12, promotion_judged_only no, promoted_unjudged 12`;
  relate recall before and after the merge is identical (11/12), so promotion did not inflate.
- **Gap 1 — per-step `cause` is blank on a per-line family.** Every one of the 12 steps has
  `"cause": ""` in the scored JSON and the report prints no `C0 causes` line (the derivation
  exists only on the entity path). C0.2 item 5 is therefore not met on kyoushi.
- **Gap 2 — the receipts contradict themselves on coverage.** `progress.json` `stages.relate.
  coverage_complete` is `true` while `case_receipt.coverage_complete` is `false` (the
  scoreboard prints `False`), and `inventory.fields` counts 16 `complete` + 16 `empty` while
  `case_receipt.lists` counts 32 lists = 16 complete + 0 capped + 0 unavailable — the 16 empty
  lists are neither, so the receipt silently loses half the enumeration.

### S1 — enumeration that works — **FAIL**

- Training-family acceptance ("the spine contains the carrier entity of every graded step"):
  only 7 of 12 steps have a single labelled line in the store at all (see S2), so 5 steps have
  no carrier entity. FAIL as stated.
- The family's dominant source gets no usable value list: `access_combined` (727,925 events)
  contributes exactly one list, `template`, and it is `empty`; the actor slot (`v1`) and the
  object slots (`v2…v6`) are never enumerated.
- 16 of 32 selected fields report `empty`, a status outside the plan's
  `complete|capped|unavailable:<mechanism>|unavailable:<name>` vocabulary; 3 of them are
  `program` and 1 `template` on template-mined sources, 2 are slot names (`v3`, `v4`) that do
  not exist there. In the control, all six `eve.json` `src_ip`/`event_type` lists are `empty`
  after scanning 1,034,760 events, while a live `stats … by src_ip` on the same
  index/sourcetype returns rows — a demonstrable unavailable-reported-as-empty.
- What does work: the Tier-A JSON mechanism. On the tuned index the `suricata` partitions give
  16 complete `src_ip`/`event_type`/`tls.sni`/`dns.rrname` lists via `tstats` (4,515 values in
  36 searches), so the mechanism probe and partition predicate are sound on that sourcetype.

### S2 — spine and episodes — **FAIL (the failing layer)**

- Episode construction over what it was given is sound: of the v2 run's 287 unique read graded
  lines, 286 sit inside an episode and 286 have their host as an entity; the control is
  1,944/1,944 for both. Links hold the 4 h bound: 39,097 links, max `|delta|` 14,399.4 s
  (control 52,783, 14,383.2 s), and the receipt reports episodes and read fraction per source.
- The acceptance fails at the input. The v2 events store contains **0** of the 406,402 graded
  lines in `/apache2/intranet.company.cyberrange.at-access.log.4` (the control contains 554),
  so `attacker_http`, `dirb`, `foothold`, `webshell_upload`, `webshell_cmd` and `reverse_shell`
  have no episode: `attacker_http`, `dirb` and `webshell_upload`/`cmd` are not even reachable
  in the v2 score, while all three loud steps sit at rank 1 in the control.
- The mechanism, measured:

  1. The localiser **did** select the attack buckets. Live replay of its own query
     (`| tstats count where index=hb_kyoushi_s1_v2 by host _time span=1614s | sort - count`):
     `2021-03-23T20:19:12 host=intranet_server 133,143` and `20:46:06 … 282,941`. The receipt's
     `windows 3 / events 434,443 / hosts 2` is those buckets.
  2. The rung-3 read **did** return them. The v2 ledger has
     `stage=behaviours source=access_combined window=1616530752…1616533980 rows=2500 capped=false`,
     and its `values_extracted` are the dirb lines at 20:45–21:12 inside that window.
  3. The parse **discarded** them. The card is `fmt=template` with two templates mined from a
     120-line sample of the consolidated source; both carry literal status/UA tokens
     (`HTTP/1.1`, `200`, `HeadlessChrome/…`). A live `parse_row` of a graded dirb line against
     the v2 card returns `{}`; against the control's per-file card it returns
     `{'v1': '172.16.100.151', 'v2': '[23/Mar/2021:20:45:10 +0000]', 'v3': 'GET',
     'v4': '/wp-content/themes/go/calender', 'v5': '404', 'v6': '363'}`.
  4. The count matches the loss: `events_read 18,786, events_parsed 14,330,
     events_out_of_structure 4,456` (23.7 %); the misfits table holds 90 shapes whose sampled
     examples are attack lines at 21:12–21:13, and the events table holds **0** rows in
     20:19–21:13 (2 rows in the wider 20:40–21:20). No event → no entity → no episode → no case
     member.

The trigger is the tuned index's consolidation (five access files → one `access_combined`
sourcetype, so the per-card 120-line sample changed), not the label, the store or the judge.

### S3 — flows, cases, promotion — **FAIL**

- "≥ 1 case in the top 50 per scenario that contains a B/P member": **0/12 at top 50 and top 100**
  (`dataset_covered false`); the control is 3/12 at top 50. The only v2 case with any graded
  member is at rank 1,448 and its labels are `attacker_vpn`+`foothold` — not an access step.
- The flow signal — the case builder's cross-source mechanism — produced **0 flows** on v2
  (0 skipped) and 0 on control (21 skipped as `flow_roles`), so no case rests on a flow.
- What passes: every case has ≥ 2 pieces of evidence (2,314 cases, `two_evidence_violations 0`);
  `coverage_complete` is reported as `false` and `uncapped_fraction 0.715583 > 0`; promotion is
  marked (`promoted 12`, `promotion_judged_only no`, `promoted_unjudged 12`) so no judged-only
  view is claimed. Case counts: 2,314 v2 vs 4,856 control.

### S4 — estate detections — **NOT EXERCISED on this family**

The plan's acceptance is botsv2 and russell. On kyoushi the alerts generator raised
`candidates 27, kept 27, attribution@50 0` on both runs — present, no exclusive credit. Not a
kyoushi acceptance property; recorded, not graded.

### S5 — weights by marginal contribution — **PASS (mechanism), 51–100 rule not exercised**

The `--weights` re-score over the three v2 family runs (kyoushi/santos/russell) produced the
fold table from re-merges, with the unit floor for an unexercised generator:

```
C4 marginal generator weights
  held out   deviation  misfit  similar_to_known  alerts  peer_rare  relate
  all        6          1       2                 1       1          1
  kyoushi    7          1       2                 1       1          1
  russell    6          1       2                 1       1          1
  santos     4          1       3                 1       1          1
```

kyoushi's own table: `deviation` 16,862 candidates / 121 kept / attribution 6 (0.545) /
marginal 4/4 / weight 4; `similar_to_known` 16,839 / 300 / 5 (0.455) / 3/1 / 3; `misfit` 2,352 /
7 / 0 / 0/0 / 1; `alerts` 27 / 27 / 0 / 0/0 / 1; `peer_rare` 16,839 / 300 / 0 / 0/0 / 1;
`relate` 519 / 0 / 0 / 0/0 / 1. Weights are marginal re-merges, not a global denominator, and a
generator with candidates and no head credit (`alerts`) keeps the unit weight. No generator's
only hit falls at 51–100 on this family, so that acceptance bullet is not exercised here.
`OPEN`: the control reports `marginal@50 = 1` for `alerts`, `peer_rare` and `relate` with
`attribution@50 = 0`; that pairing is unexplained by the current receipts and should be
checked before the fold table is used to seat weights.

### S6 — localise-then-read — **FAIL on "no build-family regression"**

- The selector and rung 3 work (S2, steps 1–2 above), and every source receipt reports
  `read_mode`, `rung`, `events_scanned` and `read_fraction`; the spine receipt repeats them per
  source. Rung-1 acceleration was not available (`accelerated: []` on both runs).
- The regression is real and measured: reachable steps 11→7, case members 3→0 at top 50,
  judge AUC 0.699→0.413, all against a control at the stored baseline. The read volume did not
  rise — 246,595 rows vs 230,237 — so this is not a budget effect.
- The plan's "every read carries `events_scanned`" is only half met: the per-source behaviour
  receipt carries it, the `ledger.jsonl` rows do not (`capped, part, query, reason, rows,
  source_id, stage, values_extracted, window_end, window_start`), so a ledger-only reader
  cannot tell how much a read scanned, and the parse-drop in S2 is invisible in the ledger.

### S7 — judge over cases — **NOT EXERCISED as specified; the ordering claim fails**

- No case was judged: `stages.judge.selection = {policy: stage1_rank, candidates: 755,
  judged: 755}` — one call per **notable**, not per case; `cases.json` has `p_yes` absent and
  `verification` absent on all 2,314 cases. So "a case with an unverified anchor is reported
  unverified", "judged-only views exclude unjudged members" and "no case is dropped by a model
  answer" are unproven by this run (the `judge_cases`/`rerank` path exists in code but did not
  run).
- The ordering that *was* measured is inverted on the tuned run: AUC **0.413** (yes-rate 0.645
  on covering notables vs 0.780 on non-covering) against 0.699 in the control, same served
  model (`gemma-4-26b-a4b-it-QAT-4bit`). §2.6 says `p_yes` orders within the head and is never a
  pass gate; on this family's v2 notables the model's preference is anti-correlated with
  coverage.

## 4. What is unproven / not exercised

- S4's live acceptance (botsv2/russell), S7's case-level bullets, S1's `first_seen_replaced`
  and S1 Tier B are outside this family's acceptance.
- The S5 51–100 marginal rule has no instance on kyoushi.
- The plan's §5 Step 4 held-out proof is untouched (no held-out index was read).
- The `_v2` index was not re-shipped for the `c_host`/`vhost` fix during this dispatch; the
  scores are on the index as built at 00:22.

## 5. OPEN / RISK (for the reviewer)

1. The S2 loss is one parameter away from invisible: the same read produced `rows=2500` in the
   ledger, so only the parse receipt (`events_out_of_structure 4,456`) and the misfits table
   show it. A ledger-only reader would score this run as a coverage success.
2. The v2 recall 11/12 rests on line-mode coverage that matches a notable's TERM against the
   source file, not against rows the run read — the `attacker_http`/`dirb`/`foothold` credits at
   rank 19 are for lines the store never held. Do not quote 11/12 as a read result.
3. `stages.relate.coverage_complete` (true) and `case_receipt.coverage_complete` (false)
   disagree in the same `progress.json`; `inventory.fields` and `case_receipt.lists` account
   for 32 lists as 16 + 0 + 0.
4. The control's `alerts`/`peer_rare`/`relate` `marginal@50 = 1` with `attribution@50 = 0` is
   unexplained; the fold table's unit weights for those generators depend on it.
5. The 10× `read_fraction` difference between the runs is the dropped 22.0 M-event `stats.log`,
   not more reading (9.3 % vs 10.0 % of non-noise events). Any cross-run read-fraction
   comparison on this proof set is invalid without that correction.

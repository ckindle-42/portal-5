# BRIEF — OrcaCyber hunt, deep dive 2 (facts only)

**For:** OrcaCyber (second review). **Written by:** the proof-run lane, 2026-11-21.
**Mode:** read the code, read the plan, read the live receipts. Diagnose the design. **Do not**
propose case-level fixes and **do not** implement. The output is a revised plan and a design
verdict; the orchestrator will split it into lanes.

## 0. What changed since your first review

Your `docs/hunt/ORCACYBER_CODE_REVIEW.md` (2026-11-20) and `docs/hunt/ORCACYBER_HUNT_PLAN.md`
(S0–S7) were implemented. At `35876168e` on `lane/hunt-proof-run` (base == current `origin/main`):

| slice | state | files |
|---|---|---|
| S0 truthful measurement / one path | merged | `notables/scoreboard.py`, `relate.py`, `run.py`, `sample.py`, `judge_notables.py` |
| S1 Tier A + Tier B enumeration | merged | `notables/inventory.py`, `tests/unit/test_hunt_inventory.py` |
| S2 entity spine + episodes | merged | `notables/spine.py`, `notables/behaviours.py` |
| S3 flows/cases/promotion | merged | `notables/relate.py`, `scoreboard.py` |
| S4 estate detections | merged | `notables/cards.py`, `generators.py` |
| S5 marginal weights | merged (measurement only) | `notables/merge.py`, `scoreboard.py` |
| S6 localise-then-read, rungs 1–3 | merged | `notables/sample.py`, `behaviours.py` |
| S7 judge over cases | **not merged** | `judge_notables.py` still judges notables |

Findings for the individual slices are in `coding_task/FINDING_HUNT_S1B.md`,
`FINDING_HUNT_S3.md`, `FINDING_S6_RUNGS23.md`, `FINDING_S6_RUNG1.md`.

The lab Splunk was tuned between rounds: `hb_kyoushi_s1_v2` (2.47 M events),
`hb_ait_santos_v2` (4.47 M), `hb_ait_russellmitchell_v2` (4.19 M) are promoted indexes with
normalised sourcetypes; the originals (24.5 M, 25.1 M, 25.5 M) remain as controls. Ten CIM data
models are accelerated (`Authentication`, `Endpoint` and its `Filesystem`/`Processes`/`Registry`/
`Services` children, `Intrusion_Detection`, `Network_Resolution`, `Network_Traffic`, `Web`), all
reporting `summary.complete=1` and a configured `summary.earliest_time` of 1616425561 (equal to
the `_v2` indexes' first event). The three `_v2` indexes have the same source paths as their
originals and carry CIM tag coverage the originals do not.

## 1. What the live proof run measured

Full receipts, score outputs and command logs: `coding_task/scratch/hunt_proof_20261120T232700/`.
The written report is `coding_task/REPORT_HUNT_PROOF_20261121.md`; read it first.

Method: each family and index ran `cards → behaviours → notables → relate → judge` against the
live lab (read-only), with the judge at Pipeline `:9099` (`hunt-reasoning`, served
`gemma-4-26b-a4b-it-QAT-4bit`). Training indexes only; held-out sets untouched.

### 1.1 Scoreboard (plan §3 baseline in brackets)

| family | index | @50 | reachable | recall of reachable | baseline ROR |
|---|---|---|---|---|---|
| santos | `_v2` | 16/21 | 11/21 | 8/11 | 11/12 |
| santos | orig | 15/21 | 12/21 | 11/12 | 11/12 |
| kyoushi | `_v2` | 11/12 | 7/12 | 7/7 | 11/11 |
| kyoushi | orig | 11/12 | 11/12 | 11/11 | 11/11 |
| russell | `_v2` | 13/22 | 11/22 | 9/11 | 14/15 |
| russell | orig | 15/22 | 15/22 | 14/15 | 14/15 |
| botsv2 | botsv2 | 2/14 loose, 1/14 strict | 6/14 (B+P 6/11) | 2/6 loose, 1/6 strict | 3/14, 5/14, 3/5 |

botsv2 causes: `censored 9, covered 1, instrument 1, not_surfaced 2, unreached 1`.
`case members top50 0/4`; `case recall 0/4`; `relate cases 5,866`, `flows 0`.

### 1.2 Slice properties observed

- **S1 Tier A** — works. `inventory.json` on every family has complete lists with values:
  santos `_v2` 11 complete / 20 empty / 1 capped, 1,495 values, `first_seen_replaced 22`;
  kyoushi `_v2` 16 / 16, 4,515 values; russell `_v2` 13 / 19, 846 values. `tstats` lists on
  `suricata src_ip` return 126–134 values in 0.42–0.44 s (Tier B indexed half).
- **S1 Tier B accelerated half** — never entered. `model_probes 0`, `accelerated []` on botsv2
  and on all `_v2` runs. Six botsv2 lists are `unavailable:mechanism / events_budget`, including
  three `wineventlog:security` lists at 2,178,447 events each. `| rest
  /services/admin/summarization by_tstats=1 | fields datamodel_name …` returns 10 rows but the
  endpoint has **no `datamodel_name` column** (only `summary.complete/earliest_time/latest_time`);
  the code's model list is therefore empty.
- **S6 rung 1** — never fires. `localisation.indexes[0]` is `mechanism=indexed`, `model=""` on
  all three `_v2` runs, with `accel_window` recorded. Facts vs measured summary window:
  santos `[1616425561,1642487481]` vs `[1616425563,1642485717]`; kyoushi
  `[1616425561,1616890440]` vs `[1616425563,1616890431]`; russell
  `[1616425561,1643094189]` vs `[1616425563,1643094189]`. The first event of every index is
  2 s before the first summarised event; `coverage_label` requires strict containment.
- **S6 rungs 2–3** — work and receipt. `localisation` has 3–4 windows per `_v2` index; 9–10
  sources read `anchored`/`narrowed_scan`, 5–6 `whole`; every behaviour receipt carries
  `read_mode`, `rung`, `events_scanned`, `coverage`, `accel_window` (never `coverage=empty`).
  Controls report `accel_window=null`, `mechanism=indexed`.
- **S2 spine** — built on every run: e.g. botsv2 15,921 entities / 125,016 episodes / 219,230
  links; `events_without_entity 53,075`. The scoreboard uses the spine as a reach store
  (`stores {'behaviour':3,'events':4,'ledger':7,'misfit':3,'spine':4}` on botsv2).
- **S3 cases** — 461 / 2,314 / 849 cases on the `_v2` runs, 3,467 / 4,856 / 4,331 on controls,
  5,866 on botsv2; `evidence_violations 0` everywhere; `coverage_complete False` with censored
  `{gap, window}` everywhere; uncapped fraction 0.54–0.90. B/P steps in a top-50 case:
  santos `_v2` 3/21 (`scenario covered yes`), kyoushi `_v2` **0/12 (`scenario covered no`)**,
  russell `_v2` 3/22 (yes), controls 3/21, 3/12, 8/22 (yes), botsv2 **0/4** (baseline 0/4).
  Promotion: `judged_only no lifted 12 unjudged_lifted 12` on every run; no `--judged-only` path
  exists in the CLI.
- **S4** — `alerts existed` 76, 27, 22, 47, 27, 14, 4. Never zero.
- **S5** — `scoreboard --weights` on the `_v2` runs gives a marginal fold table
  (all: deviation 6, similar_to_known 2, others 1; folds 4–7 / 2–3). Live runs nonetheless report
  `weights_source: default` and merge `{alerts 0, deviation 26, misfit 6, peer_rare 0,
  similar_to_known 31}`.
- **S7** — no case-level judge. 813/822, 755/755, 753/753, 800/881, 800/800, 392/873, 392/876
  notables judged; the rest `model_budget_exhausted`. AUC at notable level: kyoushi `_v2` 0.413
  (bad yes-rate .645 vs good .780), botsv2 0.578 (3 bad rows), santos `_v2` 0.952, russell `_v2`
  0.967, kyoushi orig 0.699, russell orig 0.99.

## 2. Where the live run diverged from the plan's predictions

1. **Plan S1B: "`from datamodel=` after stage 3; `inventory.json` gains `accelerated`."**
   Observed: `accelerated []`, `model_probes 0`, because the model probe asks for a field the
   endpoint does not expose. Tier B is unreachable through the merged code.
2. **Plan S6 rung 1: "a model covering the whole range localises from its summary, with no
   rung-2 scan."** Observed: every `_v2` index is `mechanism=indexed`. The summaries are
   `complete=1` and cover all but 2 s of the range; the guard treats that as no coverage.
3. **Plan Step 3 (1): "no build-family regression; recall-of-reachable @50 ≥ §3."** Observed:
   the controls match §3 exactly, but the tuned `_v2` indexes lose 1/4/4 reachable steps and ROR
   falls 11/12→8/11, 11/11→7/7, 14/15→9/11.
4. **Plan Step 3 (2): "botsv2 `keys_reachable` ≥ 12/24 and `steps_reachable` ≥ 10/14."**
   Observed: 6/14 steps (B+P 6/11); 7/20 audited keys (the pre-audit equivalent of 8/24).
   Baseline was 5/14 and 5/20 — a +1 step / +2 key move, not the planned rise.
5. **Plan Step 3 (3): "≥ 3 of 4 botsv2 scenarios have a case in the top 50 naming a B/P
   artefact."** Observed: 0/4. kyoushi `_v2` also fails at 0/12 with `scenario covered no`.
6. **Plan S6: "restricting to the burst window is the coverage win."** Observed: reading more of
   the tuned index reached fewer graded lines than reading less of the original — kyoushi `_v2`
   read 10.0 % of the index and 287 labelled lines, orig read 0.9 % and 1,944; russell `_v2`
   11/22 reachable vs orig 15/22; santos `_v2` 11/21 vs orig 12/21. The anchored windows are not
   the labelled windows.
7. **Plan S3: "the case is the product; cases carry B/P members per scenario."** Observed: the
   rule forms cases with zero evidence violations, but the graded activity is absent from the
   head on kyoushi `_v2` and botsv2.
8. **Plan S5: "replace conditional weights with a measured marginal; keep
   `PORTAL_HUNT_MERGE_WEIGHTS` as the delivery mechanism."** Observed: the measurement exists and
   is marginal; the runs still merge with `default` weights.
9. **Plan S7: "one call per case, ordering only."** Observed: no case-level judge was merged; the
   stage is per notable, and on one family `p_yes` is anti-correlated with the label (AUC 0.413).
10. **Plan S0: "the ledger is the ground truth for what was read."** Observed: the ledger exists,
    but raw line recall can exceed the reachable ceiling (santos `_v2` 16/21 covered vs 11/21
    reachable; botsv2 2/14 loose vs 6/14 reachable) because line coverage is source+term/window
    attribution, not read evidence. `relate` reports `coverage_complete=True` while the case
    receipt and scoreboard report `False`. Case `unjudged` flags are written before the judge.

## 3. Facts-only problem statement for the dive

No fixes are proposed. The facts the second dive must explain and redesign around:

- A complete, accelerated summary exists for each `_v2` index, and the strict coverage guard
  rejects it by seconds. Whether the guard's *semantics* (interval containment of an index-wide
  range against a model-specific event range) is the right gate is an open design question.
- The accelerated value list is unreachable because its model discovery reads a field this
  Splunk does not return. The dependency between S1's wide-source list and the same acceleration
  inventory as S6 rung 1 is not shared: S6 discovers models by probing each model directly, S1
  by a REST field.
- The narrow windows selected by rung 2 on the tuned indexes contain less graded activity than a
  uniform/whole read of the original. The ladder's premise — "the estate's peak buckets are where
  the rare thing is" — is not supported by these three families.
- Cases form correctly but do not carry the graded scenario on kyoushi `_v2` and botsv2; the same
  rule does carry it on the originals. The difference is the read set, not the two-evidence rule.
- Measured marginal weights exist but are not on the run path; the default weights rank botsv2
  one step lower @50 than the stored baseline.
- The judge is notable-level, not case-level, and its yes-rate is not stable across indexes for
  the same labels (AUC 0.413–0.99). Ordering-only was specified; nothing enforces it.
- The instrument now has five reach stores but no single read-gated recall: "covered" and
  "reachable" are computed on different rules, and a reader cannot tell which number is coverage.

## 4. Access terms (same as your first review)

- **Code:** the whole worktree `/Users/chris/projects/portal-5-hunt-proof-run` at `35876168e`;
  the hunt lives in `portal/modules/security/core/hunt/notables/`. Read anything, change
  nothing.
- **Lab Splunk:** `https://10.0.1.30:8089`, Splunk 10.2.5, read-only. Credentials are exported
  **by name** from the live checkout's `.env` (`LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`,
  `LAB_SPLUNK_PASSWORD`, `LAB_SPLUNK_HEC_URL`, `LAB_SPLUNK_HEC_TOKEN`), rewriting
  `host.docker.internal` to `localhost`. **Never source `.env`.**
- **Indexes:** training families only — `hb_kyoushi_s1[_v2]`, `hb_ait_santos[_v2]`,
  `hb_ait_russellmitchell[_v2]`, `botsv2`. **Never open, query or read** `hb_ait_wheeler`,
  `hb_cloudobs_aws`, `botsv1` or any of their keys.
- **No changes** to Splunk configuration, no `launch.sh` beyond `help`, no code changes.
- **Receipts:** `coding_task/scratch/hunt_proof_20261120T232700/` (per-family `progress.json`,
  `inventory.json`, `cases.json`, `notables.jsonl`, score outputs and command logs). The stored
  C0.1 run is `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/`.
- **Keys:** training-family keys only, at
  `/Volumes/data01/portal5_hunt/corpora/{botsv2_keys/keys.jsonl,hunt_bed/kyoushi_s1_ingest/keys.jsonl,ait_lds_v21/{santos,russellmitchell}_ingest/keys.jsonl}`.

## 5. Deliverable

A second review document (facts → diagnosis → revised plan), not a patch:

1. Which of the plan's S0–S7 assumptions the live run falsifies, and why.
2. The redesigned mechanism for **localisation before reading** given that (a) accelerated
   summaries exist but cover model-specific event ranges, and (b) peak buckets did not contain
   the graded activity on the tuned indexes.
3. The redesigned mechanism for **wide-source enumeration** that does not depend on a REST field
   this build does not return.
4. The unit-of-evidence and case-formation rule re-examined against "the case did not carry the
   graded scenario on the tuned index".
5. How the instrument reports one read-gated coverage number, and how the judge is wired to cases
   before ranking, with no pass gate.
6. A slice order and merge condition for each slice. Constants stay effort budgets unless a slice
   explicitly derives them by LOFO on kyoushi/santos/russell; never on botsv2.

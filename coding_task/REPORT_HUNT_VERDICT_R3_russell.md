# REPORT — Hunt Round-3 live proof & verdict for **russell** (`hb_ait_russellmitchell_v2`)

**russell: falls short.**

Lane `lane/hunt-proof-r3-russell`, worktree `/Users/chris/projects/portal-5-hunt-proof-r3-russell`,
base `a62f9bc459bd2bd87fb90846c3d0967393434d03` (= current `main`: E0–E7 all merged; `git log --oneline -5`
shows `merge: lane/hunt-e4` at HEAD). Brief `coding_task/BRIEF_HUNT_PROOF_R3_russell.md`; acceptance
`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6–§7 (slices E0–E7).

One fresh full hunt (`--stage all`) ran against `hb_ait_russellmitchell_v2`, judged through the live
Pipeline, and was scored against the neon control. No code and no Splunk configuration was changed by
this lane; `launch.sh` was never run; `.env` was never sourced (the six named keys were exported by
name only, no secret appears here). Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were
never opened, queried or read.

**Verdict basis:** 15 of the 17 brief acceptance checks pass. E2's live acceptance fails on both of
its scoring clauses — `C0 ceiling … reachable` is **11/21**, not ≥ 15/21, and **none** of
`attacker_http, dirb, wpscan, webshell_cmd, webshell_upload` is reachable (three `instrument`, two
`censored`). E2's *store* clause does pass: **1,533** `intranet_server` `access_combined` rows
(target 725, Round-2 204).

```bash
# the run (judge/embedding env per brief; PORTAL_HUNT_MERGE_WEIGHTS exported first)
export PORTAL_HUNT_MERGE_WEIGHTS=$PWD/coding_task/scratch/hunt_proof_r3_russell/merge_weights_neon_3fam.json
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_russellmitchell_v2 \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r3_russell/v3/russell \
  --stage all --family russell \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos                    # EXIT=0, 1707.62 s wall
# the verdict
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r3_russell/v3/russell \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights --json \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/russell
```

Judge env: `PORTAL_HUNT_JUDGE_URL=http://localhost:9099`, `PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning`
(served `gemma-4-26b-a4b-it-QAT-4bit`), embeddings `google/embeddinggemma-2`, keys via
`PORTAL_HUNT_*_KEY_ENV=PIPELINE_API_KEY`. Pipeline `/health` 200 and the Splunk REST endpoint
answered 200 before the run.

## 0. Run receipt (progress.json / run.log, EXIT=0)

| stage | wall | searches / model reqs | notes |
|---|---:|---|---|
| cards | 53.3 s | 83 / 7 | 17,184 rows |
| behaviours | 421.3 s (receipt 180.9 s) | 906 / 0 | `events_read 206,108`; `files_indexed 90, files_omitted 73`; read_modes `{anchored 12, whole 3}`; misfit_lines 160,455 / shapes 1,875; spine 3,264 entities / 21,058 episodes / 23,847 links |
| notables | 289.2 s | 337 / 0 | 796 merged; `weights_source` = the exported neon vector, `weights_defaulted: null`; similar_to_known reliability_auc 0.4178 |
| relate | 7.8 s | 40 | 272 cases, 283 related events, 64 flows, 12 promoted, `coverage_complete True` |
| judge | 935.3 s | 0 / 485 | 485 judged / 338 unjudged (`model_budget_exhausted`), 1.48 s/call |
| **total** | **1,699.1 s** (real 1,707.6 s) | **1,617 / 492** | rows 616,506; read_fraction 0.2726; peak 3,570 MB |

Artifacts: run dir `/Volumes/data01/portal5_hunt/hunt_proof_r3_russell/v3/russell` (plain directory,
no symlinks). Score JSON/text, run log, grade script + output, and a read-only Splunk helper live in
`coding_task/scratch/hunt_proof_r3_russell/` (that path is gitignored by `coding_task/`).

## 1. Per-slice table (E0–E7) — exactly what the brief asked for

Grader: `coding_task/scratch/hunt_proof_r3_russell/grade_russell.py`, output `grade_out.txt`;
**15/17 PASS**. Two FAILs are the E2 scoring clauses.

| slice | verdict | exact receipts |
|---|---|---|
| **E0** receipt honesty | **PASS** | `progress.json:stages.behaviours.files` = 555 rows, **0** with `rows == 0` and an empty `reason`; reasons are `''`, `empty_window`, `host_mismatch`. 11 receipts carry `coverage: accelerated` and **11/11** carry a non-null `accel_window` (`[1616425563.0, 1643094167.000001]`). Ledger refusals are declared (`reason` on 251 `host_mismatch` + 300 `censored` rows); the searches blocks report `censored 0` for every kind, so no `request_budget_exhausted` row was owed. |
| **E1** estate map carries time | **PASS** | `sources.json:cards[access_combined].facts.files` = 21 entries with `first`/`last`. Graded file `/apache2/intranet.smith.russellmitchell.com-access.log.2`: `first 1642919773.0, last 1642999045.0`, `events 8530` — **identical** to live `\| tstats count min(_time) as first max(_time) as last where index="hb_ait_russellmitchell_v2" source="…/intranet.smith.russellmitchell.com-access.log.2"` → `count 8530, first 1642919773, last 1642999045` (Δ 0 s). Sourcetype span `1642686439.0–1643061469.0`, i.e. **not** equal to the file's range. |
| **E2** file-driven placement | **FAIL on the scoring clause** | Store: `select count(*) from events where source_id like '%:access_combined' and host='intranet_server'` = **1,533** ≥ 725 ✓ (Round-2: 204). Placement: the burst window **is** now read — `progress.json` window 3 `[1642972621, 1642999045]` contains the live densest hour (`\| tstats … by _time span=1h` → `2022-01-24 03:00 7,698`, file total 8,530), and the ledger shows `search … source="…/intranet.smith.russellmitchell.com-access.log.2" \| sort - _time \| head 2500` returning **2,500 rows, 2,499 of them in hour 03**. Scores: **`C0 ceiling reachable 11/21`** (target ≥ 15/21) ✗; **none** of the five named steps reachable — `attacker_http instrument, dirb instrument, wpscan instrument, webshell_cmd censored, webshell_upload censored` ✗. File rows 5,983 of 8,530 (446 + 383 + 2,500 for `.log.2`, 1,120 / 933 / 601 for `.log.4/.3/.1`), every `host` empty or in the file's `hosts`. Root cause in §3. |
| **E3** per-source localisation | **PASS** | `localisation.indexes` = **10 entries, one per source** (`error, log, syslog, dnsmasq, postfix_syslog, suricata, access_combined, linux_secure, logstash, linux_audit`), each with `source`; mechanisms `accelerated 9, accelerated_partial 1` (> 0 ✓), each with its own `accel_window`; `syslog` (the one whose own span exceeds the summary window) declares `covered_window` + `scanned_window [[1616425561, 1616425563], [1643094167.000001, 1643094188.000001]]`. **11 read receipts** carry `coverage: accelerated` with `accel_window` (rungs `narrowed_scan 12, whole 3`) — the Round-2 "scan only" receipt is gone. |
| **E4** budget scope | **PASS** | `stages.behaviours.clock = {job_seconds 720.0, remaining_s 720.0, requests_spent 83}` — the stage's first read saw the full clock (≥ 715 ✓); `stages.behaviours.searches.total = 906` ≤ 2000 ✓ (the scoreboard cost line counts 1,617 across all stages, also ≤ 2000). No `HuntDeadlineExceededError`; EXIT 0. |
| **E5** notables contract | **PASS** | `progress.json:stages.notables.skipped_sources = {}` ✓. The one intentional skip is receipted separately as a behaviour skip: `{card_id …suricata:fast, reason: "kind:alert", behaviours: 0}` — the alert-card path E5 owns, not a fatal abort. `notables` completed: 796 merged, `notables.jsonl` written. |
| **E6** estate-map reader | **PASS** | `C0 evidence absent (excluded from the step denominator)  crack_passwords 49/49 labelled lines` ✓ and `C0 ceiling steps 11/21` with `steps_all 22` → **denominator 21** ✓. `index_map: ledger estate map, 91 source paths` — the reader now accepts the `by sourcetype source host` row. |
| **E7** judge measurement | **PASS (reporting)** | `judge auc_pooled 0.385 over deviation,misfit,peer_rare,alerts,set_novelty` (similar_to_known excluded by construction); `auc_by_generator` printed per generator (`deviation 0.56`, `peer_rare 0.36`, `alerts n/a`, `misfit n/a`, `similar_to_known 0.979`); `similar_to_known yes-rate 0.973 (judged 258, excluded from auc_pooled)`. Sub-test not runnable: this build has no `--generators` flag, so the "pooled moves ≤ 0.02 when the similar budget changes" check cannot be issued (see §5). |

## 2. Scoreboard vs the neon baseline

```
recall  top50 13/22   top100 13/22   all 15/22   notables that cost {'50': 50, '100': 100, 'None': 823}
  quiet 5/13 @50   loud 8/9 @50
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 936/61862
C0 evidence absent  crack_passwords 49/49 labelled lines
C0 recall-of-reachable  line @50 9/11  @100 9/11  all 9/11
C0 causes  censored 6, covered 9, instrument 4, not_surfaced 2, unreached 1
C0 step diff vs …/snap_neon_02cc2e3/results/hunt/neon/russell
  covered@50  lost webshell_cmd, webshell_upload   gained -
  reachable   lost attacker_http, dirb, webshell_cmd, webshell_upload, wpscan   gained exfiltration-service
judge  judged 485 bad 276 good 209 AUC all 0.937 (yes-rate bad 0.935 / good 0.507)
judge auc_pooled 0.385 over deviation,misfit,peer_rare,alerts,set_novelty
judge similar_to_known yes-rate 0.973 (judged 258, excluded from auc_pooled)
relate cases 272  case members top50 10/22  scenario covered yes  unjudged_lifted 0
cost total=1699.054s searches=1617 rows=616506 read_fraction=0.272576 peak=3570.4MB
```

Baseline re-scored in place (`scoreboard --out <neon/russell> --keys … --weights`), same code:

```
notables 850 {'similar_to_known': 300, 'deviation': 204, 'misfit': 34, 'alerts': 12, 'peer_rare': 300}
recall  top50 15/22   top100 17/22   all 17/22
C0 ceiling  steps 15/22 reachable  labelled lines read verbatim 873/61862
C0 evidence absent  n/a (the run wrote no ledger)
C0 recall-of-reachable  line @50 14/15  @100 14/15  all 14/15
```

So against the control: raw @50 **15 → 13**, reachable **15 → 11** (five web steps lost, one gained),
read-relative recall of reachable **14/15 → 9/11**. The run reads *more* labelled lines (936 vs 873)
but they are almost all one step's lines (925 of the 936 are `dnsmasq` lines, i.e.
`attacker`/`dnsteal`/`dnsteal-received`), and none of the graded file's 7,691 web-request lines is
credited.

## 3. Why E2's scoring clause fails — two measurable layers, neither a tuning knob

Verified in this order; each claim has its own command.

1. **The burst window is read, but only its newest 2,500 events.** Live
   `| tstats count … by _time span=1h` on the graded file: `2022-01-24 03:00 GMT = 7,698` of the
   file's 8,530 events. The file's own `first/last` slice the file into three even windows; the third
   `[1642972621, 1642999045]` contains that hour, and the ledger row for it
   (`… \| sort - _time \| head 2500`) returned 2,500 rows — **2,499 in hour 03**, 1 in hour 04.
   Placement is fixed (Round-2's 6-of-7 empty windows are gone); the **head is still the tail's
   2,500 of a 7,698-event burst (32 %)**. `head = min(per_read, events_in_window)` and newest-first
   ordering both hold as written; neither reads the densest hour's events.

2. **The 2,499 read lines never reach the store the scoreboard reads.** The `access_combined` card is
   a template model built from a 120-line sample: `sources.json:template.templates` has **2**
   templates and both require a `Mozilla/5.0 …` user agent. The burst lines carry
   `"python-requests/2.27.1"`. Reproduced offline with the run's own stored model
   (`TemplateModel.from_dict(card["template"])`):

   ```
   burst  '172.19.131.174 - - [24/Jan/2022:03:58:20 +0000] "GET / HTTP/1.1" 200 9291 "-" "python-requests/2.27.1"' → fields {}
   benign '10.143.3.65 - - [21/Jan/2022:05:55:22 +0000] "GET / HTTP/1.1" 200 6202 "-" "Mozilla/5.0 …Firefox/86.0"' → fields {template, v1…v6}
   ```

   Receipt: `access_combined events_read 116,466, events_parsed 57,230, events_out_of_structure 59,236
   (unparsed_share 0.509)`. Consequences, both counted:

   - `behaviours.duckdb`: **0** `access_combined` rows in the burst hour
     (`raw like '%[24/Jan/2022:03:%'` → 0; `ts BETWEEN 1642993200 AND 1642996800` → 0 for this source,
     295 rows for six other sources). The 1,533 `intranet_server` rows are the benign baseline hours
     (max 80 events/hour), which is why the store clause passes while the ceiling does not.
   - the read lines survive only as **misfit examples**: 28 `access_combined` shapes carry an
     `[24/Jan/2022:03:` example (one example per shape).

3. **The scoreboard's per-line reachability reads only `events.raw`.** `_line_read_lines()`
   (`scoreboard.py:589`) does `SELECT raw FROM events` and nothing else, so neither the ledger's
   `values_extracted` (which holds the 2,499 burst lines) nor `misfits.examples` can credit a line.
   That is why `labelled lines read verbatim` stays at 936 and `reachable` at 11/21 although the run
   demonstrably read 2,499 of the 7,691 web lines.

The three together are one story: **the burst is read by window, dropped at keying by the template
model, and invisible at credit by the per-line reader.** No single slice owns all three — E2 owns
placement, the template model is the `cards` sample, and the per-line credit rule is the scoreboard.

## 4. What the round did prove on russell

- **E0** — no silent zero-row read anywhere (555 rows), and `coverage: accelerated` is now carried on
  read receipts with a real `accel_window` (11/11), which Round-2 could not produce.
- **E1** — per-file `first`/`last` matches live `tstats` to the second and is not the sourcetype's span.
- **E3** — localisation is per source (10 entries), `accelerated` fires on 9 + 1 `accelerated_partial`
  with `covered_window`/`scanned_window` declared; rung 1 is observable in the receipt.
- **E4** — the behaviours clock starts at 720 s (not the residue of cards), and the whole run stays
  inside 2,000 searches (906 in behaviours).
- **E5** — `skipped_sources: {}`; the alert-card skip is receipted, not fatal.
- **E6** — `crack_passwords 49/49` prints and the denominator is 21 (Round-2 printed `n/a`).
- **E7** — stratified judge reporting exists: pooled 0.385 over the declared stratum, per-generator
  table, `similar_to_known` yes-rate 0.973 reported separately.
- **E2 store clause** — 1,533 `intranet_server` `access_combined` rows vs Round-2's 204; the per-file
  route receipts 21/21 files and the burst window is planned.

## 5. Limits of this proof

- One family (russell) only, per the brief. The E2 finding is measured on russell's graded file; the
  same template/head interaction would need each family's receipts to be called cross-family.
- The judge left 338 of 823 notables unjudged (`model_budget_exhausted`) and ran 935 s; the pooled
  AUC (0.385) and the generator table are computed on the judged set as the scoreboard reports them.
  The deep dive's ±0.02 stability sub-test needs a `--generators` flag this build does not have.
- `parsed vs out_of_structure` is measured from the run's own receipt plus a store count; the
  template-parse repro uses the run's stored model and one example line per class, not the full
  2,499.
- Everything above is from this run's own artifacts (plus two read-only Splunk `tstats` calls and one
  scoreboard re-score of the stored control). Nothing was written to the index, the knowledge store
  or Splunk.

## 6. Reproduce

```bash
cd /Users/chris/projects/portal-5-hunt-proof-r3-russell
uv run python coding_task/scratch/hunt_proof_r3_russell/grade_russell.py        # 15/17 PASS
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r3_russell/v3/russell \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/russell
# shows: reachable 11/21, covered@50 lost webshell_cmd+webshell_upload, crack_passwords 49/49
uv run python - <<'PY'
import json, duckdb
run = "/Volumes/data01/portal5_hunt/hunt_proof_r3_russell/v3/russell"
b = json.load(open(f"{run}/progress.json"))["stages"]["behaviours"]
print("silent empties", [r for r in b["files"] if r["rows"] == 0 and not r["reason"]])
con = duckdb.connect(f"{run}/behaviours.duckdb", read_only=True)
print("store intranet access", con.execute(
    "select count(*) from events where source_id like '%:access_combined' and host='intranet_server'").fetchone()[0])
print("store burst-hour access", con.execute(
    "select count(*) from events where source_id like '%:access_combined' and ts>=1642993200 and ts<1642996800").fetchone()[0])
PY
```

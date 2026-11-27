# FINDING: botsv2 `--stage all` finds nothing — where each key is lost, what is setup, and two root fixes

Lane: `lane/hunt-root2` · 2026-11-27 · status: diagnosis complete from stored artifacts; two
product fixes implemented and verified offline on real objects (no network, no inference, no
Splunk); every live number below is from the stored run and every live re-run is the
orchestrator's.

Run read: `/Volumes/data01/portal5_hunt/hunt_proof_r4_solo/botsv2` (progress `updated
2026-11-22T00:57:52Z`, code between `aec16e81f` and `3c041c4fa`), rescored with the HEAD
scoreboard. Build-family baselines: `/Volumes/data01/portal5_hunt/hunt_proof_r4_solo/{kyoushi,
santos,russell}/<family>/` (`_v2` indexes), rescored the same way. Proof data was not opened.

## 1. Verdict

| headline | dominant cause | class |
|---|---|---|
| keys reachable 8/20 | 12 keys sit in sources the run never read: newest-N slices of 0.12 %–8.7 % of 47 k–55.5 M-event sources, on the index the runbook keeps as **the untuned control** (`docs/hunt/SPLUNK_SETUP_RUNBOOK.md:55` "The untuned control is `botsv2`", `:70` acceleration "physically cannot build summaries over `botsv2`") | **setup** — the plan's own bar says so (`docs/hunt/ORCACYBER_HUNT_PLAN.md` Step 3 item 2: on today's untuned index "this bar is unreachable by construction … the bar is 'ceiling reported with a per-key cause and no regression'") |
| recall 0/14 @50 | of the 8 reachable keys, 6 appear in no notable at all and 1 is surfaced only at rank 97 (misfit); 9 of the top 50 slots are deviation notables computed from a series read that never ran (defect D1) | product (D1 fixed here; the rest reported) |
| cases 0/4 | needs a covered step first; 0 steps are covered in the top 50 | consequence |
| alerts existed 0 | `--stage all` runs every stage on one job clock; behaviours ran 830.964 s of 720 s and the notables stage inherited the sticky `job_deadline_exceeded`: all 299 of its reads were refused (defect D1) | **product defect, not setup** — pass-bar item 4 ("`alerts existed > 0`") fails on this alone |

So the stop condition in the brief is met for the reachability number: it is setup, and §6 gives
the steps. Two product defects are certain, independent of setup, small, and are fixed here (D1,
D3). Neither is expected to lift `keys_reachable` by itself; that claim belongs to the live run.

## 2. What was and was not exercised

Exercised: the stored `progress.json`, `ledger.jsonl` (2,088 rows), `inventory.json`,
`notables.jsonl`, `receipts`, on four runs; the HEAD scoreboard on those runs; the product's own
code on real objects (`HuntExecutor` + `SplunkWindowSource` over `httpx.MockTransport`, a real
empty behaviours store written by `behaviours_stage`).
Not exercised: Splunk (no `health()`, no search), inference, any live hunt, botsv1 / proof data.

## 3. Loss table — 12 unreachable keys (never read by the stored r3, r3_solo or r4_solo botsv2 runs: no ledger cell, event, behaviour, entity or inventory value holds them)

Carrier = `docs/hunt/BOTSV2_DIAGNOSIS.md:52-75` (earlier live audits, doc-sourced, not re-verified
here). "Read" = `progress.json:stages.behaviours.receipts[*]` summed over the source's part
receipts (`events_available`, `events_read`, `notes`); a part reads at most 1,368 events.

| key (events) | carrier | what the run read of that carrier | lost at | cause group |
|---|---|---|---|---|
| `updatexml` (1139) | mysql SQL_TEXT + stream:http burst 2017-08-16 08:24–08:38 | mysql:transaction:details **0 / 26,756,085** (9 `censored`); stream:http 10,032 / 1,424,596 (0.70 %) | behaviours read | D3 + S |
| `eidk.duckdns.org` (12), `eidk.hopto.org` (8) | stream:dns only | stream:dns 4,104 / 1,186,677 (0.35 %) | behaviours read | S |
| `Frothly_marketing_campaign_Q317.pptx.crypt` (10) | osquery_results / stream:smb / ps | osquery_results 4,104 / 47,178 (8.7 %); stream:smb 1,368 / 211,155 | behaviours read | S |
| `Important_HR_INFO_for_mkraeusen` (5), `befa9bfe…271` (2) | osquery_results only | osquery_results 4,104 / 47,178 | behaviours read | S |
| `torbrowser-install` (382) | winregistry 228 + sysmon 128 | winregistry **0 / 55,528,820** (3 `censored`); sysmon 1,368 / 1,106,383 (0.12 %) | behaviours read | D3 + S |
| `Saccharomyces_cerevisiae_patent.docx` (98) | stream:smb 74 + sysmon/security/winregistry/winhostmon | stream:smb 1,368 / 211,155; winhostmon 49,248 / 3,413,063; security 0; winregistry 0 | behaviours read | D3 + S |
| `winsys32.dll` (7) | wineventlog:security 4 + sysmon 3 | wineventlog:security **0 / 2,178,447** (ledger: 3 censored reads); sysmon 1,368 / 1,106,383 | behaviours read | D3 + S |
| `Software\Microsoft\Network` (119) | winhostmon 103, security 7, sysmon 5, winregistry 4 | winhostmon 49,248 / 3,413,063 (1.4 %); security 0; winregistry 0 | behaviours read | D3 + S |
| `invoice.doc` (5), `invoice.zip` (9) | smtp 4 + sysmon 2 + security 1 + winhostmon 1 + winregistry 1 | smtp 8,208 / 670,760 (1.2 %); sysmon 1,368; security 0; winregistry 0 | behaviours read | D3 + S |

Unreachable steps (6 of 14): `brewertalk_web/xss_cookie_theft` (scoreboard `unreached`; its only
key carries no credit), `fruitfly/c2_beacon`, `fruitfly/usb_malware_delivery`,
`insider_leak/covert_channel`, `taedonggang_phish/scheduled_task_persistence`,
`taedonggang_phish/spearphish_attachment` (all scoreboard `censored`).

**D3** = product defect fixed here (§7.2): the per-file read put a `sort` before `head`, so the
three widest carriers were read as 0 rows. **S** = setup/design limit: a 2–382-event needle in a
47 k–55.5 M-event source is not in a newest-N slice, and nothing enumerates rare values on an
unaccelerated index (`inventory.accelerated []`, `model_probes 0`; inventory: 33 searches,
`mechanisms {stats: 29, tstats: 3}`).

Would D3 alone have reached any of these keys? Not expected — reasoned, not measured: the fixed
read takes the newest 456 rows of a 10.33-day window that holds ~726 k security events or ~9 M
mysql events, and a 4–228-event needle is not expected in those rows. D3 restores coverage on
seven sources (three of them from zero); reachability needs enumeration or localisation that the
untuned index cannot afford.

## 4. Loss table — 8 reachable keys, 1 surfaced

Scoreboard `C0 ceiling … stores {'behaviour': 3, 'events': 4, 'inventory': 2, 'ledger': 8,
'misfit': 2, 'spine': 4}`, `C0 causes censored 9, not_surfaced 4, unreached 1`.

| key | where it exists | why nothing surfaces it | cause group |
|---|---|---|---|
| `kIagerfield` | 33 csp-violation events (source read whole, 2,260 / 2,290); 2 behaviour rows; 1 spine entity | the name exists only URL-encoded inside a `document-uri` value: the behaviour's object is that URL and the spine minted it as a `file` entity, never a `user`; 0 notables mention it | product limit (reported) |
| `45.77.65.211` (168,004 events) | 97 pan:traffic + 12 csp-violation events read; 5 behaviour rows (pan:traffic fields carry generic names `c5`/`c8`/`c9`); `address` entity; member of 3 cases | peer_rare kept 300 of 8,481 and this actor was not among them; its exact counts were refused (D1); its default merge weight is 0; 0 notables mention it | product limit + D1 + run config |
| `berkbeer.com` | one ledger cell (an SMTP recipient address) | no event, behaviour or entity; 0 notables | product limit (reported) |
| `mberk@berkbeer.com`, `hbernhard@berkbeer.com` | inventory list `sender_mail_from` (complete) and a ledger cell | a value that appears only in an inventory list mints no notable (`apply_inventory` corrects and adds candidate rows only) | product limit (reported) |
| `나는_데이비드를_사랑한다.hwp` | 2 stream:ftp events (source read whole); `file` entity; 1 episode; 0 behaviours (the FTP `filename` field is keyed as shape) | no behaviour, so no behaviour-based generator can rank it; 0 notables | product limit (reported) |
| `GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt` | misfit | surfaced at ranks 97 and 224 (misfit), outside the top 50 | ranking |
| `/member.php` | events/behaviour/spine | credited only together with `updatexml`, which was never read | follows row 1 of §3 |

"0 notables mention it" = a case-insensitive substring search of the stored `notables.jsonl`.

## 5. Causes ranked by what they explain

| # | cause | keys / steps explained | class | status |
|---|---|---|---|---|
| 1 | Untuned control: no Stage 3/4 acceleration → newest-N slices of wide sources, no rare-value enumeration, rung-2 localisation | 12 keys, 6 steps unreachable | setup | §6 steps; operator decision |
| 2 | D1 notables stage starved by the previous stage's clock | alerts existed 0; 299 reads refused (alerts 24, peer_rare exact counts 274 + 26 `no_index_terms`, deviation series 1); 9 of the top 50 are degenerate deviation rows | product defect | **fixed** (§7.1) |
| 3 | D3 non-streaming per-file read | 22 reads on 7 sources returned 0 rows; 3 sources read as 0 | product defect | **fixed** (§7.2) |
| 4 | Read-but-unsurfaced / inventory-only values never mint notables | 5 reachable keys (rows 1–5 of §4) | product limit | reported |
| 5 | Judge budget truncation | none at @50: the cut (378 unjudged, `judge_stage_budget_exhausted`) falls after rank 422 and the judge does not reorder (`ranking.order merged_file_order`) | run budget | reported |
| 6 | botsv2 run merged on default weights (`merge.weights_source default`, alerts 0 / peer_rare 0); the build-family run merged on measured weights | caps the effect of a live alerts/peer_rare generator | run config | reported |

## 6. Setup steps (for cause 1) — from the runbook and realism doc, not executed here

The families are already tuned (`_v2` indexes; their stored runs show localisation `accelerated` /
`accelerated_partial`). botsv2 is not, by the runbook's own decision. To lift its ceiling:

1. Operator decision 4 of `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` §8: end botsv2's role as the
   untuned control (keep another index as the control) — or keep 8/20 as the declared pre-setup
   target.
2. Add `botsv2` to the six `cim_<Model>_indexes` macros in Splunk_SA_CIM's local config (the
   runbook's Stage 1 mechanism scopes them to the three `_v2` indexes).
3. Runbook Stage 3 on botsv2: accelerate `Authentication`, `Endpoint`, `Network_Traffic`, `Web`,
   `Network_Resolution`, `Intrusion_Detection` with `acceleration.earliest_time = -451d` (the
   runbook's `-10y` covers it), serial build; `Change` last or never (55.5 M winregistry).
   Cost, doc §5.3: ≈19 M events, ~10 min for the six, +~30 min with `Change`.
4. Verify as in runbook Stage 5, then in the product's own receipt: `inventory.accelerated`
   non-empty, `model_probes > 0`, per-source `localisation.mechanism == "accelerated"`.
5. Tier B (a complete list over `wineventlog:security` / `winregistry` in ≤5 s) additionally needs
   Stage 4 index-time extraction, which needs a from-raw reindex that does not exist on disk for
   BOTS v2 (runbook §7).

## 7. Fixes

### 7.1 D1 — the notables stage starts its own clock in `--stage all`

Evidence (stored run): `stages.behaviours.clock = {job_seconds 720.0, remaining_s 720.0,
requests_spent 635}` at its head and `seconds_total 830.964` (inventory 335.06 s — the 180 s cap
of `3c041c4fa` postdates the run — reads 392.168 s, spine 99.706 s). `stages.notables`:
`alerts {existed 0, kept 0, notes [job_deadline_exceeded ×24]}`, `peer_rare.exact_counts
{counted 0, queries 300, reasons {read_failed:HuntDeadlineExceededError: 274, no_index_terms: 26}}`,
`deviation.series {error: HuntDeadlineExceededError, seconds 0.0}`, `seconds {alerts 0.004,
deviation 0.019, total 91.122, similar_to_known 90.972}`. Ledger: 299 `notables` rows, every one
`job_deadline_exceeded`, 0 rows returned. Relate's 65 reads ran because `relate_stage` calls
`executor.budget.restart_clock()` (`relate.py:1582`), as `behaviours_stage` does (`run.py:562`);
the CLI's notables step did not.

Change: `notables/__main__.py` `main()` calls `executor_for(search).budget.restart_clock()`
before `notables_stage`, the way relate does. The product job path is untouched: its
`_enter_stage` and the stage loop already give each stage its own deadline and clear a
stage-deadline exhaustion between stages (`product_jobs.py:353-372, 478-484`). `notables_stage`
now records `receipt["clock"]` (the proof field; behaviours already records the same).

Offline verification (no labels involved — the trigger is the notables receipt alone):
`tests/unit/test_hunt_bounded.py::test_a_notables_run_after_an_expired_stage_starts_its_own_clock`
runs the real CLI `main(["--stage", "notables", "--generators", "deviation"])` over a real
executor and a real empty store, with the budget left sticky by a "previous stage". Before the
fix the notables ledger rows read `job_deadline_exceeded` (the stored signature); with
the fix they read `null` and the budget is live. Limit counters (requests, cells, events) stay
global, as for every other stage.

### 7.2 D3 — per-file reads stream instead of sorting the window first

Evidence (stored ledger, same run, same index): every behaviours-stage read shaped
`search index="botsv2" … | sort - _time | head 456` on a 10.33-day window of a high-volume source
was `censored` with 0 rows — 22 reads: mysql:transaction:details 9, wineventlog:security 3,
winregistry 3, perfmon:process 3, stream:tcp 2, stream:http 1, stream:ip 1. The cards stage read
the same seven sources over the same windows (identical bounds on the four sources checked:
mysql:transaction:details, perfmon:process, wineventlog:security, winregistry) with `… | head N` and
no sort: 21 reads of 400 rows and 18 of 40 rows, none censored — winregistry (55.5 M events) and
mysql:transaction:details (26.8 M) included. A `sort` must scan the whole window before its first row; `head` stops at N.

Order is not lost: Splunk returns a bounded search newest first. In the four stored ledgers every
windowed `head` read with ≥3 timestamps is non-increasing in `_time` (botsv2 313, kyoushi 43,
santos 39, russell 36) and its first row sits at the window end (max gap 9.5e-07 s), and
`read_windows` has always declared "`head`" as "newest events first inside each" (`sample.py`
`read_windows`). Both functions re-sort the rows ascending client-side afterwards.

Change: `read_files` and `read_card_sample` issue `… | head N` (four query sites, two
docstrings). No budget classification changes: `query_budget_kind` is by `| tstats` prefix and
`per_sample_cap` reads `head (\d+)`.

Offline verification (no labels involved — the ledger's read outcomes alone select it):
`tests/unit/test_hunt_bounded.py::test_per_file_reads_stream_the_newest_rows_without_a_leading_sort`
runs both functions on a real executor and asserts every raw query is
`search index="i" source="<file>" | head <n>`. On HEAD the observed queries carry `| sort - _time |`.
Build-family exposure: their stored behaviours stage issued 292 / 404 / 304 reads of this shape
(kyoushi / santos / russell), none censored, so the fix changes no coverage there and should
return the same newest rows faster — reasoned from the ledger, to be confirmed live.

## 8. Reported, not fixed (out of this brief's fix scope or not validatable offline)

- **Rung-2 localisation is index-wide.** `sample.py::localise_query` is
  `| tstats count where index=I by host _time span=Ws` and `_scan_windows` shares one cache
  ("fetched once over the shared span and sliced per source"). In the stored run 58 of 61
  `stages.behaviours.localisation.indexes` entries are the identical record
  `{mechanism indexed, windows 2, width 3600, hosts 1, events 4806489}`: every source's anchored
  reads landed on the estate's two busiest hours, and 205 of 318 anchored `head` reads declined
  with `host_mismatch`. The build families show the same symptom (243 / 189 / 251 `host_mismatch`
  reads) while meeting their bars. Candidate: scope the aggregate to the source's route. Not
  changed: a query path that cannot be exercised without Splunk.
- **A failed deviation series still mints first-seen notables**: `origin` falls back to `start`
  (0.0), so 9 of the top 50 say "first appeared 17410.0 days in" (epoch days). Ordering is
  unaffected (a constant offset); the text shown to the judge is wrong. Disappears with D1 on a
  live run; the fallback itself remains.
- **peer_rare exact counts fail on every build family**: `read_failed:HuntSearchFailedError` 300 /
  299 / 299 (kyoushi / santos / russell). `_exact_count` sends
  `| tstats count where index=I "term" …` with bare quoted terms and no `TERM()`, and keeps only
  the exception class, so the cause is inferred. On botsv2 these reads were refused earlier, by D1
  (`HuntDeadlineExceededError` 274): this is what botsv2 will show once D1 is fixed.
- Inventory field choice: of 40 fields, trivial ones were selected (`parse_only` 125 in total:
  stream:dns `name`, smtp `attach_filename`, stream:http `uri_path`, osquery `columns.*`,
  suricata `http.url`), and 3 probes `failed:censored`, one on the raw path
  `sourcetype="wineventlog:security" | head 1` over an unbounded window (ledger row 667).
- The scoreboard's whole-word artefact regex (`(?<!\w)…(?!\w)`, `scoreboard.py:418`) cannot match
  `kIagerfield` inside `username%3DkIagerfield%26`; reachability is a substring test, so the key is
  reachable but never creditable.
- The FTP `filename` field is keyed as shape, so the `.hwp` literal never becomes a behaviour
  (0 behaviour rows for a `file` entity the spine did mint).
- peer_rare ranks 8,481 behaviours down to 300 with ties at the cut broken `['measure',
  'specificity', 'events', 'lexical']` (`tied_at_cut 1057`); the actor `45.77.65.211` was not kept.
- relate: 4 of 65 reads censored, all `… TERM("172.31.10.10") … | sort limit=20 _relate_delta`
  over 20.66 days of stream:tcp — the same non-streaming-sort pattern, smaller loss.
- `coding_task/RUN_HUNT_REDESIGN.sh` still names the untuned originals (`hb_kyoushi_s1`,
  `hb_ait_santos`, `hb_ait_russellmitchell`); the stored baselines are on the `_v2` indexes the
  runbook §7 says to point `--index` at.

## 9. Offline numbers and their label exposure

| number | value | botsv2's labels could have influenced it? |
|---|---|---|
| botsv2, stored run, HEAD scoreboard | keys 8/20, steps 8/14 (B+P 6/11), loose 0/14 @50, 1/14 @100, strict 0, cases 0/4, alerts existed 0 | the run itself is leave-one-family-out (`honesty.families [kyoushi, russell, santos]`); the number reads botsv2's keys, by definition |
| kyoushi, stored `_v2` run, rescored | recall 11/12 @50, 12/12 @100; reachable 11/12; alerts 27 | no — own keys, own run, knowledge `[russell, santos]` |
| santos, stored `_v2` run, rescored | recall 14/21 @50, 16/21 @100; reachable 13/20; alerts 46 | no — knowledge `[kyoushi, russell]` |
| russell, stored `_v2` run, rescored | recall 13/22 @50, 13/22 @100; reachable 15/21; alerts 22 | no — knowledge `[kyoushi, santos]` |
| D1 / D3 test before/after | refused → live; `sort … head` → `head` | no — selected by the notables receipt and the ledger's read outcomes, which name sources and reasons, not keys |

There is no offline "after" number for recall or reachability: both need Splunk.

## 10. Live proof (orchestrator)

Run from the live checkout after merge (it carries `.env`); a worktree has no `.env`. Everything
below is the form `coding_task/RUN_HUNT_REDESIGN.sh` uses, except that the families run on the
tuned `_v2` indexes the stored baselines used — the committed script still names the untuned
originals (runbook §7 says to point `--index` at `<index>_v2`).

```bash
cd /Users/chris/projects/portal-5
source scripts/lib/host_dotenv.sh && portal_export_dotenv_keys "$PWD/.env" PIPELINE_API_KEY
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099 PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099 PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2 PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables
store=/Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb
corpora=/Volumes/data01/portal5_hunt/corpora
out=$(mktemp -d /Volumes/data01/portal5_hunt/hunt_proof_root2.XXXXXXXX)

# 1. build families, no regression (leave-one-family-out; ~12 / 17 / 15 min)
uv run python -m $hunt --index hb_kyoushi_s1_v2           --out $out/kyoushi --stage all --family kyoushi --knowledge-store $store --knowledge-families santos,russell
uv run python -m $hunt --index hb_ait_santos_v2          --out $out/santos  --stage all --family santos  --knowledge-store $store --knowledge-families kyoushi,russell
uv run python -m $hunt --index hb_ait_russellmitchell_v2 --out $out/russell --stage all --family russell --knowledge-store $store --knowledge-families kyoushi,santos

# 2. botsv2, its own family held out of the knowledge (~29 min + the notables reads)
uv run python -m $hunt --index botsv2 --out $out/botsv2 --stage all --family botsv2 \
  --knowledge-store $store --knowledge-families kyoushi,santos,russell

# 3. score (same scoreboard as this finding)
uv run python -m $hunt.scoreboard --out $out/botsv2  --keys botsv2=$corpora/botsv2_keys/keys.jsonl
uv run python -m $hunt.scoreboard --out $out/kyoushi --keys kyoushi=$corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl
uv run python -m $hunt.scoreboard --out $out/santos  --keys santos=$corpora/ait_lds_v21/santos_ingest/keys.jsonl
uv run python -m $hunt.scoreboard --out $out/russell --keys russell=$corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl
```

Bar for 1: no lower than the stored `_v2` runs rescored in §9 — recall-of-reachable @50
kyoushi 10/11, santos 10/13, russell 11/15; recall @50 11/12, 14/21, 13/22; `alerts existed`
27 / 46 / 22; 0 censored behaviours reads. The plan's §3 values (11/11, 11/12, 14/15) are the
original-index bar and are what `RUN_HUNT_REDESIGN.sh` measures as committed.

Bar for 2, all in `$out/botsv2/progress.json` and `ledger.jsonl`:
- `stages.notables.clock.remaining_s` is the job seconds (720.0) — the stage began with a live clock;
- `stages.notables.alerts.existed > 0` (pass-bar item 4), no `job_deadline_exceeded` note anywhere in
  the notables receipt, no notables ledger row with that reason, `deviation.series` carries no `error`;
- the ledger holds no read containing `| sort - _time |`, and
  `wineventlog:security`, `winregistry`, `mysql:transaction:details` have `events_read > 0`;
- coverage item 2 stays BLOCKED, not failed, until §6 lands; a ceiling that does not rise is a
  finding about read policy, not a reason to raise the budget (plan Step 3).

Step 3 of the plan: set `HUNT_WEIGHTS_FROM=<a scored build-family run>` as the script documents, so
botsv2 merges on a measured marginal taken from the build families only (the stored botsv2 run
merged on defaults).

Proof, once, at the very end — plan Step 4, unchanged: final code against `hb_ait_wheeler`,
`hb_cloudobs_aws` and `botsv1`, `--stage all --allow-proof`, scored and reported as-is.

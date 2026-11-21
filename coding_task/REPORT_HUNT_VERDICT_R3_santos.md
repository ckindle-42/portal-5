# REPORT — Hunt Round-3 live proof & verdict for **santos** (`hb_ait_santos_v2`)

**santos: falls short**

Lane `lane/hunt-proof-r3-santos`, worktree `/Users/chris/projects/portal-5-hunt-proof-r3-santos`,
base `a62f9bc45` (all eight slices E0–E7 merged: E0/E1/E2/E3/E5/E6/E7 via `fc7d84cc3`, E4 via
`a62f9bc45`). Brief `coding_task/BRIEF_HUNT_PROOF_R3_santos.md`; acceptance
`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6–§7.

No code, no Splunk configuration and no `launch.sh` was changed or run. Held-out sets
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or read; no query in
this lane names them. `.env` was read by key name only (six named keys, never `source`d); no secret
appears in this report.

Verdict summary: **E0, E1, E3, E4, E5, E6, E7 pass their brief acceptance lines. E2 fails the C0
clause (reachable 9/20 vs required ≥12/20; `attacker_http`, `dirb`, `wpscan` still unreachable).**
The file-read mechanism itself returned the required rows; the attack burst they contain was then
discarded as out-of-structure by the `access_combined` template model.

## 0. Preflight (before the run)

| check | receipt |
|---|---|
| Splunk | `https://10.0.1.30:8089` answered `services/server/info`, version **10.2.5**, build `1d180ea50aed` |
| target index | `hb_ait_santos_v2` present (index list read with `count=0`; no held-out index queried) |
| Pipeline judge | `GET /v1/models` lists `hunt-reasoning`; a 1-token probe answered `Yes`, served `gemma-4-26b-a4b-it-QAT-4bit` |
| Pipeline embedding | `POST /v1/embeddings model=google/embeddinggemma-2` returned **768** dims |
| inputs | `keys.jsonl` 7,799,762 B; `knowledge_v2_20261116.duckdb` 8,925,184 B; neon baseline dir present |
| merge weights | `PORTAL_HUNT_MERGE_WEIGHTS={"alerts":1,"deviation":2,"misfit":1,"peer_rare":1,"relate":1,"similar_to_known":5}` (brief-supplied neon 3-family vector; `weights_source: override`) |
| output | `/Volumes/data01/portal5_hunt/hunt_proof_r3_santos/v3/santos` |

## 1. Live index facts used by E1/E2 (read-only `tstats`, `hb_ait_santos_v2` only)

```text
| tstats count min(_time) as first max(_time) as last where index=hb_ait_santos_v2 source="/apache2/intranet.smith.santos.com-access.log" by sourcetype source host
  count=9462  first=1642400738 (2022-01-17 06:25:38Z)  last=1642451200 (2022-01-17 20:26:40Z)  host=intranet_server

| tstats ... where index=hb_ait_santos_v2 sourcetype=access_combined by sourcetype host
  intranet_server count=15784 first=1642142365 last=1642451200   (sourcetype-wide: first=1642085133, last=1642458113)
  other hosts: cloud_share 44244, hayes_mail 20319, mail 95368, rogersturnbull_mail 3634, webserver 150093

| tstats count where index=hb_ait_santos_v2 source="<graded file>" by _time span=1h
  2022-01-17 11:00 = 7894 of the file's 9462 events (densest hour); 10:00 = 51, 12:00 = 190
```

The graded file's own range starts four days after its sourcetype's range and its densest hour is
11:00Z. Index-wide `access_combined` on `intranet_server` is 15,784 events.

## 2. Run receipt

```text
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out /Volumes/data01/portal5_hunt/hunt_proof_r3_santos/v3/santos \
  --stage all --family santos \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,russell
```

`progress.json:stage = judge` (final stage), `updated 2026-11-21T22:26:15Z`, `run.log` has no
traceback.

| stage | wall | model req | searches | notes |
|---|---:|---:|---:|---|
| cards | 35.746 s | 6 | 83 | 17 cards / 14 sources, 0 unparsed |
| behaviours | 490.092 s | 0 | 1,316 | events_read **264,917**; behaviours 3,384; read_modes `{anchored 11, whole 3}`; unfit lines 241,493 |
| notables | 118.066 s | 0 | 337 | total 779; weights_source `override`; `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` |
| judge | 1,272.299 s | 774 | 0 | 769 judged / 804; 35 unjudged `{timeout 5, model_budget_exhausted 30}`; served `gemma-4-26b-a4b-it-QAT-4bit` |
| **total** | **1,916.203 s** | **780** | **1,779** | rows 772,482; read_fraction 0.300207; peak 3,762.8 MB |

## 3. Per-slice table (E0–E7)

| slice | verdict | exact receipts |
|---|---|---|
| **E0** receipt honesty | **PASS** | `progress.json:stages.behaviours.files`: **0** rows with `rows == 0` and empty `reason` (595 file rows; 214 empty, all declared: `host_mismatch` **189**, `empty_window` **25**). 10 receipts with `coverage: accelerated`, **10/10** carry a non-null `accel_window`; coverage values seen `{accelerated, accelerated_partial, whole}`. `ledger.jsonl` reasons `{host_mismatch: 189, censored: 300}`; the search ceiling was not hit (1,779/2,000) so no `request_budget_exhausted` row was due. |
| **E1** per-file estate time | **PASS** | Graded file in `sources.json:cards[hb_ait_santos_v2:access_combined].facts.files`: `first=1642400738.0`, `last=1642451200.0`; its sourcetype's facts are `first=1642085133.0`, `last=1642458113.0` — **not equal**. Both file values match the live `tstats` exactly (0 s difference). **95/95** indexed files carry a non-zero time range. |
| **E2** file-driven placement | **FAIL (mechanism passes, C0 clause fails)** | Graded file: **6** receipts, rows **430 + 2,500 + 738 = 3,668** (≥2,500), `events_available=9462`; every read has `host=""` and `hosts=["intranet_server"]` → **0 off-host**. Store `events where source_id like '%:access_combined' and host='intranet_server'` = **7,459** (≥1,000). **`C0 ceiling steps 9/20 reachable` — required ≥12/20 — `attacker_http`, `dirb`, `wpscan` all `reachable: false`.** `covered@50` 5/20. The 3 zero rows are declared `host_mismatch`; `access_combined` receipt says `files_indexed 21 / files_routed 21 / files_omitted 20`. |
| **E3** per-source localisation | **PASS** | `localisation.indexes` has **10** entries (one per wide source, not one per index); mechanisms `{accelerated: 9, accelerated_partial: 1}`; no `indexed` entry. The partial (syslog) carries `covered_window [1616425563.0, 1642485679.000001]` and two `scanned_window` pieces `[[1616425561.0, 1616425563.0], [1642485679.000001, 1642487481.000001]]`. 10 read receipts carry `coverage: accelerated` (E0's enabling half). |
| **E4** budget scope | **PASS** | `stages.behaviours.clock = {job_seconds 720.0, remaining_s 720.0, requests_spent 83}` (≥715). Total searches **1,779 ≤ 2,000** (behaviours receipt 1,127; scoreboard stage 1,316). Cards' 35.7 s is not charged to the read clock. |
| **E5** notables contract | **PASS** | `stages.notables.skipped_sources = {}`; notables completed and wrote `notables.jsonl` (779 rows in `progress.json`, 804 lines on disk incl. `set_novelty: 25`); `progress.json:stages.notables.similar_to_known` present. |
| **E6** estate-map reader | **PASS** | Scoreboard line exactly: `C0 evidence absent (excluded from the step denominator)  crack_passwords 44/44 labelled lines`; `ceiling.steps = 20`, `steps_all = 21`; `index_map = "ledger estate map, 89 source paths"`. |
| **E7** judge measurement | **PASS** | `judge judged 769 bad 37 good 732 AUC all 0.242`; **`judge auc_pooled 0.365 over deviation,misfit,peer_rare,alerts,set_novelty`**; per-generator table printed: `alerts n/a (47/0/47, yes 0.638)`, `deviation 0.401 (123/25/98, yes 0.366)`, `misfit n/a (9/0/9, yes 0.556)`, `peer_rare n/a (295/0/295, yes 0.488)`, `similar_to_known 0.05 (295/12/283, yes 0.871)`. **`judge similar_to_known yes-rate 0.871 (judged 295, excluded from auc_pooled)`** — reported separately. |

## 4. Scoreboard vs neon baseline

```text
C0 ceiling  steps 9/20 reachable  labelled lines read verbatim 1004/47367
C0 evidence absent (excluded from the step denominator)  crack_passwords 44/44 labelled lines
C0 recall-of-reachable  line @50 5/9  @100 8/9  all 9/9
C0 modes  line 9/21 @50  16/21 @100  18/21 all
C0 step diff vs /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos
  covered@50  lost attacker, dns_scan, dnsteal, dnsteal-received, network_scan,
              service_scan, traceroute, webshell_cmd, webshell_upload  gained -
  reachable   lost attacker_http, dirb, wpscan  gained -
judge  judged 769  bad 37  good 732  AUC all 0.242
judge auc_pooled 0.365 over deviation,misfit,peer_rare,alerts,set_novelty
judge similar_to_known yes-rate 0.871  (judged 295, excluded from auc_pooled)
cost total=1916.203s  searches=1779  rows=772482  read_fraction=0.300207  peak=3762.8MB
```

Neon baseline: `covered@50 18/21`, `reachable 12/21`. Round-3 reaches **9/20** (denominator 20
after the E6 adjustment) and covers 5 reachable steps @50 (9/9 at all). Against neon it loses 9
covered steps and 3 reachable steps and gains none. It also regresses against the stored Round-2
run (which printed `reachable 11/21`, `lines read 3353`): two previously-reachable steps
(`attacker_change_user`, `exfiltration-service`) are lost and the labelled-line read count falls
to 1,004.

## 5. Why E2 fails — the burst is read, then discarded

The E2 mechanism is visible and works to the letter of its sub-properties:

- `sources.json` carries the graded file's own time range (E1), and the file read plan uses it:
  three slices of `[1642400738, 1642451200]`, the middle one
  `[1642417558.67, 1642434379.33]` (11:05:58–15:46:19Z), with `| sort - _time | head 2500`.
- That middle read returned 2,500 rows and its tail **is** the 11:22Z WPScan burst: the ledger row
  for the read ends with `172.21.128.119 ... [17/Jan/2022:11:22:35 +0000] "HEAD ..." 404 ...
  "WPScan v3.8.20"` values. So placement, host and head all reached the attack traffic.

What defeats the slice is the parser, not the planner. The `access_combined` card's template model
has only two templates (HeadlessChrome count 66, Firefox count 53). An offline call with the run's
own card on a WPScan line returns:

```text
fmt template  templates=2 (HeadlessChrome 66, Firefox 53)
parse_row(WPScan line).fields = {}
card.in_part({}) = True
```

The run's own receipt agrees: `events_read 128,805 / events_out_of_structure 40,354`
(`unparsed_share 0.313295`, `events_keyed 88,451`). The store bears it out: only **447** rows fall
inside the middle read's window and only **85** in the 11:00Z hour, against the live 7,894; the
graded file's 2,500-row burst was read and then counted as out-of-structure. This is also why
`C0 ... labelled lines read verbatim` falls from 3,353 (R2) to 1,004.

A second, independent loss is visible in the file plan's own receipt: `files_routed 21 /
files_omitted 20` on `access_combined`, with 189 `host_mismatch` refusals in the ledger (the
anchored pass declines files not on the anchor's host). Those files may still be read by another
pass, but the aggregate is fewer credited lines, not more. The graded file is read; its labelled
burst is the part that is discarded.

**Conclusion for E2:** the read-side mechanism meets its stated rows/host/store numbers, but the
acceptance line that matters — `C0 ceiling reachable ≥ 12/20` with `attacker_http`, `dirb`, `wpscan`
reachable — fails (9/20). This is a parser/template-coverage gap exposed by dense, non-browser
user agents, not a failure to place the read.

## 6. Not done / unproven

- E7's stability check in the deep dive (re-run with `--generators` without `similar_to_known`;
  pooled AUC must not move by more than 0.02) was not run — it needs a second full hunt, which the
  brief did not ask for. The brief's E7 line (report pooled, per-generator and similar separately)
  is met.
- One live run only; no repeat to bound run-to-run variance. The verdict is against this run's
  receipts.
- botsv2 was not run (not this brief's family); E4's botsv2 clause is untested here.
- `relate` `coverage_complete` is `True` in `progress.json` but the scoreboard prints
  `coverage_complete False` / `uncapped_fraction 0.835046`; not part of E0–E7 acceptance, noted for
  the reviewer.

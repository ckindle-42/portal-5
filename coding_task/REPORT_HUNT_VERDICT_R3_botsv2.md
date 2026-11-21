# botsv2: falls short

Graded 2026-11-21 on `lane/hunt-proof-r3-botsv2`, HEAD `a62f9bc45` (clean tree), against
`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6–§7 (slices E0–E7) on `main` with all eight slices merged.
Splunk `botsv2` only, read-only: no code change, no Splunk configuration change, no `launch.sh`,
no `.env` sourced (six keys exported by name from the live checkout's `.env`). Held-out sets
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or read.

**The control's four graded properties still hold** — `keys_reachable 7/20` (floor 5/20),
`mechanism: indexed`, `C0 causes` non-empty, `honesty` non-null, and E5 now completes with
`similar_to_known` present. **But the brief's own run does not succeed:** the literal `--stage all`
**exits 1** after 18 m 58 s with `HuntDeadlineExceededError: job_deadline_exceeded`, raised in
`relate` because the behaviours stage alone consumed the whole 720 s job clock (733.0 s of
`seconds_total`, `clock.remaining_s` 720.0 at its head). The run therefore has no judge, no
cases and no promotion, and its behaviour read is **45 of 712 planned file-windows** — every
graded and wide source (`wineventlog:security`, `stream:http`, `suricata`, `pan:traffic`,
`access_combined`, `winhostmon`) was refused by the deadline and returned **0 rows**, so every
coverage number below is a floor, below R2's degraded run.

## 0. What was run

One run, one working tree, one lab box (Pipeline `:9099`, `hunt-reasoning` → live; embeddings
`google/embeddinggemma-2`; lab Splunk 10.2.5 at `https://10.0.1.30:8089`).

| step | command | outcome |
|---|---|---|
| the brief's run | `uv run python -m portal.modules.security.core.hunt.notables --index botsv2 --out /Volumes/data01/portal5_hunt/hunt_proof_r3_botsv2/botsv2 --stage all --family botsv2 --knowledge-store …/knowledge_v2_20261116.duckdb --knowledge-families kyoushi,santos,russell` | **EXIT 1**, wall 18:58.25 (1138 s) |
| the verdict | `…notables.scoreboard --out …/botsv2 --keys botsv2=…/botsv2_keys/keys.jsonl --weights --json` | EXIT 0, 3.9 s |

Stage receipts (from `progress.json` / log):

| stage | wall | searches (budget queries) | rows | outcome |
|---|---|---|---|---|
| cards | 388.6 s | 625 | 107,947 | completes, 104 sources / 144 cards, 113 model requests (556.3 model-s) |
| behaviours | **733.0 s** (`seconds_total`; 452.4 s of reads) | 339 | 10,434 events, 534 behaviours | completes its receipt, its plan is cut by the deadline |
| notables | 13.3 s | 278 (all refused) | 0 | completes: 703 notables, `similar_to_known` present |
| relate | ~280 s | 9 (all refused) | 0 | **raises `HuntDeadlineExceededError`** (`relate.py:1530 → executor.py:548`) |
| judge | — | — | — | never reached |

`clock.remaining_s` at the behaviours head is **720.0** (the brief asks ≥ 715) — E4's restart does
what it says. The clock then expires *inside behaviours*: `seconds_total` 733.0 > `job_seconds`
720.0, and the first `job_deadline_exceeded` ledger row is behaviours row 965 of 1,396.

## 1. The brief's acceptance properties

| property | result | receipt |
|---|---|---|
| **E4 — EXIT 0** | **FAIL** | process exit 1; `HuntDeadlineExceededError: job_deadline_exceeded` |
| **E4 — `clock.remaining_s ≥ 715`** | pass | `progress.json:stages.behaviours.clock {"job_seconds":720.0,"remaining_s":720.0,"requests_spent":625}` |
| **E4 — `events_read > 0`** | pass | `behaviours: events_read=10434` |
| **E4 — no `HuntDeadlineExceededError`** | **FAIL** | raised in relate; 2 traceback lines in `run_all.log` |
| **E4 — `searches.total ≤ 2000`** | pass | behaviours 339; whole process 1,251 budget queries (625+339+278+9) |
| **E4 — every `winhostmon` row `rows > 0` or non-empty `reason`** | pass in letter, **not in substance** | 45 `winhostmon` rows: **0 rows read**; reasons `job_deadline_exceeded` 27, `host_mismatch` 18 |
| **E2×E4 probe interaction** | reported | `grep -c '"| tstats' ledger.jsonl` = **828** vs `search index=` = **1,478**; in behaviours, 570 `tstats` (171 ok / 399 refused) against 824 `search` rows (155 ok / 456 refused / 207 `host_mismatch` declared / 5 censored / 1 `query_bound`) |
| **E5 — full generators complete** | **pass** | `notables: enabled=['alerts','peer_rare','deviation','misfit','similar_to_known'] … total=703`; `stages.notables.similar_to_known` present; `similar_to_known kept=300` |
| **E5 — no `pan:threat` `SimilarityError`** | **pass** | `pan:threat` is an alert card (`skipped botsv2:pan:threat: kind:alert behaviours=0`); `skipped_sources {}`; no traceback |
| **E5 — `notables.jsonl` exists** | **pass** | 703 lines (`wc -l`), 0 lines mention `pan:threat` |
| **Control — `keys_reachable ≥ 5/20`** | **pass** | `C0 ceiling keys 7/20 reachable steps 7/14 (B+P 5/11)` |
| **Control — untuned `mechanism: indexed`** | **pass** | 63 localisation entries, `mechanisms {'indexed': 63}`, `accelerated: []`, read `coverage` `{scan: 88, whole: 13}` |
| **Control — `promoted_unjudged == 0`** | **vacuous pass** | `promotion effect promoted=0` — relate crashed, so nothing was promoted; the property has no carrier |
| **Control — `C0 causes` non-empty** | **pass** | `C0 causes censored 9, covered 2, not_surfaced 2, unreached 1` (a per-step cause for all 14 steps) |
| **Control — `honesty` non-null** | **pass** | `honesty {"knowledge":"loaded","families":["kyoushi","russell","santos"],"knowledge_items":2431,…}`; scoreboard `honesty … excluded botsv2 reliability AUC 0.588` |
| **E0 — 0 silent zero-row file rows** | **pass** | 712 file rows, 667 zero-row, **0** with an empty `reason` |
| **E7 — stratified `judge auc_pooled` / `auc_by_generator` / `similar_to_known` yes-rate** | **not measurable** | `judge: no judge result in this run (omitted)` — judge never ran |

## 2. Slice table E0–E7 on botsv2

| slice | property on this family | result | receipt |
|---|---|---|---|
| **E0** receipt honesty | a planned read that returned nothing, or was refused, is declared with a reason | **pass** | of 667 zero-row file rows: `job_deadline_exceeded` 456, `host_mismatch` 207, `censored` 3, `query_bound` 1 — **0 silent**. Ledger: 2,308 rows; every refused read carries a reason; 0 `request_budget_exhausted` (the request ceiling was never reached, 1,251/2,000). Read coverage `scan 88 / whole 13`, `accelerated` 0 (untuned, expected) |
| **E1** per-file time range | every file fact carries its own `first`/`last`, not the source's | **pass** | 281 estate-map file rows carry `last > 0`; e.g. `access_combined /var/log/httpd/access_log` `first 1501545656.0 last 1504223987.0`; **independent live check** `\| tstats min(_time) as first max(_time) as last count where index="botsv2" sourcetype="access_combined" source="/var/log/httpd/access_log"` → `first 1501545656 last 1504223987 count 393038` (exact), and it differs from the sourcetype's own span (`1501545603–1504223987`) at the head |
| **E2** file-driven placement | windows from the file's range, file's own host, density head | **plan-level pass; execution not observed** | 0 file rows issued with a host not in `hosts`; 136 reads carried a host filter; 0 dense probes silent. But of 712 planned file-windows only **49 were issued** (45 read), 456 refused by the deadline — and every wide/graded source read **0 rows**: `pan:traffic` 160 planned / 0 read, `stream:http` 14/0, `wineventlog:security` 5/0, `suricata` 5/0, `access_combined` 10/0, `winhostmon` 45/0 |
| **E3** per-source localisation | one entry per source; `accelerated` where the summary covers it | **pass as the control** | `localisation.indexes` 63 entries, 63 unique `source` keys (one per source), `mechanisms {'indexed': 63}`. `accelerated` absent is the expected untuned result (botsv2 is outside the CIM allowlist); no entry is the old one-per-index shape |
| **E4** budget scope & planned ceiling | cards' wall time is not a read cost; the plan is budgeted | **FAIL** | restart works (`remaining_s 720.0`), but behaviours alone needs 733.0 s (inventory 272.3 s + reads 452.4 s) > 720 s, so the plan is cut mid-stage and the next read stage raises. The request planner is not the binding constraint (339 of 2,000), so the refusals are `job_deadline_exceeded`, not `request_budget_exhausted` |
| **E5** notables contract | completes with an alert-card candidate present; skips non-consuming sources | **pass** | full generator set completes in 13.3 s, 703 notables, `similar_to_known` present with `skipped_sources {}`; `pan:threat` (alert, 2 events) minted no candidate and aborted nothing |
| **E6** estate-map reader | reads the path set the run wrote; `evidence_absent` adjusts the denominator | **not exercised on this family** | botsv2 scores entity mode; the `evidence_absent`/`index_map` block is line-mode only (`scoreboard.py:_line_ceiling`). No key is absent on botsv2 (13/14 steps have a reachable artefact). E6's carrier is santos/russell |
| **E7** judge measurement & prompt | stratified `auc_pooled`, `auc_by_generator`, ranked yes-rate | **not measurable** | `judge` block `null`; no cases were written because relate crashed. The pre-judge `similar_to_known` reliability AUC is 0.588 (`stages.notables.similar_to_known`), not a verdict |

## 3. Why the run fails

**E4 fixed the wrong clock for this estate.** `run.py:522` calls `executor.budget.restart_clock()`
at the head of `behaviours`, so cards' 388.6 s is no longer charged to reads — correct, and the
receipt proves it (`remaining_s 720.0`). But the behaviours stage's *own* work is 733.0 s on this
estate: 272.3 s of inventory (33 searches) plus 452.4 s of file reads, and the read plan is
**712 file-windows**. `plan_within_requests` (`sample.py:835`) trims that plan against the
*request* ceiling only (1,375 free at the head), so nothing is dropped up front; the deadline then
cuts the plan while it executes, at behaviours ledger row 965. The executor's `exhausted` flag is
sticky, so every later read in every later stage is refused — notables' inventory (278 rows, all
`job_deadline_exceeded`), then relate (9 rows, then the raise). `_run_relate` catches only
`FileNotFoundError`/`ValueError`, so the exception ends the process at exit 1 and judge never runs.

The plan's priority order (`-events, path, -start`) sorts within a source, but the source loop
runs small sources first: the ten sources that were read are `ms:o365:management`,
`weblogic_stdout`, `stream:icmp`, `stream:smtp`, `linux_audit`, `linux_secure`,
`symantec:ep:agt_system:file`, `stream:smb`, `windowsupdatelog`, `stream:ftp`. The graded
evidence (`wineventlog:security`, `stream:http`, `suricata`, `access_combined`) is planned last
and never read. That is why the scoreboard is worse than R2 even though `keys_reachable` holds:
reachability is computed from the estate map and inventory (which did run), coverage from the
notables (which were built on 10,434 events).

**E2×E4 probe interaction, measured.** E2's density probe is one `tstats` per planned file-window
(`sample.py:_window_events`). In behaviours that is 570 `tstats` rows against 824 `search` rows —
41 % of the stage's ledger — and discovery is 221 requests / 337.0 s of the 998.1 s query time,
spent before the 49 behaviour reads. The probes themselves were cut too (399 refused). The
per-file route and the density probe are individually cheap; together, on a 104-source estate,
they do not fit the 720 s job clock, and nothing plans against wall time.

## 4. Scoreboard, baseline and R2

| measure | stored baseline (re-scored) | R2 C (degraded, stage-split) | **R3 (`--stage all`, this run)** |
|---|---|---|---|
| keys reachable | 5/20 | 7/20 | **7/20** |
| steps reachable | 5/14 (B+P 5/11) | 6/14 (6/11) | **7/14 (5/11)** |
| loose @50 / @100 / all | 3 / 3 / 3 | 3 / 4 / 4 | **2 / 3 / 3** |
| strict @50 / @100 / all | 2 / 2 / 2 | 2 / 2 / 2 | **2 / 3 / 3** |
| scenarios loose @50 | 2/4 | 2/4 | **1/4** |
| class @50 (B / P / T) | — | — | **0/5, 1/6, 1/3** |
| case recall top50 | — | 0/4 | **0/4 (no cases)** |
| promoted / unjudged lifted | — | 10 / 0 | **0 / — (relate crashed)** |
| judge | — | 725 judged, AUC 0.84 | **none** |
| notables | — | 725 | **703** (`similar_to_known` 300, `peer_rare` 300, `deviation` 100, `misfit` 3) |
| read fraction | 0.117 % | 0.150 % | **0.451 %** (1,020,900 rows / 226,317,740) |
| search requests | — | 2,804 | **2,308 ledger rows / 1,251 budget queries** |
| peak memory | — | — | 3,883.8 MB (notables; compare 388 MB behaviours) |

**`C0 step diff` vs the stored baseline** (`--baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/botsv2`):

```
covered@50  lost brewertalk_web/malicious_account, brewertalk_web/web_scan, taedonggang_phish/ftp_download
            gained insider_leak/competitor_recon, insider_leak/patent_exfil
reachable   lost brewertalk_web/web_scan
            gained insider_leak/competitor_recon, insider_leak/executive_contact, insider_leak/patent_exfil
```

Per-step causes: `censored 9` (`sql_injection`, `web_scan`, `c2_beacon`, `macbook_file_encryption`,
`usb_malware_delivery`, `covert_channel`, `ftp_download`, `scheduled_task_persistence`,
`spearphish_attachment`), `covered 2` (`competitor_recon` @49, `patent_exfil` @49), `not_surfaced 2`
(`malicious_account`, `executive_contact`), `unreached 1` (`xss_cookie_theft`, 0 labelled lines).

The `keys_reachable` figure is the same as R2's because reachability is read from the estate map,
the inventory and the ledger (which all completed); the coverage collapse is the truncated read.

## 5. Proven and not proven

**Proven (live, read-only, this run):** `--stage all` exits 1 with `HuntDeadlineExceededError` at
relate; the behaviours stage records `remaining_s 720.0` at its head and then runs 733.0 s, so its
plan is cut by the job clock (456 file-window refusals, first at ledger row 965); every graded and
wide source read 0 rows; notables completes with all five generators and no `SimilarityError`;
`keys_reachable 7/20`; `mechanism: indexed` on 63 per-source localisation entries with no
`accelerated`; `C0 causes` non-empty; `honesty` non-null; 0 silent zero-row file reads; the estate
map carries per-file ranges that match a live `tstats` to the second.

**Not proven / not measured:** the judge block (no judge stage — so E7's `auc_pooled`,
`auc_by_generator` and ranked yes-rate do not exist for this run); promotion and `promoted_unjudged`
(relate crashed, nothing promoted — the printed 0 is vacuous); E2's executed-read properties on the
graded files (their windows were never read); E6 (line-mode only, no carrier on botsv2). Single run:
the structure argues reproducibility (733 s > 720 s is measured, not incidental), but a second
`--stage all` was not run.

## 6. Receipts

```bash
cd /Users/chris/projects/portal-5-hunt-proof-r3-botsv2
eval "$(python3 coding_task/scratch/huntenv.py)"   # the six named keys only
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables
out=/Volumes/data01/portal5_hunt/hunt_proof_r3_botsv2/botsv2
mkdir -p "$out"

uv run python -m $hunt --index botsv2 --out "$out" --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell 2>&1 | tee "$out/run_all.log"
# EXIT=1, 18:58.25 total

uv run python -m $hunt.scoreboard --out "$out" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl" --weights --json \
  | tee "$out/score_all.txt"
uv run python -m $hunt.scoreboard --out "$out" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl" --weights \
  | tee "$out/score_human.txt"
uv run python -m $hunt.scoreboard --out "$out" \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl" \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/botsv2
```

Artefacts: `/Volumes/data01/portal5_hunt/hunt_proof_r3_botsv2/botsv2/{run_all.log,score_all.txt,score_human.txt,progress.json,ledger.jsonl,sources.json,inventory.json,notables.jsonl,behaviours.duckdb,entities.duckdb}`.
Raw run output stays on the data volume; `coding_task/scratch/` holds only `huntenv.py` (no symlinks).

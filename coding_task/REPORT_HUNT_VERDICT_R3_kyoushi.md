# REPORT — Hunt Round-3 live proof & verdict for **kyoushi** (`hb_kyoushi_s1_v2`)

**kyoushi: falls short**

Lane `lane/hunt-proof-r3-kyoushi`, worktree `/Users/chris/projects/portal-5-hunt-proof-r3-kyoushi`,
base `a62f9bc45` (all eight E slices E0–E7 merged: `git log --oneline -8` = E4 merge, E0/E1/E2/E3/E5/E6/E7
merges). One fresh full hunt (`--stage all`) against the live `hb_kyoushi_s1_v2` index, judged through
the live Pipeline, scored with the current scoreboard against the stored neon control.

Rules observed: no code and no Splunk configuration changed; `launch.sh` never run; `.env` never
sourced (only the six named keys read by name, `host.docker.internal` → `localhost`); held-out sets
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) never opened, queried or read. Run artefacts:
`/Volumes/data01/portal5_hunt/hunt_proof_r3_kyoushi/v3/kyoushi` (log `.../v3/kyoushi.run.log`,
scoreboard `.../v3/scoreboard_kyoushi.{txt,json}`, baseline re-score `.../v3/scoreboard_baseline_rescore.txt`).

## 1. Run receipt (EXIT 0 — no traceback, all five stages written)

| stage | wall | searches | receipt |
|---|---:|---:|---|
| cards | 51.3 s | 76 | 18 cards, all `understood`, 8 model requests, 24,850 rows, ledger estate map 6,848 rows |
| behaviours | 198.0 s (437.6 s total incl. inventory/spine) | 911 | `events_read 234,664`; `files_indexed 79`, `files_omitted 63`; read modes `{anchored 11, sampled 1, whole 3}`; misfit 154,661 lines / 2,239 shapes; spine 5,805 entities / 35,537 episodes / 41,989 links, `without_entity 4,064` |
| notables | 213.2 s | 337 | 755 merged + 57 `set_novelty` = 812 candidates; `similar_to_known` kept 300, reliability AUC 0.9042, `excluded: kyoushi (index unseen by the store)`; `weights_source: override` |
| relate | 11.4 s | 53 | 381 cases, 12 promoted, 64 flows, `coverage_complete True` |
| judge | 537.8 s | 0 | 282 judged / 530 unjudged (`model_budget_exhausted`), 2.5448 s/call, served `gemma-4-26b-a4b-it-QAT-4bit` |
| **total** | **1,239.8 s** | **1,377 issued** (ledger 1,620 rows) | rows 582,258; read_fraction 0.240; peak 3,806.5 MB; the 1,239.8 s is the scoreboard `cost` total (cards+behaviours+notables+judge), relate's 11.4 s is not in it |

`PORTAL_HUNT_MERGE_WEIGHTS` was exported as the neon 3-family vector
`{alerts:1, deviation:2, misfit:1, peer_rare:1, relate:1, similar_to_known:5}` and arrived intact:
`progress.json:stages.notables.merge = {method: weighted, weights_source: override, weights: {alerts 1,
deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}, defaulted: None}`.

Three lanes (this one, santos, botsv2) shared the lab Splunk and the Pipeline between 15:53 and 16:21,
so stage wall times and the judge's calls/second are contended (R2 judged 438 rows from the same
estate; this run judged 282 of 812).

## 2. Per-slice acceptance (E0–E7, `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6)

| slice | required line | measured | verdict |
|---|---|---|---|
| **E0** receipt honesty | 0 file rows with `rows == 0` and empty `reason`; `coverage: accelerated` carries non-null `accel_window` | 537 file rows, **0** silent; reasons `{<none> 282, host_mismatch 243, empty_window 12}`; ledger 1,620 rows, 0 with `request_budget_exhausted` (none were refused — `searches.total 911`); receipt coverages `{accelerated, accelerated_partial, scan, whole}`, **0** accelerated/partial receipts with null `accel_window` | **PASS** |
| **E1** estate map carries time | graded file `first`/`last` in `sources.json` and equal to live `tstats` within 1 s | `cards[access_combined].facts.files[intranet…access.log.4] = first 1616487926.0, last 1616533993.0`; 85/85 files carry both; live `\| tstats min(_time) max(_time) … source="…access.log.4"` returns **1616487926 / 1616533993** (exact), source range `1616453872..1616869019` (different → not the sourcetype's own range) | **PASS** |
| **E2** file-driven placement | (a) graded file rows ≥ `per_window`, every `FileRead.host ∈ ("", *hosts)`, tail read; (b) duckdb `access_combined`/`intranet_server` ≥ 1,700; (c) `C0 ceiling` reachable ≥ 11/12 with `attacker_http, dirb, webshell_cmd, webshell_upload` reachable | (a) 7 receipts: 3 reads on the file's own range (`…926–…281` 1,059 rows; `…281–…637` 897; `…637–…993` **2,500 = the newest 2,500 lines, tail slice**) + 4 declared `host_mismatch`; sum **4,456 ≥ 2,500**, 0 off-file hosts. (b) **8,867 ≥ 1,700**. (c) **reachable 7/12** (baseline 11/12); step diff `reachable lost attacker_http, dirb, webshell_cmd, webshell_upload`; all four cause **`instrument`** | **FAIL** — (a) and (b) hold, (c) is the round's core line and it did not move |
| **E3** per-source localisation | `localisation.indexes` > 1 entry per source, `accelerated > 0`, read coverage `accelerated` on ≥ 1 read | **9 entries**, mechanisms `{accelerated 6, accelerated_partial 2, indexed 1}`; partials carry `covered_window`+`scanned_window` (`suricata`, `syslog`); no entry's `accel_window` equals the index union `[1616425561, 1616890440]`; the `access_combined` read receipt is `coverage: accelerated`, `accel_window [1616425563.0, 1616890425.000001]` | **PASS** |
| **E4** budget scope | `clock.remaining_s ≥ 715`, `searches.total ≤ 2000` | `clock {job_seconds 720.0, remaining_s 720.0, requests_spent 76}`; `searches.total 911` (cards 76 + behaviours 911 + notables 337 + relate 53 = 1,377 issued, ceiling 2,000); `exhausted_reason None`; ledger holds **243** `host_mismatch` declarations that are not requests (1,154 behaviours ledger rows − 911 issued) | **PASS** |
| **E5** notables contract | `skipped_sources == {}` on the tuned families | `progress.json:stages.notables.skipped_sources = {}`; `inventory.candidates 19`; run log shows the alert-kind source skipped by the inventory (`skipped …suricata:fast: kind:alert behaviours=0`), not fatal; 755 merged and `notables.jsonl` written | **PASS** |
| **E6** estate-map reader | `evidence_absent` computed (no `n/a`, `[]` for kyoushi) | scoreboard JSON `ceiling.evidence_absent = []`, `ceiling.index_map = "ledger estate map, 80 source paths"` (the run's 80 declared sources are all in the map, so the guard is a completeness test, not a loosened one); the render prints no `C0 evidence absent` line for `[]` (existing contract). Counter-check: the same command over the stored neon run (no ledger) still prints `C0 evidence absent  n/a (the run wrote no ledger)` | **PASS** |
| **E7** judge measurement | `auc_pooled`, `auc_by_generator`, `similar_to_known` yes-rate reported separately | `judge auc_pooled 0.343 over deviation,misfit,peer_rare,alerts,set_novelty`; per generator `alerts n/a (27 judged, 0 bad, yes 0.815)`, `deviation 0.389 (63/9/54)`, `misfit 0.333 (7/1/6)`, `peer_rare n/a (31/0/31)`, `similar_to_known 0.457 (154/15/139)`; `judge similar_to_known yes-rate 0.3182 (judged 154, excluded from auc_pooled)`; legacy `AUC all 0.403` still printed | **PASS** |

**Seven of eight slices meet their receipt line. E2 does not**, and E2 carries the round's core
measurement, so the plan's outcome (reachability recovered) fails.

## 3. Scoreboard vs the neon baseline

Baseline re-scored under the **current** scoreboard (unchanged stored run, log
`scoreboard_baseline_rescore.txt`):

| metric | this run (`hb_kyoushi_s1_v2`) | baseline (`hb_kyoushi_s1`, neon) |
|---|---:|---:|
| steps | 12 | 12 |
| **reachable** | **7/12** | **11/12** |
| recall of reachable @50 / @100 / all | 6/7 · 7/7 · 7/7 | 11/11 · 11/11 · 11/11 |
| raw line recall @50 / @100 / all | 10/12 · 11/12 · 11/12 | 11/12 · 11/12 · 11/12 |
| labelled lines read verbatim | **287 / 408,038** | **1,964 / 408,038** |
| causes | censored 1, covered 6, instrument 4, not_surfaced 1 | covered 11, unreached 1 |
| index map / evidence_absent | ledger map, 80 paths / `[]` | `n/a (the run wrote no ledger)` / `null` |
| cases (members @50, scenario) | **9/12, scenario covered yes** | — (stored run has no relate stage) |
| promotion | lifted 12, `judged_only no`, `unjudged_lifted 0` | — |
| judge | 282 judged, AUC all 0.403, pooled 0.343, similar yes 0.318 | no judge result in the stored run |

Step diff `C0 step diff vs …/neon/kyoushi`: `covered@50 lost attacker_vpn, gained -`;
`reachable lost attacker_http, dirb, webshell_cmd, webshell_upload, gained -`.
Case coverage is the one place this run is better than R2 (0/12 → 9/12, `scenario covered yes`);
reachability and labelled-line read count are unchanged from R2 (7/12, 287).

## 4. The layer that fails: the card's sample, not the read

E2's read side now does exactly what the slice specifies, and the failure is downstream of it. Three
independent receipts:

1. **The read reaches the attack.** The graded file's third window is its own tail slice
   `[1616518637, 1616533993]` and its queued query is
   `search index="hb_kyoushi_s1_v2" source="…/intranet.company.cyberrange.at-access.log.4" | sort - _time | head 2500`
   → **2,500 rows**. Those are the file's last 2,500 lines (log lines 405,978–408,477), which are
   precisely the labelled attack flood (keys at 407,904–408,477: `attacker_http`,
   `dirb`, `foothold`, `webshell_cmd`, `webshell_upload`; lines 408,468–408,477 are the webshell
   upload/command lines). The store holds **0** of them: `select count(*) from events where raw = ?`
   is 0 for each of the last 5 log lines, the store has no `wp_meta` row at all, and its intranet
   `access_combined` rows from that file stop at line 1,956 (all before the first labelled line 2,076).
2. **The run's own parser rejects them.** Replaying the run's own card (`sources.json` `template`,
   `structure: template`, 2 templates) through the run's own `parse_row` over the on-disk file:
   the last 2,500 lines parse **0/2,500** (`fmt = text`), the labelled lines 2,076–3,076 **0/1,001**,
   the 10,000 lines at 200,000 **0/10,000**, the last 8,478 lines **0/8,478** — while the pre-attack
   lines 4–1,956 parse 1,431/1,953 (`template`). The source receipt says it: `events_read 166,764`,
   `events_out_of_structure 69,759` (41.8 %), `templates 2/2 explained 0.9833`.
3. **The card's sample never saw the file.** The card's own sample receipt is
   `{"lines": 120, "parsed": 118, "search_sourcetypes": ["access_combined"], "hosts": ["acme_mail", "mail"], "windows": 3}`
   — 3 windows × 40 lines drawn from 2 of the source's 26 files (`SAMPLE_WINDOWS=3`, `SAMPLE_LINES=40`,
   `SAMPLE_SOURCES=2`), none of them the graded intranet file. Its two templates describe the
   acme_mail/mail access shapes; every attack-hour shape is out of structure. The stored neon run's
   store, by contrast, holds **574** of those same lines (407,904–408,477), so the lines are parseable
   by a template learned on the right file — this is a sampling-scope defect, not an unparseable format.

Consequence: `lines_read` stays 287 (the 287 are `openvpn` 264 + `audit` 19 + `auth` 4 — none from the
access log), so the four E2 steps stay `instrument` and reachable stays 7/12. **E2's own deliverable —
row volume and host/tail placement — is proven (4,456 rows, 8,867 stored intranet access rows, 0 off-host
reads); its promised outcome needs a sample/parse fix that no E slice owns.**

Caveat on the ≥1,700 target: it is met, but not by attack evidence — only **1,431** of the 8,867
stored intranet access rows come from the graded file, and all of them are pre-labelled baseline lines
(4–1,956). The 1,700 line therefore passes while the evidence it was meant to represent is absent.

Cost of the change: this run read **24.0 %** of the index (582,258 rows) against R2's 10.7 %, on the
same 408k-line file, and reached the same 287 labelled lines. Behaviours alone issued 911 requests
plus 314 `| tstats count` density probes; the request ceiling (2,000) was not hit, but the read volume
rose ~1.9x with no labelled-line gain.

## 5. What was not run / limits of this report

- **E7's stability check** (§6 E7 live proof: pooled AUC moves ≤ 0.02 when `similar_to_known` is
  excluded from a *fresh* judge run) was not run: it needs a second full judge pass
  (`--generators` without `similar_to_known`, ~9 min of Pipeline). The brief's E7 line only asks for
  the three reported figures, which are above.
- The judge sample is 282 of 812 (530 `model_budget_exhausted`, 2.54 s/call under three concurrent
  lanes); per-generator `auc` is therefore `n/a` for `alerts` and `peer_rare` (0 bad rows judged).
- The parse replay is the run's own card + parser over the on-disk log; it is not a second live hunt.
  It agrees with the store receipts (0 rows, 0 `wp_meta`) and with `events_out_of_structure`.
- `relate.coverage_complete True` in the run's receipt vs `coverage_complete False` in the scoreboard
  is unchanged from R2 (the relation receipt does not count the reader's gap/window censoring).
- The baseline numbers are the stored neon run under today's scoreboard; its `lines_read` differs by
  20 from the 1,944 quoted in `REPORT_HUNT_VERDICT_R2_kyoushi.md` (that figure was not re-measured
  there) — the reachable/covered/cause figures reproduce exactly.

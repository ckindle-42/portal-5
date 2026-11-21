# REPORT — Hunt Round-2 live proof & verdict for **kyoushi** (`hb_kyoushi_s1_v2`)

**kyoushi: falls short**

Lane `lane/hunt-proof-r2-kyoushi`, worktree `/Users/chris/projects/portal-5-hunt-proof-r2-kyoushi`,
base `26aee7eee` (= current `main`: D0–D10 merged + D6 live rebuild). Brief
`coding_task/BRIEF_HUNT_PROOF_R2_kyoushi.md`; acceptance `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5
(D0–D10) and `coding_task/FINDING_HUNT_D*.md`.

One fresh full hunt (`--stage all`) ran against the D6-rebuilt `hb_kyoushi_s1_v2` index, judged
through the live Pipeline, then scored with a step-set diff against a re-scored control. No code
and no Splunk configuration was changed by this lane; `launch.sh` was never run. Held-out sets
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or read. `.env` was
read by key name only (the six named keys; `host.docker.internal` rewritten to `localhost`),
never sourced; no secret appears in this report.

```bash
# the run (judge/embedding env per brief; PORTAL_HUNT_MERGE_WEIGHTS exported first)
export PORTAL_HUNT_MERGE_WEIGHTS=$PWD/coding_task/scratch/hunt_proof_r2_kyoushi/merge_weights_neon_3fam.json
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_kyoushi_s1_v2 --out coding_task/scratch/hunt_proof_r2_kyoushi/v2/kyoushi \
  --stage all --family kyoushi \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families santos,russell          # EXIT=0, 761.8 s wall
# scoreboard (step diff + measured marginal + machine JSON)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/hunt_proof_r2_kyoushi/v2/kyoushi \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --weights --json \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/kyoushi
```

Judge env: `PORTAL_HUNT_JUDGE_URL=http://localhost:9099`, `PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning`
(preflight answered; served `gemma-4-26b-a4b-it-QAT-4bit`), embeddings `google/embeddinggemma-2`,
keys via `PORTAL_HUNT_*_KEY_ENV=PIPELINE_API_KEY`.

**Run artifacts moved after grading** to `/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi`
(POINTER.txt in the scratch dir; the wiki truth-claims test walks the whole tree). Score JSONs,
grade output, D6 verify JSON, weights file and logs stay in `coding_task/scratch/hunt_proof_r2_kyoushi/`.

## 0. Baseline substitution (the brief's named dirs are gone)

The brief's prior-run checkout `/Users/chris/projects/portal-5-hunt-proof-run` does not exist on
this machine (`ls: No such file or directory`; no `hunt_proof_20261120T232700` anywhere under
`/Users/chris` or `/Volumes/data01`), so its `control/kyoushi` and `v2/kyoushi` are not on disk.
Both substitutions below are flagged, not silent:

- **Diff baseline:** `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/kyoushi` —
  the stored run against the original index `hb_kyoushi_s1`. Re-scored under the current
  scoreboard it reproduces the control numbers exactly: index `hb_kyoushi_s1`, steps 12,
  **reachable 11**, **covered@50 11** (same as the 2026-11-21 verdict's control row). The one
  step outside the control's reachable set is `reverse_shell` (1 labelled line, cause `unreached`).
- **D7 weights source:** measured fresh, the same way the lost prior `--weights-out` would have
  been: `scoreboard --weights-out` over the three surviving neon family runs (symlinked dir
  `coding_task/scratch/hunt_proof_r2_kyoushi/neon3/`) →
  `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` →
  `merge_weights_neon_3fam.json`, exported via `PORTAL_HUNT_MERGE_WEIGHTS` before the run. This
  independently reproduces the santos R2 lane's measurement over the same neon runs
  (identical vector, `coding_task/scratch/hunt_proof_r2_santos/merge_weights_neon_3fam.json`).

## 1. Run receipt (run.log / progress.json, EXIT=0)

| stage | wall | searches | notes |
|---|---:|---:|---|
| cards | 30.35 s | 76 | 13 sources → 18 cards, 18 understood, 8 model requests |
| behaviours | 263.16 s (receipt 95.6 s + inventory 121.8 s + spine) | 1,022 | events_read 125,122; `files_indexed 79, files_omitted 0`; read_modes `{anchored 12, whole 3}`; misfit_lines 17,265; spine 9,362 entities / 28,015 episodes / 41,492 links |
| notables | 155.45 s | 337 | 755 merged + 57 set_novelty = 812 judged candidates; **`weights_source: "measured"`**; similar_to_known reliability_auc 0.9042 |
| relate | 9.77 s | — | 2,363 cases, 12 promoted, flows 64, `coverage_complete True` |
| judge | 312.87 s | 0 | 438 judged / 374 unjudged (`model_budget_exhausted`), rate 1.6413 s/call |
| **total** | **761.83 s** | 1,489 | rows 259,746; read_fraction 0.1071; peak 3,332.8 MB |

Scoreboard headline (vs the neon control):

```
C0 ceiling  steps 7/12 reachable  labelled lines read verbatim 287/408038
C0 evidence absent  n/a (the run recorded no complete per-source index map)
C0 recall-of-reachable  line @50 6/7  @100 7/7  all 7/7
C0 modes  line 10/12 @50  11/12 @100  11/12 all
C0 causes  covered 6, instrument 4, not_surfaced 1, unreached 1
C0 step diff vs .../neon/kyoushi
  covered@50  lost attacker_vpn  gained -
  reachable   lost attacker_http, dirb, webshell_cmd, webshell_upload  gained -
raw line recall  top50 10/12  top100 11/12  all 11/12
judge  judged 438  AUC 0.403  yes-rate bad 0.655 good 0.758
```

## 2. Per-slice table (D0–D10)

Grade script: `coding_task/scratch/hunt_proof_r2_kyoushi/grade_kyoushi.py` — **23/30 checks pass**;
full output `grade_out.txt`. PASS/FAIL is against the brief's acceptance list and §5's live proof.

| slice | verdict | exact receipts |
|---|---|---|
| **D0** measurement truth | **FAIL (2 of 6 properties)** | reachable **7**/12 (`reachable ≥ 11` fails; control had 11). Step diff vs neon: `reachable lost attacker_http, dirb, webshell_cmd, webshell_upload; gained -` — **exactly the four steps the brief's per-file read should recover**. covered@50 `lost attacker_vpn; gained -` (`lost == []` fails). **`evidence_absent` prints `n/a (the run recorded no complete per-source index map)`** — the cards-stage ledger row is now `by sourcetype source host` (tuples, 6,848 rows), so the D0 path-set-equals-row-count rule rejects it; kyoushi has no evidence-absent step, so no step is wrongly counted, but the instrument property is not delivered. Diff prints step names, no ratio in the headline (holds). |
| **D1** per-file read | **FAIL on its live proof; the mechanism half is real** | Routing works: 26/26 `access_combined` files receipted (157 `(file,window)` rows, 79 files indexed stage-wide, `files_omitted 0`), and the ledger contains `search index="hb_kyoushi_s1_v2" source="/apache2/intranet.company.cyberrange.at-access.log.4" \| head 1250` per window — the query names the labelled file. But 19/26 files never yielded a row across all their reads; the labelled file's 20 schedule reads returned 0 rows in 16 windows and head-capped slivers in 3 (741+856+1,250), because **99.5 % of the file's 408,477 lines sit in [20:00..22:00) UTC on 23-Mar** (live `tstats by _time` hour histogram: hour 20 → 258,514, hour 21 → 147,888) while the 13 schedule windows divide the file's 5.6-day span evenly (~5.8 h each). Store holds **1,134** intranet_server access events (< 1,700 acceptance); `attacker_http, dirb, webshell_cmd, webshell_upload` stay unreachable. |
| **D2** one field vocabulary | **PASS** | 0 of 1,489 ledger queries match `by (template\|program\|v[1-6])`; inventory statuses `{complete 40, parse_only 60}` — **zero `empty`**; 16,158 values over 40 complete lists. |
| **D3** capped keeps the tail | **PASS (vacuous)** | No list exceeded `LIST_MAX` on this family this run (`capped=0`), so `capped ⇒ values > 0` holds with no exercise; the D3 live proof remains santos-only (dns.rrname / dns_query). |
| **D4** numeric identities | **PASS** | 6 numeric-id `user` entities in `entities.duckdb` (uid/auid ids); spine CLI verify over the run's own store: `steps=12 read=7 pass=7 lines_read=588 lines_with_episode=588 lines_without_entity=0` — every read line carries an entity and an episode; every *read* step passes (the 5 unread steps are D1's failure, not D4's). |
| **D5** rung 1 fires | **PARTIAL FAIL (list-level yes; localisation/read no)** | `inventory.accelerated` = all 6 model roots `['Authentication','Endpoint','Intrusion_Detection','Network_Resolution','Network_Traffic','Web']` ✓, `model_probes 215`, `probe_failures []`, **5 value lists carry `mechanism: accelerated`** ✓. But **0 of 15 read receipts and the localisation receipt have `coverage: "accelerated"`** — localisation is `{mechanism: "indexed", model: "", coverage: "scan"}`, accel_window recorded but rejected. Diagnosed live (read-only re-issue of the run's own probes): the guard needs **one** model's summary window to contain the whole index span `[1616425561..1616890440]`, and no model does — Authentication misses the start by **2 s** (summary first 1616425563) and the end by 15 s (last 1616890425); every other model starts 2–8 h later. `localise` is called once per index with the union range, so on any family whose estate crosses model boundaries rung 1 can structurally never fire — the same fall the santos R2 lane measured (2 s short there, 2 s/15 s here). Endpoint has **no summarized events at all** for this index (`summariesonly count = 0`) yet still lists as a complete root. |
| **D6** setup/rebuild | **PASS (live-verified)** | `verify --index kyoushi`: 22/22 rows ok — `service_log_absent ok rows=0`; `user_clean ok rows=0 (scan 9000)`; `auid_indexed ok rows=6 (scan 25090)`; `entity_indexed:hb_kyoushi_s1_v2 ok rows=14`; `sourcetypes rows=13 scan=2425851` (total < 2.7 M ✓); `summaries_complete 6/6`; `acceleration_window -10y on 6 models`. |
| **D7** measured merge | **PASS** | `progress.json:stages.notables.merge.weights_source = "measured"`, weights `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` = the exported file, `weights_defaulted: null`; the generator table prints `head@50` beside `attribution@50`/`marginal@50`/`measured`/`used`. |
| **D8** verified promotion | **PASS on its property; the recall fall is S3's** | `case promotion judged_only no lifted 12 unjudged_lifted 0` (`relate.case_quality.promoted_unjudged = 0`, all 12 lift ids judged) and `case evidence pieces min 2 violations 0` (members verify). The set-novelty route exists (57 `set_novelty` candidates judged). But `case members top50 0/12` (control 3/12), `scenario covered no` — the R1 S3 failure persists and is the ceiling's binding constraint at @50. |
| **D9** flows | **PASS** | `flows 64 > 0`; `flows_skipped 7487` accounted `{capped 3446, duplicate 1157, single_source 2844, not_entity 15, order 25}` — duplicate-ingest pairs are skipped as duplicates, never flows. |
| **D10** S0 cause, delivered | **PASS** | `C0 causes covered 6, instrument 4, not_surfaced 1, unreached 1` with per-step names (`instrument: attacker_http, dirb, webshell_upload, webshell_cmd; not_surfaced: attacker_vpn; unreached: reverse_shell`); no step has an empty cause. `progress.json:honesty` non-null from the first write: `{knowledge loaded, families [russell, santos], excluded kyoushi, items 1604, embedding google/embeddinggemma-2, reliability_auc 0.9042, weights_source measured, …}`. |

## 3. The failing layer, named

The read→store path loses the attack hour, in two stacked steps — the same layer the 2026-11-21
verdict named (S2 at its input), still failing with D0–D10 merged:

1. **Window allocation (D1's read side).** The labelled file `intranet.company.cyberrange.at-access.log.4`
   holds 408,477 lines, 99.5 % of them in two hours on 23-Mar (the attack). The 13 even schedule
   windows put 16 of 20 reads where the file is empty (0 rows), and the one overlapping window
   returns a `head`-capped 1,250 of ~406k available rows. The localiser's anchored read did reach
   the attack window `[1616530752..1616533980)` and returned 1,403 rows — and the webshell
   labelled lines are the **last 10 lines of the file** (21:12:56–21:13:13 UTC, lines 408,468–408,477),
   past every read's cap. Net: 287/408,038 labelled lines read verbatim, store 1,134 < 1,700.
2. **Parse coverage (S2).** The 2,653 attack-hour rows that *were* read (1,250 schedule + 1,403
   anchored) produced **0 store events**: the store holds no intranet_server event after 03-23T15:00
   UTC, while 2,404 of 10,484 read `access_combined` lines landed in `misfits` (488 shapes kept).
   The card's 2 mined templates (`templates=2/2 explained=0.9833`, mined from a 120-line sample of
   early-hour lines) do not cover the attack-hour shapes (dirb probe URLs, `POST
   /wp-admin/admin-ajax.php`, long `special-*.php?wp_meta=<base64>` shell URLs).

Consequences measured: reachable 7/12 with the four access_combined steps `instrument` (the raw
line scan credits `deviation@45` for `attacker_http`/`dirb`/`webshell_cmd`/`webshell_upload` — the
ranking can surface them; the run just never kept their lines as events); `attacker_vpn` lost at
@50 only (covered at @100 by `misfit@76` — a head-composition effect, the notable is present);
judge AUC 0.403 (below chance ordering, as in R1's 0.413); case members @50 0/12.

For scale against R1 (stored `_v2` run, graded 2026-11-21): reachable was 7/12 there too, 0 events
reached the store from the attack window, `reachable 7/12`, AUC 0.413, case members 0/12 — the R2
run reproduces those ceilings while D2/D4/D6/D7/D8/D9/D10's slice mechanisms are now live-proven.
The delta this round is inside the read and parse stages, not in scoring.

## 4. Shortfalls

- **D0** — reachable 7/12 (< 11); reachable ⊉ control (4 steps lost); covered@50 ⊉ control
  (`attacker_vpn`); `evidence_absent` instrument not delivered (no complete per-source index map).
- **D1** — the live proof fails: 19/26 files never yielded a row, store 1,134 < 1,700, the four
  steps are not recovered by the per-file read.
- **D5** — no localisation/read receipt with `mechanism: accelerated`; the single-model
  exact-containment guard cannot pass a whole-index span (2 s short at start, 15 s at end).
- **D3** — vacuous pass only (no capped list exercised on this family).

## 5. What checks this (orchestrator re-runs)

```bash
cd /Users/chris/projects/portal-5-hunt-proof-r2-kyoushi
# 1. the scoreboard, any time (run dir is on /Volumes; JSON copy in scratch)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --weights --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/kyoushi
#    shows: reachable 7/12, the four-step reachable loss, covered@50 lost attacker_vpn.
uv run python coding_task/scratch/hunt_proof_r2_kyoushi/grade_kyoushi.py   # 23/30 checks pass (RUN points at the /Volumes dir)
# 3. D6, read-only:   uv run python -m scripts.lab.splunk_setup verify --index kyoushi   # 22/22 ok
```

If the scoreboard's reachable line prints `7/12` with the four named losses, the shortfall stands;
a `reachable ≥ 11` with `lost == []` would mean the read/parse stages changed since this run.

## 6. What I did not do / what is unproven

- The R1 comparison rows are quoted from `coding_task/REPORT_HUNT_VERDICT_kyoushi.md`, not
  re-measured (its stored run dirs no longer exist on disk to re-score).
- The `evidence_absent` exclusion property is exercised only in its null case on kyoushi (no
  evidence-absent step); the santos lane's D0 proof carries the positive case.
- The webshell lines' post-read fate ("would have misfit") is reasoned from the 488 kept shapes and
  the 0-store-events measurement, not proven by re-parsing those exact lines through the card.

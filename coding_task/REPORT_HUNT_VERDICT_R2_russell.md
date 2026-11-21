# REPORT — Hunt Round-2 live proof & verdict for **russell** (`hb_ait_russellmitchell_v2`)

**russell: falls short.**

Lane `lane/hunt-proof-r2-russell`, worktree `/Users/chris/projects/portal-5-hunt-proof-r2-russell`,
base `26aee7eee` (= current `main`: D0–D10 merged + D6 live rebuild; the only commits ahead of it
on `origin/main` at dispatch were the sibling R2 verdict docs — verified `git diff --stat
26aee7eee origin/main` touches `coding_task/REPORT_HUNT_VERDICT_R2_santos.md` only). Brief
`coding_task/BRIEF_HUNT_PROOF_R2_russell.md`; acceptance `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5
(D0–D10) and `coding_task/FINDING_HUNT_D*.md`.

One fresh full hunt (`--stage all`) ran against the D6-rebuilt `hb_ait_russellmitchell_v2` index
(EXIT=0, 1,151.4 s), judged through the live Pipeline, then scored with a step-set diff against a
re-scored control. No code and no Splunk configuration was changed by this lane; `launch.sh` was
never run. Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened,
queried or read. `.env` was read by key name only (the six named keys; no
`host.docker.internal` present in them), never sourced; no secret appears in this report.

```bash
# the run (judge/embedding env per brief; PORTAL_HUNT_MERGE_WEIGHTS exported first)
export PORTAL_HUNT_MERGE_WEIGHTS=$PWD/coding_task/scratch/hunt_proof_r2_russell/merge_weights_neon_3fam.json
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_russellmitchell_v2 --out coding_task/scratch/hunt_proof_r2_russell/v2/russell \
  --stage all --family russell \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos          # EXIT=0, 1151.4 s wall
# scoreboard (step diff + measured marginal + machine JSON)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/hunt_proof_r2_russell/v2/russell \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights --json \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/russell
```

Judge env: `PORTAL_HUNT_JUDGE_URL=http://localhost:9099`, `PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning`
(preflight answered; served `gemma-4-26b-a4b-it-QAT-4bit`), embeddings `google/embeddinggemma-2`,
keys via `PORTAL_HUNT_*_KEY_ENV=PIPELINE_API_KEY`.

**Run artifacts moved after grading** to
`/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell` (POINTER.txt in the scratch dir;
the wiki truth-claims test walks the whole tree). Score JSONs, grade output, D6 verify JSON,
measured weights, diagnostics and logs stay in `coding_task/scratch/hunt_proof_r2_russell/`.

## 0. Baseline substitution (the brief's named dirs are gone)

The brief's prior-run checkout `/Users/chris/projects/portal-5-hunt-proof-run` does not exist on
this machine (`ls: No such file or directory`; no `hunt_proof_20261120T232700` anywhere under
`/Users/chris` or `/Volumes/data01`), so its `control/russell` and `v2/russell` are not on disk.
Both substitutions below are flagged, not silent:

- **Diff baseline:** `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/russell` —
  the stored run against the original index `hb_ait_russellmitchell` that the 2026-11-21 proof
  report used for its §2 baseline row. Re-scored under the current scoreboard it reproduces the
  control numbers exactly: index `hb_ait_russellmitchell`, **reachable 15/22**, **covered@50 14**
  (read-relative), raw @50 **15/22** — the same three numbers as the 2026-11-21 verdict's control
  row (`15/22 reachable`, `14/15` ROR @50).
- **D7 weights source:** measured fresh, the same way the lost prior `--weights-out` would have
  been: `scoreboard --weights-out` over the three surviving neon family runs (symlinked dir
  `coding_task/scratch/hunt_proof_r2_russell/neon3/`, removed after the measurement) →
  `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` →
  `merge_weights_neon_3fam.json`, exported via `PORTAL_HUNT_MERGE_WEIGHTS` before the run. This
  independently reproduces both sibling lanes' measurements over the same neon runs (identical
  vector, `coding_task/scratch/hunt_proof_r2_{santos,kyoushi}/merge_weights_neon_3fam.json`).
  It is a real measured marginal from real stored runs of these corpora, **not** the lost
  prior-`v2` vector.

## 1. Run receipt (progress.json / run.log, EXIT=0)

| stage | wall | searches / model reqs | notes |
|---|---:|---|---|
| cards | 38.2 s | 83 / 7 | 7 model requests |
| behaviours | 315.1 s (receipt 134.7 s + inventory 132.6 s + spine) | 1,274 / 0 | events_read 113,121; `files_indexed 90, files_omitted 0`; read_modes `{anchored 12, whole 3}`; misfit_lines 22,650; spine 10,085 entities / 25,758 episodes / 36,232 links |
| notables | 272.3 s | 337 / 0 | 753 merged; **`weights_source: "measured"`**; similar_to_known reliability_auc 0.4178 |
| relate | 9.0 s | 40 | 1,879 cases, 12 promoted, flows 64, `coverage_complete True` |
| judge | 525.8 s | 576 reqs | 576 judged / 189 unjudged (`model_budget_exhausted`), rate ≈ 1.25 s/call (probe 8) |
| **total** | **1,151.4 s** | 1,734 / 583 | rows 334,623; read_fraction 0.1479; peak 3,073 MB |

## 2. Per-slice table (D0–D10)

Grade script: `coding_task/scratch/hunt_proof_r2_russell/grade_russell.py` — **30/39 checks pass**;
full output `grade_out.txt` (it reads the moved run dir on /Volumes, so it re-runs as-is).
PASS/FAIL is against the brief's acceptance list (brief line 23) and §5's live proof.

| slice | verdict | exact receipts |
|---|---|---|
| **D0** measurement truth | **FAIL (4 of 6 properties)** | reachable **11/22** (`reachable ≥ 15` fails; control had 15). Step diff vs neon: `reachable lost attacker_http, dirb, webshell_cmd, webshell_upload, wpscan; gained exfiltration-service` — the five lost steps are exactly the web steps the per-file read should recover. covered@50 `lost attacker, dnsteal, dnsteal-received, service_scan, webshell_cmd, webshell_upload; gained -` (`lost == []` fails). **`evidence_absent` prints `n/a (the run recorded no complete per-source index map)`** — `crack_passwords 49/49` never prints and the denominator stays 22 instead of 21 (the same D0×D1 interaction as both sibling lanes; §3.2). Diff prints step names, no ratio in the headline (holds). |
| **D1** per-file read | **FAIL on its live proof; the mechanism half is real** | Routing works: 21/21 `access_combined` files receipted (917 `(file,host,window)` rows; `files_indexed 90, files_omitted 0`), and the ledger contains `search index="hb_ait_russellmitchell_v2" source="/apache2/intranet.smith.russellmitchell.com-access.log.2" \| head 411` — the query names the labelled file. But the graded file (8,530 events, 100 % host `intranet_server`, 7,698 of them in the single hour 2022-01-24 01:00–02:00 UTC — live `tstats by _time span=1h`, `diag_d1_d5.json`) yielded **452 rows of 8,530** (5.3 %): 6 of 7 schedule windows returned 0 rows (the windows divide the file's ~5-day span evenly, hours where the file has ≤ 97 events), the overlapping schedule read was `head 411`→288 rows, and the anchored read **did** find the attack hour and host (`host="intranet_server"`, window `[1642993200..1642996800]`) but was capped at **`head 144`** → 144 of 7,698 attack-hour events (1.9 %). Store holds **204** intranet_server access events (< 725 acceptance). `attacker_http, dirb, wpscan` stay `instrument`-credited; `webshell_cmd, webshell_upload` stay `unreached` (0 lines read). |
| **D2** one field vocabulary | **PASS** | 0 of 1,734 ledger queries match `by (template\|program\|v[1-6])`; inventory statuses `{complete 36, capped 4, parse_only 60}` — **zero `empty`**; 28,489 values. `access_combined:c_ip` complete **11** (tstats), `linux_audit:acct` complete **8** (tstats), `suricata:fast:signature` complete **16** (tstats) — all three present-field lists are complete with values > 0 (the exact counts are the deep dive's santos examples; russell's estate is smaller and the property, not the count, is the acceptance). |
| **D3** capped keeps the tail | **PASS** | 4 capped lists, all with values: `dnsmasq:dns_query` **5,000** (share 0.218), `suricata#event_type=dns:dns.rrname` **4,961** (0.219), `suricata#event_type=flow:dest_ip` **5,000** (0.143), `access_combined:cs_uri_stem` **4,500** (0.410). No `capped` with empty values. |
| **D4** numeric identities | **PASS** | Numeric-id `user` entities exist: **5** in `entities.duckdb` (incl. `33`, `4294967295` — the auditd unset sentinel FINDING_HUNT_D4 predicted — and `0)`, its predicted malformed neighbour). Spine CLI verify over the run's own store: `steps=22 read=11 pass=11 lines_read=9017 lines_with_episode=9017 lines_without_entity=0` — every *read* step passes; the 11 unread steps are D1's failure, not D4's. Carriers include the numeric identities: `attacker_change_user` → `user:33`, `escalated_sudo_session` → `user:0)`, `exfiltration-service` → `user:4294967295`. Spine receipt: `without_entity=1924` (new store; FINDING_HUNT_D4's predicted post-change russell number was 1,924 — exact match). |
| **D5** rung 1 fires | **PARTIAL FAIL** | `inventory.accelerated` = all 6 model roots `['Authentication','Endpoint','Intrusion_Detection','Network_Resolution','Network_Traffic','Web']` (≥ 6 ✓), `model_probes 215`, `probe_failures []`, **5 value lists carry `mechanism: accelerated`** and are complete (`linux_secure:dest` 10 values, `linux_secure:src` 11, `linux_secure:signature` 3, `syslog:dest` 4, `syslog:src` 1). But no read fired rung 1: every receipt is `coverage=scan`, and `localisation.indexes[0]` is `{mechanism: "indexed", model: "", coverage: "scan"}` — **`mechanism: accelerated` never appears in a localisation/read receipt**. Diagnosed live: the index span is `[1616425561, 1643094188]`; the summaries cover `[1616425563.0, 1643094167.0]` — **2 s short at the start, 21 s short at the end**, and the exact-containment guard rejects it. Third family, same guard (santos 2 s/1,802 s; kyoushi 2 s/15 s). |
| **D6** setup/rebuild | **PASS (live-verified)** | `verify --index russellmitchell`: **22/22 rows ok** — `service_log_absent ok rows=0`; `user_clean ok rows=0 (scan 6818)`; `auid_indexed ok rows=5 (scan 18740)`; `sourcetypes rows=14 scan=2261780` (total matches the D6 finding's predicted russell `_v2` total **2,261,780** to the event, < 2.7 M ✓); `summaries_complete 6/6`; `acceleration_window -10y on 6 models`. The run's own read confirms the shipper copy is gone: `syslog` read **168** events of 58,908 (the D6 finding predicted russell `syslog` 58,908 exactly), and `.service` names no longer type as users. |
| **D7** measured merge | **PASS** | `progress.json:stages.notables.merge.weights_source = "measured"`, weights `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` = the delivered file exactly; `weights_defaulted: null`. Generator table prints `head@50` beside `attribution@50`/`marginal@50`/`measured`/`used`. **No counterfactual attribution is claimed on this run**: the offline re-merge harness (adapted from the santos lane's `counterfactual_merge.py`) does not reproduce the live merge order on russell's rows — its delivered-vector head (`{similar 21, alerts 5, peer_rare 5, deviation 9, misfit 5, set_novelty 5}`) differs from the run's actual head@50 (`{similar 22, deviation 14, peer_rare 6, alerts 4, misfit 4, set_novelty 12}`) and its re-merged @50 (1 step) contradicts the run's own 9 — the D7 finding's documented order-sensitivity caveat ("re-merging a stored notables.jsonl is not bit-identical"). The santos lane's "delivered vector is best at @50" conclusion does **not** transfer to russell and is not asserted here. |
| **D8** promotion lifts verified members | **PASS** | `case promotion judged_only no lifted 12 unjudged_lifted 0` (`relate.case_quality.promoted_unjudged = 0`); `case evidence pieces min 2 violations 0`; `case members top50 19/22` with `scenario covered yes` — the strongest case result of the three R2 families (santos 7/21, kyoushi 0/12). The gained step verifies end-to-end: `exfiltration-service` is **reachable** (gained vs control), its 2 labelled lines are read and covered (`spine_verify.txt`: `exfiltration-service lines=2 read=2 covered=2 pass=True`), carried by `user:4294967295`/`process:/lib/systemd/systemd`. |
| **D9** flows | **PASS** | `flows 64 > 0` (5 host-proven); `flows_skipped 20843` accounted `{capped 2241, duplicate 2965, single_source 10454, not_entity 5146, order 34, host 3}` — duplicate-ingest pairs are skipped as duplicates, never flows. |
| **D10** S0 cause + honesty | **PASS** | `C0 causes covered 6, instrument 3, not_surfaced 5, unreached 8` with per-step names; no step has an empty cause. `progress.json:honesty` non-null from the first stage write: `{knowledge loaded, families [kyoushi, santos], excluded russell, items 1627, embedding google/embeddinggemma-2, reliability_auc 0.4178, merge_method weighted, weights_source measured, merge_weights …}`. |

## 3. Scoreboard vs baseline (the headline numbers)

```
recall  top50 9/22   top100 18/22   all 19/22   notables that cost {'50': 50, '100': 100, 'None': 765}
C0 ceiling  steps 11/22 reachable  labelled lines read verbatim 3010/61862
C0 evidence absent  n/a (the run recorded no complete per-source index map)
C0 recall-of-reachable  line @50 6/11  @100 9/11  all 9/11
C0 modes  line 9/22 @50  18/22 @100  19/22 all   strict n/a for per-line keys
C0 causes  covered 6, instrument 3, not_surfaced 5, unreached 8
C0 causes steps  instrument: dirb, wpscan, attacker_http   not_surfaced: attacker, dnsteal,
  dnsteal-received, exfiltration-service, attacker_vpn   unreached: traceroute, dns_scan,
  network_scan, service_scan, webshell_cmd, dnsteal-dropped, webshell_upload, crack_passwords
C0 step diff vs …/snap_neon_02cc2e3/results/hunt/neon/russell
  covered@50  lost attacker, dnsteal, dnsteal-received, service_scan, webshell_cmd,
              webshell_upload   gained -
  reachable   lost attacker_http, dirb, webshell_cmd, webshell_upload, wpscan  gained exfiltration-service
relate cases 1879  case members top50 19/22  scenario covered yes  unjudged_lifted 0
judge  judged 576 bad 42 good 534 AUC 0.332 (yes-rate bad 0.667 / good 0.665)
cost total=1151.407s  searches=1734  rows=334623  read_fraction=0.147947  peak=3073.2MB
```

Acceptance: `reachable ≥ 15` **fails (11)**; `covered@50 ⊇ control` **fails (6 lost, 0 gained)**;
`lost == []` **fails**; `evidence_absent crack_passwords 49/49` **fails** (n/a; denominator 22 not
21). Read-relative recall of reachable is 6/11 @50 (control 14/15). Against the R1 stored `_v2`
run (`REPORT_HUNT_PROOF_20261121.md` §2: reachable 11/22, ROR 9/11, raw @50 13/22): the ceiling
is unchanged at 11 and ROR fell 9/11 → 6/11 while raw @50 fell 13 → 9 — the head covers fewer
steps than the R1 `_v2` run's head did, on an index that reads 4× more labelled lines (3,010 vs
2,502 read verbatim; the control reads 725).

## 4. Shortfalls, with the failing design layer

No case-level patches below — each is named at the layer whose decision produced it.

1. **D1 — read placement: window and head allocation are still source-driven, not file-driven.**
   The per-file route (D1's mechanism) works: every file is in the route, gets its own ledger rows
   and receipts, none omitted. The failures are the two placement decisions around it:
   (a) the schedule windows are the source's even windows, so 6 of 7 of the graded file's reads
   land in hours where the file has ≤ 97 events (0 rows), and
   (b) the per-file head is the file's share of one source-wide slice (`head 411`, `head 144`), so
   even the correctly placed anchored read — right window `[1642993200..1642996800]`, right host
   `intranet_server` — returns 144 of 7,698 attack-hour events. Result: 452/8,530 rows from the
   file carrying 7,695 labelled lines; store 204 < 725; `attacker_http, dirb, wpscan`
   instrument-credited, `webshell_cmd, webshell_upload` unreached; reachable 11 < 15.
   Layer: `sample.read_files`' per-file budget/window rule (the same layer the santos and kyoushi
   R2 verdicts named, with russell adding the cleanest measurement yet: a *correctly placed*
   anchored read that a `head 144` still starves). This is the round's core fix and it did not
   land end-to-end on the graded file in any of the three families.
2. **D0 ↔ D1 interaction — the estate-map row shape changed under D0's reader.** D1's
   `index_facts` reads `by sourcetype source host` (the run's cards ledger row is 2,487 tuples of
   90 distinct paths); D0's `_index_paths` ragged-row guard (distinct paths == row count) rejects
   it, so `evidence_absent` prints `n/a`, `crack_passwords` stays in the denominator (22, not 21)
   and the `49/49 absent` annotation is lost. Identical on santos and kyoushi — three for three.
   Layer: `scoreboard._index_paths` needs the D1 row shape (paths are derivable from it; the
   guard applies per path set, not per row count).
3. **D5 — rung 1's exact-containment guard cannot pass a rebuilt index as built.** The inventory
   half is live-proven (6/6 model roots, 215 probes, 5 accelerated-mechanism complete lists). The
   firing half fails because `coverage_label` requires one model's summary window to contain the
   whole searched range: the rebuilt index spans `[1616425561, 1643094188]`, the summaries cover
   `[1616425563.0, 1643094167.0]` — 2 s short at the start, 21 s at the end. Layer: either the
   acceleration summaries must be rebuilt to cover the full span (operator/setup), or the guard
   needs the tolerance/per-source-window treatment already attributed in the prior proof report.
   Unchanged by the D6 rebuild; the accelerated aggregate itself answers.
4. **Head composition, not weights, moved coverage.** Raw @50 fell 13 (R1 `_v2`) → 9 and
   read-relative covered 11 → 6. The delivered D7 vector is the measured neon marginal, and the
   scoreboard's own single-family fold table is the expected single-family fallback
   (`C4 marginal … russell 26/6/31/0/0/0` = DEFAULT row — one family cannot produce real LOFO
   folds). Because the offline counterfactual harness diverges from the live merge on this run's
   rows (§2 D7), no attribution between vectors is claimed — the fall is reported as a
   ranker/head-composition outcome on the new estate, measured at head@50 composition
   `{similar 22, deviation 14, peer_rare 6, alerts 4, misfit 4, set_novelty 12}`, not patched.

Not a slice failure but recorded: the judge's `p_yes` separates below chance on this head
(`AUC 0.332`, bad yes-rate 0.667 vs good 0.665; 576 judged, 189 `model_budget_exhausted`). This
run's judge window overlapped the botsv2 R2 lane's live hunt on the same Pipeline (this run's
notables started 12:16; botsv2's `--stage all` launched 12:16:06 while this lane's run was
in flight — PIDs 61578/62491), so judge-rate and AUC numbers carry a contention caveat. The same
below-chance judge appeared on the uncontended kyoushi R2 run (AUC 0.403) and santos R2 (0.151),
so it is a cross-family pattern, not only contention. No D0–D10 acceptance hangs on it.

## 5. What passed that the round set out to prove

D2 (estate vocabulary: 0 parse-local queries, 36 complete lists, 0 false `empty`), D3 (4 capped
lists keeping 4,500–5,000 values with `capped_share`), D4 (numeric identities typed;
verify `read=11 pass=11`, `lines_without_entity 0`; `without_entity=1924` matching the D4
finding's predicted russell number exactly), D6 (rebuilt index verified live: shipper copies out,
`user` clean, `auid` indexed rows=5, 2,261,780 events / 14 sourcetypes — the D6 receipt's russell
total to the event), D7 (`weights_source: "measured"` consumed with the delivered vector,
`weights_defaulted null`), D8 (`promoted_unjudged 0`; members 19/22; `exfiltration-service` gained
as a reachable step and verified end-to-end through the spine), D9 (64 flows, duplicates
excluded, 5 host-proven), D10 (causes for every step + honesty non-null from the first write).
Two slice mechanisms — D8's set-novelty route and D0's honest diff — delivered their first
positive russell results this round (`exfiltration-service` gained; the diff names steps, no
ratio).

## 6. What this run did not do / limits

- The graded family is russell only (this lane's brief); the D1 window/head finding is measured
  on russell's labelled file and matches the sibling lanes' santos/kyoushi measurements, but the
  fix is one round-level change, not three.
- The baseline is a substitute (neon) because the brief's prior-run checkout was deleted; its
  `v2/russell` weights vector could not be recovered, so D7's delivered vector is the
  neon-measured marginal. The D7 acceptance (`weights_source != "default"`) is unaffected; the
  vector's provenance is flagged in §0.
- The offline counterfactual weights harness diverges from the live merge on this run (§2 D7) —
  reported, not fixed (no code changes on this lane).
- The judge budget left 189 of 765 notables unjudged and the judge window overlapped the botsv2
  lane's live run (§4 note); `promoted_unjudged` and case facts are computed on the judged set as
  the scoreboard reports them.
- `linux_audit:exe` (the deep dive's santos example list) was not selected under the declared
  40-list budget — a documented D2 budget decision, not a regression.
- The botsv2 R2 lane's own run/results are that lane's to report; nothing here grades botsv2.

## 7. Artifact locations and reproduce

Run dir: `/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell` (moved after grading;
pointer `coding_task/scratch/hunt_proof_r2_russell/POINTER.txt`). The receipts above were read
from these files before/after the move. Re-run any of:

```bash
cd /Users/chris/projects/portal-5-hunt-proof-r2-russell
# scoreboard, any time (run dir is on /Volumes; JSON copy in scratch)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/russell
# shows: reachable 11/22, the five-step reachable loss with exfiltration-service gained,
#        covered@50 lost 6 / gained 0.
uv run python coding_task/scratch/hunt_proof_r2_russell/grade_russell.py   # 30/39 checks pass
uv run python -m portal.modules.security.core.hunt.notables.spine \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell --family russell \
  --keys /Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl
# shows: steps=22 read=11 pass=11 lines_without_entity=0
# D6, read-only:  uv run python -m scripts.lab.splunk_setup verify --index russellmitchell  # 22/22 ok
```

If the scoreboard's reachable line prints `11/22` with the five named web losses and the
six-step covered@50 loss, the shortfall stands; a `reachable ≥ 15` with `lost == []` would mean
the read stage changed since this run.

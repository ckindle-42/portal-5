# REPORT — Hunt Round-2 live proof & verdict for **santos** (`hb_ait_santos_v2`)

**santos: falls short**

Lane `lane/hunt-proof-r2-santos`, worktree `/Users/chris/projects/portal-5-hunt-proof-r2-santos`,
base `26aee7eee` (= current `main`: D0–D10 merged + D6 live rebuild). Brief
`coding_task/BRIEF_HUNT_PROOF_R2_santos.md`; acceptance
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 (D0–D10) and `coding_task/FINDING_HUNT_D*.md`.

One fresh full hunt (`--stage all`) ran against the D6-rebuilt `hb_ait_santos_v2` index, judged
through the live Pipeline, then scored with a step-set diff against a baseline. No code and no
Splunk configuration was changed by this lane. Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`,
`botsv1`) were never opened, queried or read. `.env` was read by key name only, never sourced (six
named keys; no `host.docker.internal` present); no secret appears in this report.

```bash
# the run (env: judge/embedding vars per brief; PORTAL_HUNT_MERGE_WEIGHTS exported first)
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out coding_task/scratch/hunt_proof_r2_santos/v2/santos \
  --stage all --family santos \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,russell
# scoreboard (step diff + measured weights + machine JSON)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/hunt_proof_r2_santos/v2/santos \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --weights --json \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos
```

Judge env: `PORTAL_HUNT_JUDGE_URL=http://localhost:9099`, `PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning`
(preflight answered; served `gemma-4-26b-a4b-it-QAT-4bit`), embeddings
`google/embeddinggemma-2` (probe answered), keys via `PORTAL_HUNT_*_KEY_ENV=PIPELINE_API_KEY`.

## 1. Baseline substitution (the brief's named dirs are gone)

The brief's prior-run checkout `/Users/chris/projects/portal-5-hunt-proof-run` no longer exists
(`git worktree list` has no such entry; `find` over `/Users/chris` and `/Volumes/data01` finds no
`hunt_proof_20261120T232700` directory), so its `control/santos` and `v2/santos` runs are not on
disk. Both substitutions below are flagged rather than silent:

- **Diff baseline:** `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos` —
  the stored run against the original index `hb_ait_santos` that the 2026-11-21 proof report used
  for its §2 baseline reproduction. Re-scored under the current scoreboard it reproduces the
  control numbers exactly: `C0 ceiling steps 12/21 reachable`, read-relative covered@50 **11**,
  `C0 recall-of-reachable line @50 11/12`, raw @50 covered **18**. A second control-generation run
  (`snap_ru2_c7b28e7/results/hunt/ru2/santos`, also `hb_ait_santos`) scores 13/21 reachable /
  covered 11 — close, but neon is the documented match, so neon is the baseline.
- **D7 weights source:** the same substitution. `scoreboard --weights --weights-out` over the
  surviving stored runs (neon, three families via a symlinked dir
  `coding_task/scratch/hunt_proof_r2_santos/neon3/`) measured
  `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` →
  `merge_weights_neon_3fam.json`, exported via `PORTAL_HUNT_MERGE_WEIGHTS` before the run. This is
  a real measured marginal from real stored runs of these corpora, **not** the lost prior-`v2`
  vector (`{deviation 6, misfit 1, similar_to_known 2, alerts 1, peer_rare 1, relate 1}`).

## 2. Run receipt (progress.json / run.log, EXIT=0)

| stage | wall | searches | notes |
|---|---:|---:|---|
| cards | 28.44 s | 83 | 6 model requests |
| behaviours | 110.3 s receipt / 293.6 s with inventory+spine | 1,231 | events_read 129,768; `files_indexed` 87, `files_omitted` 0; read_modes `{anchored 11, whole 3}`; misfit_lines 16,627 |
| notables | 103.3 s | 337 | 779 merged; `weights_source: "measured"` |
| relate | 9.3 s | 40 | 2,580 cases, 12 promoted, `coverage_complete True` |
| judge | 482.1 s | 0 | 531 judged / 260 unjudged (`model_budget_exhausted`), rate 1.3535 s/call |
| **total** | **907.5 s** | 1,691 | read_fraction 0.1212; peak 3,659 MB |

## 3. Per-slice table (D0–D10)

Receipts are quoted from `progress.json`, the scoreboard output, and read-only probes. PASS/FAIL
is against the brief's acceptance list (brief line 23) and the slice's live proof in §5 of the
deep dive.

| slice | verdict | exact receipts |
|---|---|---|
| **D0** measurement truth | **FAIL (3 of 4 properties)** | reachable **11**/21 (`reachable ≥ 12` fails; control had 12). Step diff vs neon: `reachable lost attacker_http, dirb, wpscan; gained attacker_change_user, exfiltration-service`. covered@50 `lost: attacker, dns_scan, dnsteal, dnsteal-received, network_scan, service_scan, traceroute, webshell_cmd, webshell_upload; gained: -` (`lost == []` fails). **`evidence_absent` = `n/a (the run recorded no complete per-source index map)` — `crack_passwords 44/44` never prints and the denominator stays 21 instead of 20.** Diff prints step names, no ratio in the headline (property holds). |
| **D1** per-file read | **FAIL on its live proof; the mechanism half is real** | Per-file routing works: 21/21 `access_combined` files receipted, 179 `(file,window)` ledger rows, `files_indexed 21 / files_routed 21 / files_omitted 0` per source, 87 files indexed stage-wide, none omitted. The ledger contains `search index="hb_ait_santos_v2" source="/apache2/intranet.smith.santos.com-access.log" | head 360` — **the query names the labelled file** (RC1's route defect is gone). But every read of it returned **0 rows**: its 4 share-windows are 2022-01-13/14/15 + 01-17 ~02:27–07:05 UTC while the file's events live at 10:00–19:00 on 01-17 (peak hour 11:00–12:00 = 7,894 of 9,462 events, `tstats by _time span=1h`); its 4 anchored reads carry `host="inet-firewall"` while all 9,462 events of the file are on `intranet_server` (`tstats … by host`). Store holds **184** intranet_server access events (rotated files only) vs the ≥ 1,000 acceptance; `attacker_http, dirb, wpscan` stay unreachable. |
| **D2** one field vocabulary | **PASS** | 0 of 1,691 ledger queries match `by (template|program|v[1-6])`; inventory statuses `{complete 36, capped 4, parse_only 60}` — **zero `empty`**. `access_combined:c_ip` complete **18** (tstats, 0.46 s); `linux_audit:acct` complete **13** (0.45 s); `suricata:fast:signature` complete **22** (0.45 s). `linux_audit:exe` was **not selected** (7th name of its source; `INVENTORY_MAX_FIELD_SEARCHES 40` documented in FINDING_HUNT_D2 as left at 40 rather than tuned to reproduce the example) — the deep dive's fourth example number is not met; the D2 property (no parse-local query, `empty` only for present-and-zero) holds. |
| **D3** capped keeps the tail | **PASS** | 4 capped lists, all with values: `dnsmasq:dns_query` capped **5,000** values (capped_share 0.2496), `suricata#event_type=dns:dns.rrname` capped **5,000** (0.2569), `postfix_syslog:mpid` 4,500 (0.4946), `access_combined:cs_uri_stem` 4,667 (0.3342). No `capped` with empty values. |
| **D4** numeric identities | **PASS** | `user:1002` exists in `entities.duckdb` (4 events, 1 episode); numeric-id user entities = 4 (`1002`, `1003`, `33`, `4294967295` — the auditd unset sentinel FINDING_HUNT_D4 predicted). Spine CLI verify: `steps=21 read=11 pass=11 lines_read=10043 lines_with_episode=10043 lines_without_entity=0`. Spine receipt: 10,238 entities, 26,555 episodes, 40,530 links (`events_without_entity` 5,538 — a new-store number, not comparable to the pre-D6 store's 3,351). |
| **D5** rung 1 fires | **PARTIAL FAIL** | `inventory.accelerated` = all 6 model roots `['Authentication','Endpoint','Intrusion_Detection','Network_Resolution','Network_Traffic','Web']` (≥ 6 ✓), `model_probes 215`, `probe_failures []`, 5 value lists with `mechanism: accelerated`. But no read fired rung 1: every anchored receipt is `rung=narrowed_scan, coverage=scan`, and `localisation.indexes[0]` is `{mechanism: "indexed", model: "", coverage: "scan"}` — **`mechanism: accelerated` never appears**. Diagnosed live (read-only, `diag_rung1.py`): the index data range is [1616425561, 1642487481]; no model's summary window contains it — Authentication misses by **2 s at the start and 1,802 s at the end**, the other five models only summarise the last ~4.6 days (first summarised event 1642084517+); Endpoint's probe returns no window at all. The exact-containment guard (`sample.coverage_label`) therefore falls to rung 2 on every read. The accelerated aggregate itself works (`tstats summariesonly=true … by host _time span=3600s` answers, e.g. host `aecid-samba-4` bucket at 1616425200) — the summaries cover the range, the guard rejects it. |
| **D6** setup/rebuild | **PASS (live-verified)** | `verify --index santos`: `service_log_absent ok rows=0`; `user_clean ok rows=0 (scan 6744)`; `auid_indexed ok rows=5 (scan 24042)`; `sourcetypes rows=14 scan=2573164` (total < 2.7 M ✓); `summaries_complete 6/6`. The run's own read confirms the duplicate is gone: `syslog` read **152** events (pre-D6 run read 11,250 and typed `.service` names as users). |
| **D7** measured merge | **PASS** | `progress.json:stages.notables.merge.weights_source = "measured"`, weights `{alerts 1, deviation 2, misfit 1, peer_rare 1, relate 1, similar_to_known 5}` = the delivered file; `weights_defaulted: null`. Generator table prints `head@50` beside `attribution@50`/`marginal@50`/`measured`/`used`. Counterfactual (same rows, re-merged with the scoreboard's own machinery): delivered vector **8** raw steps @50 vs default `{31/26}` **5** — the delivered vector is the best of the three at @50 on this run's rows, so the coverage fall is not a D7 artifact. |
| **D8** promotion lifts verified members | **PASS** | `case promotion judged_only no lifted 12 unjudged_lifted 0` (`relate.case_quality.promoted_unjudged = 0`; all 12 lift ids carry `unjudged: false`). `case members top50 7/21` (> 3/21), `scenario covered yes`, two-evidence violations 0. `exfiltration-service` is now **reachable** (gained vs control) and its set-novelty candidate exists in the file: a `set_novelty` row with `entities [{role: object, value: ut}]`, 2 event_ids and the `type=SERVICE_START … unit=ut` evidence line — at rank 780, i.e. surfaced but not in the head (`not_surfaced`), not `not_generically_surfaceable`. |
| **D9** flows | **PASS** | `flows 64 > 0`; `flows_skipped 19361` accounted `{capped 2330, duplicate 2899, single_source 9399, not_entity 4667, order 65, host 1}` — duplicate-ingest pairs are skipped as duplicates, never flows. 7 flows are `host_proven`, e.g. value `1.cpm.ak-is2.net`, ingress `dnsmasq` → later `suricata#event_type=dns` on host `inet-firewall`. (The deep dive's example endpoint pair `…→ linux_audit/linux_secure` does not appear among the host_proven flows; the dns→network pair does.) |
| **D10** S0 cause + honesty | **PASS** | `C0 causes covered 6, instrument 3, not_surfaced 5, unreached 7` with per-step names; no step has an empty cause. `progress.json:honesty` non-null from the first stage write: `{knowledge loaded, families [kyoushi, russell], excluded santos, items 1631, embedding google/embeddinggemma-2, reliability_auc 0.4429, merge_method weighted, weights_source measured, merge_weights …}`. |

## 4. Scoreboard vs baseline (the headline numbers)

```
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 3353/47367
C0 evidence absent  n/a (the run recorded no complete per-source index map)
C0 recall-of-reachable  line @50 6/11  @100 6/11  all 11/11
C0 modes  line 9/21 @50  9/21 @100  19/21 all
C0 causes  covered 6, instrument 3, not_surfaced 5, unreached 7
C0 step diff vs …/neon/santos
  covered@50  lost attacker, dns_scan, dnsteal, dnsteal-received, network_scan,
              service_scan, traceroute, webshell_cmd, webshell_upload   gained -
  reachable   lost attacker_http, dirb, wpscan  gained attacker_change_user, exfiltration-service
relate cases 2580  case members top50 7/21  scenario covered yes  unjudged_lifted 0
judge  judged 531 bad 36 good 495 AUC 0.151 (yes-rate bad 0.306 / good 0.818)
cost total=907.46s  searches=1691  rows=311780  read_fraction=0.121166
```

Acceptance: `reachable ≥ 12` **fails (11)**; `covered@50 ⊇ control` **fails (9 lost, 0 gained)**;
`lost == []` **fails**; `evidence_absent crack_passwords 44/44` **fails** (n/a, denominator 21 not
20). Read-relative recall of reachable is 6/11 @50 (control 11/12).

## 5. Shortfalls, with the failing design layer

No case-level patches below — each is named at the layer whose decision produced it.

1. **D1 — read placement, window/host selection is still source-driven, not file-driven.**
   The per-file route (D1's mechanism) works: the labelled file is in the route, gets its own
   ledger rows and receipts. But the windows chosen for it come from the source's activity
   (horde-dominated 01-13/14/15 + early 01-17), where the file has zero events, and the anchored
   reads inherit the source-level host anchor `inet-firewall` while the file's 9,462 events are
   all on `intranet_server`. Result: 0 rows from the file carrying 7,786 labelled lines;
   `attacker_http, dirb, wpscan` unreachable; reachable 11 < 12; store intranet events 184 < 1,000.
   Layer: `sample.read_files` window/host allocation (D1's Build assigned the budget per file but
   the windows/hosts still come from source-level facts). This is the round's core fix and it did
   not land end-to-end on the graded file. (FINDING_HUNT_D1's declared limit — "a multi-host
   file's head is still arrival order across its hosts; anchored reads do carry host=" — is the
   half that bites; the window half is new evidence.)
2. **D0 ↔ D1 interaction — the estate-map row shape changed under D0's reader.** D1's
   `index_facts` now reads `by sourcetype source host`; D0's `_index_paths` still keys on the
   two-field row and its ragged-row guard (distinct paths == row count) correctly refuses the
   three-field row (87 distinct paths ≠ 4,626 rows), so `evidence_absent` prints `n/a`,
   `crack_passwords` stays in the denominator (21, not 20) and the `44/44 absent` annotation is
   lost. Layer: `scoreboard._index_paths` needs the D1 row shape (paths are still derivable from
   it — the guard can be applied per-path-set, not per-row-count).
3. **D5 — rung 1's guard cannot pass on this index as built.** `inventory.accelerated` is fixed
   (6/6 model roots, 215 probes, 0 failures — the D5 inventory change works). The firing half
   fails because `coverage_label` requires the summary window to contain the whole searched range
   exactly; the rebuilt index's summaries miss it by 2 s / 1,802 s (Authentication) or ~4.6 days
   (the other five models). Layer: either the acceleration summaries must be rebuilt to cover the
   full index span (operator/setup), or the guard needs the per-source window treatment the prior
   proof report already attributed ("the guard has no tolerance and no per-source window").
   Unchanged by the D6 rebuild; the aggregate itself answers.
4. **Coverage vs control — the read and rows, not the weights.** Raw @50 recall fell 18 → 9 and
   read-relative covered 11 → 6. The delivered D7 vector is *not* the cause (counterfactual: the
   default vector scores **5** @50 steps on these same rows vs 8 delivered). The fall follows from
   (a) the labelled web file unread (its three steps move from `instrument`-credited to
   `unreached`/absent from the head) and (b) this run's head covering fewer steps overall: the
   D6-rebuilt index feeds different rows (129,768 events read vs 213,233 stored; the shipper
   duplicate is gone), and the steps `attacker, dnsteal, dnsteal-received` were **read** this run
   (not_surfaced) but no @50 notable claims them, where the control's default-weighted head had
   matching rows. This is a ranker/head-composition outcome on the new estate, reported, not
   patched.

Not a slice failure but recorded: the judge's `p_yes` is anti-correlated with label on this run's
head (`AUC 0.151`, bad yes-rate 0.306 vs good 0.818) — the same judge seat separated on the prior
santos runs (0.952). The judged sample is this run's head (531 of 791; 260 `model_budget_exhausted`
within the 720 s budget). No D0–D10 acceptance hangs on it.

## 6. What passed that the round set out to prove

D2 (estate vocabulary: 0 parse-local queries, 36 complete lists, 0 false `empty`), D3 (capped
lists keep 4,500–5,000 values with `capped_share`), D4 (numeric identities typed; verify 11/11,
`lines_without_entity 0`; `attacker_change_user` now read-relative covered), D6 (rebuilt index
verified live: shipper copies out, `user` clean, `auid` indexed, 2.57 M events / 14 sourcetypes),
D7 (`weights_source: "measured"` consumed, and measurably better than defaults at @50 on these
rows), D8 (`promoted_unjudged 0`; `exfiltration-service` gained as a reachable step with a
set-novelty candidate), D9 (64 flows, duplicates excluded, 7 host-proven), D10 (causes + honesty
non-null). Two steps the control could not reach — `attacker_change_user` and
`exfiltration-service` — are reachable for the first time.

## 7. What this run did not do / limits

- kyoushi and russell were not re-run (this lane is santos-only); the D1 window/host finding is
  measured on santos's labelled file and the same mechanism applies to any multi-host,
  activity-skewed file on the other families — unproven there.
- The baseline is a substitute (neon) because the brief's prior-run checkout was deleted; its
  `v2/santos` weights vector could not be recovered, so D7's delivered vector is the neon-measured
  marginal, not the prior-`v2` one. The D7 acceptance (`weights_source != "default"`) is
  unaffected; the vector's provenance is flagged.
- The judge budget left 260 of 791 notables unjudged; `promoted_unjudged` and case facts are
  computed on the judged set as the scoreboard reports them.
- `linux_audit:exe` (the deep dive's fourth example list) was not selected under the declared
  40-list budget — a documented D2 budget decision, not a regression.
- Held-out sets untouched; no `.env` sourcing; no launch.sh; no code or Splunk changes.

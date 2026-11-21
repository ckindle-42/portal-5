# botsv2: falls short

Graded 2026-11-21 on `lane/hunt-proof-r2-botsv2`, HEAD `26aee7eee` (clean), against
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5–§6 (slices D0–D10) and `coding_task/FINDING_HUNT_D*.md`.
Splunk `botsv2` only, read-only; no Splunk configuration change, no code change, no
`launch.sh`, no `.env` sourced (the six keys were exported by name from the live checkout's
`.env`). Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened.

**The four measured acceptance properties of the control now hold** — keys 7/20 (floor 5/20)
with no lost step, `mechanism: indexed` on an estate the CIM allowlist excludes,
`promoted_unjudged 0`, `progress.json:honesty` non-null with `C0 causes` non-empty — **but the
family falls short because the brief's own run cannot produce them**: `--stage all` reads
nothing and crashes, and the stage-split `notables` stage aborts on a new inventory defect, so
the scored run below is a *degraded* configuration (one generator dropped). The wide-estate D1
read also spends the entire request budget.

## 0. What was run

Three runs, one working tree, one lab box:

| run | command | outcome |
|---|---|---|
| **A — the brief's literal command** | `…notables --index botsv2 --out …/botsv2 --stage all --family botsv2 --knowledge-store knowledge_v2_20261116.duckdb --knowledge-families kyoushi,santos,russell` | **exit 1 in 720.98 s.** Cards 573.2 s, then every behaviour read refused (`events_read=0`), `HuntDeadlineExceededError` at relate. Scoreboard 4/20 keys, 0/14. |
| **B — stage split** (same code, one stage per process, cards reused from A, so a fresh 720 s budget per stage) | `--stage behaviours`, `--stage notables …` | behaviours complete (259,769 events); **notables crashes**: `SimilarityError: behaviour sources need an activity card with roles: botsv2:pan:threat (kinds: alert)`. |
| **C — scored run** | B + `--stage notables --generators alerts,peer_rare,deviation,misfit` (no knowledge store) + `--stage relate` + `--stage judge` | completes; notables stage writes **575**, relate adds 3 `relate` + 147 `set_novelty` (725 total), **5,747 cases, 725/725 judged**; scoreboard below. `similar_to_known` is absent from C — the only deviation from the brief, forced by B's crash. |

Timings (wall): cards 573.2 s (113 model requests, 887.1 model-seconds), behaviours 632.2 s
(inventory 265.9 s, 1,813 behaviour reads), notables 32.9 s, relate 93.7 s, judge 464.8 s,
case rerank 199.4 s. Scoreboard total 1,129.8 s.

Environment: Pipeline `:9099` root (the brief's `PORTAL_HUNT_JUDGE_URL=http://localhost:9099`;
the judge client appends `/v1/chat/completions`, and the doubled `/v1/v1/chat/completions`
returns 404 live), `hunt-reasoning` served `gemma-4-26b-a4b-it-QAT-4bit`, embeddings
`google/embeddinggemma-2`; lab Splunk 10.2.5 at `https://10.0.1.30:8089`.

## 1. Acceptance properties (the brief's list)

| property | result | receipt |
|---|---|---|
| **No regression**: `keys_reachable ≥ 5/20`, and scoreboard numbers vs the prior verdict | **pass** | `C0 ceiling keys 7/20 reachable steps 6/14 (B+P 6/11)`; step diff vs the stored baseline `covered@50 lost - gained -` / `reachable lost - gained fruitfly/usb_malware_delivery`; `C0 modes loose 3/14 @50 4/14 @100 4/14 all strict 2/14 @50` |
| **Untuned control localises with `mechanism: indexed`**, not `accelerated` (botsv2 is outside the CIM allowlist) | **pass** | `localisation.indexes[0] {"width":3600,"hosts":1,"windows":2,"events":4806489,"mechanism":"indexed","model":"","coverage":"scan","accel_window":null,"notes":[]}`; the six D5 probes ran (`localise_accel 6 requests, 0 censored`) and returned no covering summary. Independent check: `| tstats summariesonly=true count from datamodel=Authentication where index="botsv2" by host _time span=3600s` → **0 rows**, the same query on `hb_ait_santos_v2` → rows. |
| **Wide-estate D1**: `pan:traffic`, `winhostmon`, `pan:system`, `ms:o365:management` read without crashing or blowing the budget | **partial** | no crash; `pan:traffic` 32/32 files (839 rows), `pan:system` 32/32 (659), `ms:o365:management` 15/15 (4,476); **`winhostmon` 1 of 9 files** (1,752 rows), 150 file-window reads refused `request_budget_exhausted`, `searches {"total": 2000}` — the request ceiling was the thing that ended the read. Details in `FINDING_HUNT_R2_BOTSV2_WIDE_ESTATE.md`. |
| **D8**: `promoted_unjudged == 0` | **pass** | `promotion {"lifted": 10, "total": 12, "judged_only": false}`, every lifted id `unjudged: false`; scoreboard `case promotion judged_only no lifted 10 unjudged_lifted 0`. Case judge: 5,731 of 5,747 cases verified (`notable_missing` 13, `evidence_not_resolved` 3), judged-only view 5,731 cases / 49,622 members, 957 dropped. |
| **D10**: `progress.json:honesty` non-null, `C0 causes` non-empty | **pass** | A: `honesty {"knowledge":"loaded","families":["kyoushi","russell","santos"],"knowledge_items":2431,"merge_method":"weighted","weights_source":"default",…}`; C: honesty non-null (knowledge `none loaded`, because `similar_to_known` did not run). `C0 causes censored 9, covered 2, instrument 1, not_surfaced 1, unreached 1`, with a per-step `cause`/`cause_source` for all 14 steps. |

## 2. Slice table (D0–D10) for botsv2

| slice | property on this family | result | receipt |
|---|---|---|---|
| **D0** | baseline reproduces; step-level sets; `C0 causes` on an entity family | **pass** | stored baseline rescored with this scoreboard: `keys 5/20 reachable steps 5/14`, `loose 3/14 @50`, `strict 2/14` — the plan's table; diff vs it prints names only (`lost -`, `gained fruitfly/usb_malware_delivery`). No `evidence_absent` step: every graded artefact's locator resolves in the estate map (the four wide sourcetypes name no graded key, §6 of the deep dive). |
| **D1** | every indexed file has its own read or a reason; wide estate read | **partial** | 1,963 `(source,file,window)` rows over 181 files: 1,813 read, 150 `request_budget_exhausted`, 19 files declared (`files_indexed 181`, `files_omitted 19`). Same-volume read (259,769 vs 260,342) for 1,813 behaviour searches. |
| **D2** | one vocabulary; no parse-only name queried; `empty` means present-and-zero | **pass, and its candidates are what crash `notables`** | `fields {'complete': 32, 'failed:censored': 1, 'parse_only': 107, 'unavailable:mechanism': 7}`, `mechanisms {'stats': 33}`, 761 values, `stream:http src_ip` 249, `linux_audit uid` 3, `stream:smtp src_ip` 116; the 7 unavailable are `events_budget` on the widest sources (`wineventlog:security EventCode` ×3, `stream:tcp src_ip` ×3, `winregistry process_image`). The complete `pan:threat dest` list (2 events) is the crash seed. |
| **D3** | `capped` implies `values > 0` | **not exercised** | no list on botsv2 exceeds `LIST_MAX`; `capped []`. `first_seen_replaced 0` (also 0 before), `candidates 32` (was 13). |
| **D4** | numeric identities typed; part is part of the key | **not measurable here** | spine `events 259769 entities 14143 episodes 122823 links 217276 without_entity 56295`; botsv2's graded steps are Windows/Suricata/stream keys, not audit `auid`, so the D4 property has no carrier on this family. |
| **D5** | rung 1 fires when a complete summary covers the window | **pass as a no-op** | six `localise_accel` probes, `accelerated []` in inventory, `mechanism: indexed`, `accel_window: null`; independent `summariesonly` probe returns nothing for botsv2. On a tuned index the same probe returns rows, so this is the allowlist, not a dead query. |
| **D6** | setup: shipper copies out, `user` regex, `auid` | **out of scope** | operator-owned; this lane made no setup change. |
| **D7** | merge consumes the measured marginal | **not met** (not a brief acceptance item) | `weights_source: "default"`, `weights {'alerts':0,'deviation':26,'misfit':6,'peer_rare':0,'similar_to_known':31}`; the scoreboard's `--weights` fold is measured but nothing feeds it back in this command. |
| **D8** | only verified members are promoted; set novelty gives the singleton a route | **pass on promotion; set novelty present** | lifted 10 / 12, `unjudged_lifted 0`; `set_novelty 147`; `case evidence pieces min 2 violations 0`. Case recall `top50 0/4, top100 0/4, all 1/4` (one scenario's B/P step is in a case at all). |
| **D9** | a flow is `(entity, host)`; a duplicate ingest is not one | **not asserted here** | `flows 11`, `flow_skips {'host': 7, 'not_entity': 11, 'same_role_vector': 7, 'single_source': 635}`; the deep dive's D9 proof is santos, and this lane did not verify duplicate-pair exclusion on botsv2. |
| **D10** | cause per step, honesty block | **pass** | §1 above. |

## 3. The failing layers

**L1 — the single 720 s job budget still cannot produce a run (D0/S6 carrier).** In Run A,
`cards` is 573.2 s of wall (113 model calls, 887 model-seconds) and the inventory that runs at
the head of `behaviours` is another 147.3 s — 720.5 s in total, i.e. the whole budget before the
first behaviour read (the same inventory takes 265.9 s when it is allowed to finish, as in Run
B). Run A therefore read **0** events, produced 39 notables over an empty store and died at
relate with `HuntDeadlineExceededError` (`relate.py:1530 → executor.py:548`). This is worse than
the morning verdict's Run A (48,412 events, 5/20 keys): the cost grew with the sourcetype count,
and it is the cards stage — a model-bound stage no slice's acceptance covers — that spends the
budget. `--stage all` cannot be the measurement command until cards stops being charged to the
same clock (a separate budget, or a cached card stage).

**L2 — `notables` crashes on the untuned control (D2 × D8 contract).** The notables stage adds
inventory candidates in memory (`run.py:548` → `inventory.apply_inventory`) and then
`similar._ranked_notables` requires *every* behaviour's source to have a card that consumes
`similar_to_known`; an **alert** card does not, so it raises. The new D2 vocabulary is what makes
it fire: `pan:threat dest` is now a complete list (2 events), producing exactly one candidate:

```
store behaviours 18668
after inventory 18700 replaced 0 candidates 32
sources only after inventory: {'botsv2:pan:threat': 1}
```

`similar.py:303` raises and `notables.jsonl` is never written, so relate/judge/scoreboard have
no input. Why this is new on `main` (reasoned from receipts, not re-run on the old tree): the
morning verdict records 13 complete lists and 6 `unavailable:mechanism` on botsv2, and its
`notables` stage completed with 876 notables — this run has 32 complete lists, and the single
extra candidate is the alert card. Two repairs are both code changes (out of this lane's
scope): skip a non-consuming card in `_ranked_notables`, or do not mint candidates for alert
cards in `_unseen_candidates`.

**L3 — D1's per-file route spends the whole request budget on the wide control.** 1,813
behaviour reads + 180 discovery + 7 localise = 2,000 (the ceiling), and `winhostmon`'s eight
smaller files are refused after its largest file is read. The read is graceful and fully
receipted, but the budget — not the data — decides what the control sees.

**Not the failing layers.** Coverage (D0), the ladder's label (D5) and case promotion (D8) all
hold on this family: `mechanism: indexed`, per-step causes, 7/20 keys with no lost step,
`promoted_unjudged 0`.

## 4. Scoreboard, baseline and the morning runs

| measure | stored baseline (re-scored today) | morning split run (`REPORT_HUNT_VERDICT_botsv2.md`) | R2 A (`--stage all`) | **R2 C (this lane)** |
|---|---|---|---|---|
| keys reachable | 5/20 | 7/20 | 4/20 | **7/20** |
| steps reachable | 5/14 (B+P 5/11) | 6/14 (6/11) | 4/14 (4/11) | **6/14 (B+P 6/11)** |
| loose @50 / @100 / all | 3 / 3 / 3 | 2 / 2 / 3 | 0 / 0 / 0 | **3 / 4 / 4** |
| strict @50 / @100 / all | 2 / 2 / 2 | 1 / 1 / 1 | 0 / 0 / 0 | **2 / 2 / 2** |
| recall-of-reachable loose @50 | 3/5 | 2/6 | 0/4 | **3/6** |
| scenarios loose @50 | 2/4 | 2/4 | 0/4 | **2/4** (3/4 @100) |
| case members top50 | 0/4 | 0/4 | 0/4 | **0/4** (1/4 all) |
| promoted / unjudged lifted | — | 7/7 | 0/0 | **10/0** |
| judge | — | 740 judged, AUC 0.589 | (none) | **725 judged, AUC 0.84**, bad 4 |
| read fraction | 0.117 % | 0.14 % | 0.048 % | **0.150 %** |
| requests | — | not reported | 756 | **2,804** (2,000 of them behaviours) |

The stored baseline's own `progress.json:honesty` is `null` and it has no inventory block: it
predates D10, so D10 is graded on this session's runs only (A and C, both non-null).

Per-step causes (C): `covered 2` (`malicious_account` @46, `ftp_download` @12), `instrument 1`
(`web_scan` @21), `not_surfaced 1` (`usb_malware_delivery`), `censored 9`, `unreached 1`
(`xss_cookie_theft`, 0 labelled lines).

## 5. Proven and not proven

**Proven (live, read-only):** the brief's `--stage all` reads 0 behaviour events and exits 1 at
relate; `notables` crashes with the quoted `SimilarityError`; the ceiling is 7/20 with a
per-step cause and no lost step vs the baseline; `mechanism: indexed` with `accelerated` probes
live and empty; the four wide sourcetypes are routed per file, three fully and `winhostmon`
partly, at exactly 2,000 requests; `promoted_unjudged 0`; `progress.json:honesty` non-null and
`C0 causes` non-empty; 725/725 notables judged (AUC 0.84).

**Not proven / not measured:** the brief's full-generator scoreboard — C is missing
`similar_to_known` (13 notables, the highest default weight 31) because of the crash; every C
coverage number is therefore a **lower bound**. `first_seen_replaced` is 0 and no list is
`capped` on botsv2, so D3 is unexercised. D4 and D9 have no carrier/proof on this family. The
judged-only path was exercised through `rerank --cases` (5,731 cases, 957 members dropped), not
by re-running relate with `judged_only`. The `peer_rare` exact-count defect persists
(`exact=0/300`, 300 ledger rows `censored`, 0 rows): re-checked live,
`| tstats count where index=botsv2 "45.77.65.211"` → no row, `TERM("45.77.65.211")` →
`168004`. `events_scanned` is still the anchor-window population (~4.81 M per wide source),
not rows scanned.

## 6. Receipts

```bash
cd /Users/chris/projects/portal-5-hunt-proof-r2-botsv2
# .env keys exported by name (python shlex export), host.docker.internal -> localhost
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099        # the brief's root form; /v1 is a 404
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables
run=$PWD/coding_task/scratch/hunt_proof_r2_botsv2

# A — the brief's command (fails)
uv run python -m $hunt --index botsv2 --out $run/botsv2 --stage all --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell

# B — stage split; behaviours completes, notables crashes
mkdir -p $run/run_b/botsv2 && cp $run/botsv2/sources.json $run/run_b/botsv2/ && cp -a $run/botsv2/cache $run/run_b/botsv2/
uv run python -m $hunt --index botsv2 --out $run/run_b/botsv2 --stage behaviours
uv run python -m $hunt --index botsv2 --out $run/run_b/botsv2 --stage notables --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell

# C — the measured run: same, minus the generator that crashes
cp -a $run/run_b/botsv2 $run/run_c/
uv run python -m $hunt --index botsv2 --out $run/run_c/botsv2 --stage notables \
  --generators alerts,peer_rare,deviation,misfit
uv run python -m $hunt --index botsv2 --out $run/run_c/botsv2 --stage relate --family botsv2
uv run python -m $hunt --index botsv2 --out $run/run_c/botsv2 --stage judge --family botsv2

uv run python -m $hunt.scoreboard --out $run/run_c \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl" \
  --weights --json
uv run python -m $hunt.scoreboard --out $run/run_c \
  --keys "botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl" \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/botsv2
uv run python -m $hunt.rerank --run "botsv2=$run/run_c/botsv2" --no-council --cases \
  --case-budget 50 --case-deadline 720 --json
```

Raw logs and score output: `coding_task/scratch/hunt_proof_r2_botsv2/{run_all.log,score_all.txt,
run_b/,run_c/}`.

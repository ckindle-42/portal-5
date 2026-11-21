# botsv2: falls short

Graded 2026-11-21 on `lane/hunt-verdict-botsv2` (HEAD `83f72271e`, clean) against
`docs/hunt/ORCACYBER_HUNT_PLAN.md` S0–S7 and the plan's §5 Step 3 pass bar. Splunk
`botsv2` only, READ-ONLY; no Splunk configuration change, no `launch.sh`, no code change.
The narrow control criteria **do** hold — `keys_reachable` did not regress and localisation is
`mechanism=indexed` — but the plan's case and enumeration acceptance properties fail, so the
family falls short.

## 0. What was run

Environment: Pipeline `http://localhost:9099` (served `gemma-4-26b-a4b-it-QAT-4bit` for
`hunt-reasoning`; embeddings `google/embeddinggemma-2`), lab Splunk 10.2.5 at
`$LAB_SPLUNK_URL` (the configured value is an IP, so no `host.docker.internal` rewrite was
needed). `PIPELINE_API_KEY`, `LAB_SPLUNK_*` exported from the live checkout's `.env`; no value
printed. Knowledge store `knowledge_v2_20261116.duckdb`, held out `kyoushi,santos,russell`.
The brief's `PORTAL_HUNT_JUDGE_URL=http://localhost:9099/v1` was used as the **root**
`http://localhost:9099`: `judge.chat_completions_endpoint` appends `/v1/chat/completions`, so
the literal `/v1` suffix resolves to `/v1/v1/chat/completions` (verified live: 404), and the
root resolves to `/v1/chat/completions` (200). This is the URL `RUN_HUNT_REDESIGN.sh` and the
S1B/S7 findings use.

Two live botsv2 runs, because the plan's own single-invocation command does not complete:

| run | command | outcome |
|---|---|---|
| **A — literal `--stage all`** | `notables --index botsv2 --out … --stage all --family botsv2 --knowledge-store … --knowledge-families kyoushi,santos,russell` | **crashes at relate**: `HuntDeadlineExceededError: job_deadline_exceeded`; 1,766 behaviour reads refused; scoreboard 5/20 keys, 0/14 |
| **B — stage-split** (the orchestrator's proof-run method: one stage per process into a new run dir seeded with Run A's cards output — `sources.json` + `cache/` copied, so the cards model cost was not paid twice; behaviours, notables, relate, judge each start a fresh 720 s shared budget) | `--stage behaviours`, `notables`, `relate`, `judge` separately | completes; **7/20 keys**, 2/14 loose @50, 0/4 cases |
| **C — stored baseline** (S0 reproduction) | scoreboard over `snap_neon_02cc2e3/results/hunt/neon/botsv2` (2026-11-19, `defd357bc`) | **5/20 keys, 3/14 loose, 2/14 strict, 3/5 and 2/5 of reachable** — the plan's table exactly |

`_v2` comparison: **not applicable**. botsv2 is the plan's original-index control
(`scripts/lab/splunk_setup/plan.py:20 CONTROL_INDEX = "botsv2"`) and has no tuned `_v2`
counterpart; the runbook deliberately keeps it out of the CIM allowlist. The only baseline this
family has is C.

Timings (wall): cards 526.2 s, behaviours 501.3 s (read 198.3, inventory 160.4, spine 22.3),
notables 271.6 s, relate 149.3 s, judge 654.5 s. A cold end-to-end run is ≈ 2,100 s; the
plan's `job_seconds` is 720 s.

## 1. S0 — truthful measurement (pass, with two instrument defects)

**Baseline reproduction passes.** `snap_neon_02cc2e3` scores

```
C0 ceiling  keys 5/20 reachable  steps 5/14 (B+P 5/11)  stores {behaviour, events, misfit}
C0 recall-of-reachable  loose @50 3/5  strict @50 2/5
C0 modes  loose 3/14 @50   strict 2/14 @50
```

which is the plan §3 table (3/14 / 2/14, reachable 5/14, recall-of-reachable 3/5 / 2/5).
The new C0.2 fields are present in both live runs: `case_recall`, `promotion_effect`,
per-generator `attribution@50` and `marginal@50/@100`, per-step `cause`, `ledger.jsonl`
(985 rows in A, 1,898 in B), and the `cost` block.

Two defects prevent the run's cost/coverage numbers from being a clean instrument:

1. **`peer_rare` exact counts are broken live.** Run B's receipt is
   `"exact_counts": {"candidates": 300, "counted": 0, "queries": 300,
   "reasons": {"read_failed:HuntSearchFailedError": 300}}`; the ledger shows 300 queries
   `| tstats count where index="botsv2" "10.0.1.1" "10.0.1.100"` recorded `censored` with 0
   rows. Verified independently against the live Splunk:
   `| tstats count where index="botsv2" "45.77.65.211"` → **no row**;
   `| tstats count where index="botsv2" TERM("45.77.65.211")` → `{"count":"168004"}`.
   The bare quoted term in a `tstats` filter returns nothing on this build, so the peer_rare
   generator never gets exact counts (baseline was 300/300). Commit `5b13cb38c` changed
   `TERM(...)` to a plain quoted term; this is live-visible now.
2. **`events_scanned` on a rung-3 read is the anchor window's population, not rows scanned.**
   Run B reports `events_scanned: 4,811,307` on every wide source (e.g. `winregistry`, which
   read 4,818 rows of 55.5 M), because `sample.read_anchors` sets
   `found.events_scanned = sum(anchor.events)` — the two selected windows' tstats counts — and
   `_merge_anchored` adds the kept uniform rows. The field therefore cannot be used as a scan
   cost; the C0.2 cost block uses the ledger instead.

## 2. Slice acceptance — graded for botsv2

| slice | property botsv2 exercises | result | receipt |
|---|---|---|---|
| **S0** instrument | baseline reproduces; ledger, causes, case/marginal fields | **pass** | §1; `C0 modes` line identical to the plan for C |
| **S0** instrument | promoted raw row cannot raise strict/case recall | unit-proven, not exercised here | run B `promotion effect promoted=7 strict top50 1/1 with/without; case top50 0/0` |
| **S1** enumeration | a **complete** list on a KV source; `values > 0`; `stats` with `events_scanned`; `first_seen_replaced > 0`; `unavailable` never reported as `empty` | **fail** | 13 complete lists exist (`linux_audit.uid` — the named `exe` field was not selected — 3 values, 457 k scanned, 10.9 s; `stream:http.src_ip` 249 values; `stream:mysql.src_ip` 3; `stream:ftp.src_ip` 2; osquery/AD lists), mechanisms `stats: 26`, `two_names: 1`, but **`first_seen_replaced: 0`** (`candidates: 10`; the acceptance needs `first_seen_replaced > 0`); 6 `unavailable:mechanism`, 13 `empty` |
| **S2** spine/episodes | spine built; every source receipt reports `read_mode` and `read_fraction` | **pass** (build-family carrier property not this lane) | B: `events=260342 entities=15921 episodes=125228 links=219653 without_entity=53075` (20.4 % are measurement-shaped rows); `read_mode {'anchored': 83, 'whole': 20}`; every receipt has `read_fraction`; spine `sources[*].read_fraction` present |
| **S3** cases/flows/promotion | ≥ 1 case in the top 50 per scenario with a B/P member; every case ≥ 2 evidence pieces; `coverage_complete`/`uncapped` reported; promotion cannot add unjudged to a judged-only view | **fail** (headline) | B: `case members top50 0/4  0/4  0/4`, `case recall 0/4`, `first true case 827  false cases above it 827`; 5,867 cases, `related notables 0` (all 40 relate evidence reads `censored`, 0 rows), `case evidence pieces min 2 violations 0`, `coverage_complete False`, `uncapped_fraction 0.573688`, `unjudged cases 167`, `promotion judged_only no lifted 7 unjudged_lifted 7` |
| **S4** alerts | `alerts existed > 0` on botsv2; a Suricata alert card is read as a detection stream; no alert notable without an entity | **pass on `existed > 0` and entities; Suricata-as-detection unproven** | B: `alerts: existed=4 kept=4 seconds=3.62` (sources `ess_content_importer`, `ms:o365:management#StatusDisplayName=Service restored`, `pan:threat`); all 4 notables carry an entity. The `suricata` source was read as activity (4,818 events, 991 behaviours), not as an alert stream, and produced no alert notable |
| **S5** weights | marginal re-merge table + `attribution@50`; `existed == 0` keeps unit weight; hit at 51 reported 0/@50 > 0/@100 | **instrument present; property not exercised on botsv2** | B table: `deviation candidates 19195 kept 247 attribution@50 1/1 marginal@50 1 marginal@100 1 merge_weight 1`; all others `marginal 0/0`, `merge_weight 1` (`UNMEASURED_WEIGHT`); notables receipt says `weights_source: "default"`, i.e. the scoreboard's marginal vector was not passed to the run. botsv2 has no generator whose hit leaves the head at 51, so the `0/@50 > 0/@100` case is not exercised; it was proven on russell by the S5 lane. A single family cannot LOFO |
| **S6** localisation | `mechanism=indexed` on the untuned control; `coverage=scan`, `accel_window` recorded; keys ceiling holds with per-key cause; every read carries `events_scanned`; read fraction per source | **pass (letter) / fail (cost, see §3)** | B: `localisation {"width":3600,"hosts":1,"windows":2,"events":4806489,"mechanism":"indexed","model":"","coverage":"scan","accel_window":null,"notes":[]}`; 83 receipts `rung=narrowed_scan`, `coverage=scan`, non-null `events_scanned`; 7/20 keys with causes; `read_fraction 0.001405` (0.14 %, baseline 0.117 %) |
| **S7** judge over cases | unverified anchor reported; judged-only excludes unjudged; no case dropped by model answer; p_yes only orders | **pass** | `rerank --cases --case-budget 50`: `cases 5867 verified 5865 unverified 2 (evidence_not_resolved) unverified_members 26 judged 50 unjudged 5817 order.moved 50 judged_only 5849 cases / 50598 members (dropped 283)`; budget 0 control: `judged 0 unjudged 5867 order.moved 0`, cases unchanged. Notable judge: `judged 740 bad 3 good 737 AUC 0.589 yes_rate_bad 1.0 yes_rate_good 0.714` — p_yes is close to the yes-always bias; it is not a pass gate in the plan |

## 3. The failing design layers

**S3 — cases (the headline).** The plan's §5 Step 3 bar is "≥ 3 of 4 botsv2 scenarios have a
case in the top 50 that contains a B/P member naming an artefact (strict rule)". Run B gives
**0/4**, and no B/P member is in *any* of the 5,867 cases
(`case members top50 0/4 top100 0/4 all 0/4`). The first case whose payload names a scenario is
at rank 827, behind 827 false cases. The case builder assembles 5,867 structurally valid cases
(`evidence_pieces min 2 violations 0`) but its head is benign. The relate stage's own
re-verification did not run: all 40 seeds' evidence reads are `censored` with 0 rows over the
30-day case window against two wide mysql sources (`mysql:transaction:details` 30,
`mysql:server:stats` 10) because the `| eval _relate_delta=… | sort limit=20` read exceeds the
bounded search; the same query through the transport with a narrow window returns 20 rows. So
`related notables 0` and `coverage_complete False`.

**S1 — enumeration wiring.** The enumeration half works (13 complete lists, 26 `stats`
mechanisms, 538 values, 10.1 M events scanned, `two_names: 1`), but it does not change a
behaviour: `first_seen_replaced: 0` and `candidates: 10`. The lists are enough to put 7 keys in
the reachable ceiling (`ledger` 7, `misfit` 3, `spine` 4, `events` 4, `behaviour` 3) but no
notable names the added values. This is the plan's S1 acceptance property, and it fails on the
wide control.

**S0/S6 — the single job budget cannot produce the run.** The literal command in the brief
(`--stage all`) does not complete: cards alone is 526.2 s of model-driven wall time and
inventory 160–166 s of Splunk searches, both charged to the one 720 s
`job_seconds` budget (`executor.py:28`, "shared hunt wall time across every worker", started
when the cards stage first calls `executor_for`). Run A's behaviours stage then issued 1,766
reads that were refused with `job_deadline_exceeded`; 81 of 103 source receipts read **0**
events (all 81 carry that note), the run read 48,412 events instead of 260,342, and recall is
**0/14**. `--stage all` never reaches relate: the stage walls alone (526 + 236 + 76 = 838 s)
exceed 720 s before relate's first read. Stage-splitting (B) is the only way the plan's own
acceptance can be measured on a cold wide index. The plan's Step 3 says "same code, no tuning"
and `--stage all` per §4 S6; as written it cannot pass.

The ladder itself is labelled correctly and is **not** the cause of the 0/14: in Run B
`mechanism=indexed`, `coverage=scan`, `accel_window=null` on the untuned control, 2 one-hour
windows on one host (`cassiopeia`), and the anchored reads contributed only 9,275 rows of the
260,342 (114 host-filtered reads, 57 sources; 14 sources returned rows). The coverage still
comes from the equal-slice baseline, and the read fraction (0.14 %) is essentially the old
sample (0.117 %), not a localised read. That is consistent with the plan's own measured risk
that host pruning on botsv2 Windows saves little, but it means S6's "ask the estate where the
rare thing is" is not demonstrated by this run.

**S5/S7 are not the failing layers.** S5's marginal table is present but the run used default
weights (`weights_source: default`); the only @50 contributor is `deviation` (marginal 1). S7's
deterministic verification, judged-only view and no-drop property all hold; the notable judge's
AUC 0.589 on 3 positives is too small a positive class to judge ordering quality (the plan keeps
p_yes out of the pass bar).

## 4. Baseline vs runs

| measure | C stored (2026-11-19) | A `--stage all` | B stage-split |
|---|---|---|---|
| keys reachable | 5/20 | 5/20 | **7/20** |
| steps reachable | 5/14 (B+P 5/11) | 5/14 (B+P 5/11) | **6/14 (B+P 6/11)** |
| loose @50 / @100 / all | 3 / 3 / 3 | 0 / 0 / 0 | 2 / 2 / 3 |
| strict @50 / @100 / all | 2 / 2 / 2 | 0 / 0 / 0 | 1 / 1 / 1 |
| recall-of-reachable loose/strict @50 | 3/5 / 2/5 | 0/5 / 0/5 | 2/6 / 1/6 |
| scenarios loose @50 | 2/4 | 0/4 | 2/4 |
| cases in top 50 (B/P members) | n/a (no case store) | 0/4 | 0/4 |
| alerts existed | 0 | 0 | 4 |
| read fraction | 0.117 % | 0.077 % | 0.14 % |
| `localisation.mechanism` | n/a (no localiser) | indexed | indexed |

The keys ceiling did not regress (5 → 7 → 5); the recalled steps moved down one at @50
(`malicious_account` @45 → not surfaced; `web_scan` 20 → 37; `ftp_download` 13 → 21;
`macbook` 33 → 155). Under the plan's own definition, the only botsv2 pass bar that the
coverage layer must meet without the Splunk setup is "ceiling reported with a per-key cause and
no regression", and that is met. The case bar is not.

## 5. What is proven and what is not

Proven (live, read-only):
- The stored baseline reproduces exactly (C).
- `keys_reachable` on the live control (7/20 in B; 5/20 in A) with a per-step cause and
  `events_scanned` on every receipt.
- `localisation.mechanism=indexed`, `coverage=scan`, `accel_window=null` on botsv2.
- The `--stage all` command fails at relate with `job_deadline_exceeded`; the 1,766 deadline
  refusals and 81 zero-read receipts are in `progress.json`.
- `alerts existed=4`, all with an entity.
- S7's verification/judged-only/no-drop properties on the live cases.

Not proven / out of reach:
- The `_v2` comparison: no botsv2 `_v2` index exists.
- The plan's post-setup coverage bar (≥ 12/24 keys) on botsv2: the CIM models exclude botsv2 by
  design, so it is unreachable by construction and not attempted.
- S3's build-family acceptance: this lane grades botsv2 only.
- Whether the 7/20 ceiling rise is caused by the new lists (2 values came from `misfit`/`ledger`
  in B; the other 5 are the old stores). It is a ceiling, not surfaced content.
- The judge's usefulness: 3 positive rows, AUC 0.589, yes-rate 1.0/0.714; the plan keeps p_yes
  out of the pass bar.
- The `peer_rare` exact-count defect is live-visible, but its effect on recall is nil here
  (peer_rare contributes 0 @50).

## 6. Receipts

Run A (literal), the failure:

```
behaviours: events_read=48412 ... wall=46.576s
  read_mode per source: {'anchored': 83, 'whole': 20}
notables: ... total=706 wall=76.026s
relate: ... HuntDeadlineExceededError: job_deadline_exceeded
scoreboard: C0 ceiling keys 5/20 reachable steps 5/14 ... C0 modes loose 0/14 @50
```

Run B (stage-split), the complete run:

```
behaviours: events_read=260342 existed=19036 kept=19036 ... wall=198.262s
  inventory searches=32 seconds=160.416 fields={'complete': 13, 'empty': 13, 'unavailable:mechanism': 6} values=538 joints=13 flows=0 ... first_seen_replaced=0
  read_mode per source: {'anchored': 83, 'whole': 20}
  spine: events=260342 entities=15921 episodes=125228 links=219653 without_entity=53075
notables: ... alerts existed=4 kept=4 ... total=876 wall=271.593s
relate: seeds=40 requests=40 related_events=0 cases=5867 flows=0 promoted=7 coverage_complete=False wall=147.007s
judge: notables=876 judged=740 unjudged=136 ... budget=674 ... served=['gemma-4-26b-a4b-it-QAT-4bit']
scoreboard: keys 7/20 reachable steps 6/14 (B+P 6/11)
  C0 modes loose 2/14 @50 2/14 @100 3/14 all strict 1/14 @50 1/14 @100 1/14 all
  case members top50 0/4 top100 0/4 all 0/4
  first true case 827 false cases above it 827
rerank --cases --case-budget 50: cases 5867 verified 5865 unverified 2 judged 50 order_moved 50 judged_only 5849 cases / 50598 members
```

Commands (copy-pasteable):

```bash
cd /Users/chris/projects/portal-5-hunt-verdict-botsv2
set -a; . /Users/chris/projects/portal-5/.env; set +a
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables
data=/Volumes/data01/portal5_hunt
run=$PWD/coding_task/scratch/botsv2-control-staged

# B: one stage per process (same code; fresh shared budget per stage).
# The cards stage is reused from Run A because it is model-bound and its output is the
# same either way; copy it so the read budget is not charged for it again.
mkdir -p "$run/botsv2"
cp coding_task/scratch/botsv2-control-stageall/botsv2/sources.json "$run/botsv2/"
cp -a coding_task/scratch/botsv2-control-stageall/botsv2/cache "$run/botsv2/"
# (or run: uv run python -m "$hunt" --index botsv2 --out "$run/botsv2" --stage cards --family botsv2)
uv run python -m "$hunt" --index botsv2 --out "$run/botsv2" --stage behaviours
uv run python -m "$hunt" --index botsv2 --out "$run/botsv2" --stage notables --family botsv2 \
  --knowledge-store "$data/knowledge/knowledge_v2_20261116.duckdb" \
  --knowledge-families kyoushi,santos,russell
uv run python -m "$hunt" --index botsv2 --out "$run/botsv2" --stage relate --family botsv2
uv run python -m "$hunt" --index botsv2 --out "$run/botsv2" --stage judge --family botsv2
uv run python -m "$hunt".rerank --run botsv2="$run/botsv2" --cases --case-budget 50 --case-deadline 720

uv run python -m "$hunt".scoreboard --out "$run" \
  --keys "botsv2=$data/corpora/botsv2_keys/keys.jsonl"
```

# Splunk setup runbook — staged, costed, verifiable, reversible

Executes `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` §5 (Target setup) and §8 (the operator's
decisions) against the lab Splunk. **Nothing in this document has been applied.** Every stage is
run by the orchestrator, one at a time, and each stage is gated by its own verification before
the next starts. The order is forced by the measurement in that document:
**sourcetype → TA/CIM → reindex → acceleration → summaries**.

Everything is generated from one source of truth, `scripts/lab/splunk_setup/plan.py`, so the
reindex mapping and the `props`/`transforms`/`tags`/`datamodels`/`savedsearches` conf files cannot
disagree:

```bash
uv run python -m scripts.lab.splunk_setup app --check      # committed app tree is in sync
uv run python -m scripts.lab.splunk_setup plan --index santos
```

---

## 0. How the lab Splunk is reached

| path | how | named key / default |
|---|---|---|
| REST (all mutations + every verification search) | `https://10.0.1.30:8089`, basic auth, `verify=False` | `LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`, `LAB_SPLUNK_PASSWORD` |
| HEC (the reindex ships here) | `https://10.0.1.30:8088/services/collector/event` | `LAB_SPLUNK_HEC_URL`, `LAB_SPLUNK_HEC_TOKEN` |
| SSH (app copy, restart, `splunk show config`) | `ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST` → `pct exec 301 -- docker …` | `LAB_PROXMOX_HOST` (default `10.0.0.203`), `LAB_SSH_KEY` (default `~/.ssh/portal-lab_id_ed25519`), `PROXMOX_SSH_USER` (default `root`) |

These are the keys already in `.env.example` (§ "Splunk SIEM (Proxmox LXC 301 — 10.0.1.30)");
this runbook adds none. **Never `source .env`** — export by name in the shell that runs a stage:

```bash
set -a; export $(grep -E '^LAB_SPLUNK_(URL|USER|PASSWORD|HEC_URL|HEC_TOKEN)=' .env | xargs); set +a
```

The Splunk container is `splunk` inside Proxmox LXC 301 (the repo's `lab_host.py` convention is
`ssh → pct exec`; the container name and LXC id are CLI flags, `--container splunk --lxc-id 301`).

## 1. What changes, and what does not

| # | brief item | where in this runbook |
|---|---|---|
| 1 | enable the TAs and CIM bindings for the training sourcetypes | stage 1 |
| 2 | accelerate the CIM models (optionally Change) with the doc's window | stage 3 |
| 3 | normalise sourcetypes by a reindex to explicit `sourcetype=` per input | stage 2 |
| 4 | index-time entity extraction for the training indexes, same reindex | stage 2 (conf is in stage 1) |
| 5 | route `stats.log`, perfmon and mysql noise out | stage 2 |
| 6 | one `collect` summary per index | stage 4 |
| 7 | keep one untuned index as the degradation control | `botsv2` — see below |

**New index names only.** Every reindexed event lands in `<index>_v2`
(`hb_kyoushi_s1_v2`, `hb_ait_santos_v2`, `hb_ait_russellmitchell_v2`). The four existing indexes
are never written, never cleaned and never deleted by any stage; rollback of stage 2 is a single
`DELETE` of the `_v2` index.

**The untuned control is `botsv2`.** Three independent reasons, in order of weight:

1. It **cannot** be normalised: BOTS v2 ships as pre-indexed Splunk buckets
   (`scripts/lab_bots_install.py`), there is no raw corpus on disk in
   `/Volumes/data01/portal5_hunt/corpora/` to re-ingest, so "set the sourcetype per input" has no
   input to act on.
2. It is where the degradation the hunt must keep meeting was **measured**: the same Windows
   events answer to `WinEventLog` on the raw path and `wineventlog:security` on the tsidx path
   (§4.2 of the realism doc). Keeping it untuned keeps that trap live.
3. It is 23.5 GB / 226 M events / 451 days — ≈6× the three families' bytes together (3.7 GB)
   and ≈3× their events. Keeping it out of the acceleration window also keeps the build cost
   small (stage 3).

To make that structural rather than incidental, the CIM index allowlist macros for the six
accelerated models (`cim_*_indexes`) are scoped to the three `_v2` indexes, so data-model
acceleration physically cannot build summaries over `botsv2`. The scope is written into
**Splunk_SA_CIM's own local config** by stage 1, because that app ships those macros with an empty
`()` default that wins over a copy in any other app — measured live 2026-11-21: the search parser
normalised the invocation to `litsearch ()`. No other model's macro is touched.
Side effect, deliberate and visible: on `botsv2` those six models stop populating (today they
populate as a ~200 s scan). The `tags` from `botsv2_data_set` are untouched, so
`tag=authentication` still works there; only `tstats from datamodel=` is gone. Stage 5's control
probes assert exactly this.

**Measured volumes** (from the three ingest receipts, `<corpus>_ingest/receipt.json`;
regenerate with `uv run python -m scripts.lab.splunk_setup inventory`; the full table is
`scripts/lab/splunk_setup/inventory.json`):

| index | events in | kept for `_v2` | dropped as noise | files kept | source files |
|---|---:|---:|---:|---:|---:|
| `hb_kyoushi_s1` | 24,504,858 | 2,465,043 (10.1 %) | 22,039,815 | 218 | 225 |
| `hb_ait_santos` | 25,143,873 | 4,474,600 (17.8 %) | 20,669,273 | 250 | 380 |
| `hb_ait_russellmitchell` | 25,522,335 | 4,191,003 (16.4 %) | 21,331,332 | 257 | 380 |

The kyoushi "kept" number reproduces the realism doc's independently measured huntable volume
(~2.5 M) — the classifier and the doc agree.

---

## Stage 0 — preflight (read-only)

**Command** (≈1 min, 0 disk):

```bash
uv run python -m scripts.lab.splunk_setup preflight | tee coding_task/scratch/splunk_setup/preflight.json
```

It reads `/services/server/info`, the seven TAs' enable state, whether each `_v2` index exists,
and the acceleration state of the seven models (via `| rest /services/data/models`).

**Expected:** `version` starts `10.2`; every TA in `apps` is `false` except `Splunk_TA_nix` /
`Splunk_TA_aws` (already enabled today); every `_v2` index is `false`; every model shows
`acceleration.enabled = 0`.

**Rollback:** none — read-only.

**Record the pre-state** (the proof afterwards that the original indexes did not change):

```spl
| eventcount summarize=false index=botsv2 OR index=hb_kyoushi_s1 OR index=hb_ait_santos OR index=hb_ait_russellmitchell
```
→ four rows; copy the counts into `coding_task/scratch/splunk_setup/preflight.json`.

---

## Stage 1 — app, TAs, CIM bindings, new indexes (~3–5 min, <10 MB)

**What it does** (`apply`): renders the app from `plan.py`, streams it into
`/opt/splunk/etc/apps/portal5_hunt_setup`, enables the TAs, writes the six `cim_*_indexes`
overrides into `Splunk_SA_CIM`'s local `macros.conf` (REST), creates the three `_v2` indexes,
extends the HEC token's index allowlist, and restarts Splunk. Each step reads state first and
writes only on a difference, so re-running it is a no-op (proved by
`tests/unit/test_splunk_setup.py::test_stage_one_apply_is_idempotent`).

**Command** (from the repo root, on the orchestrator host):

```bash
uv run python -m scripts.lab.splunk_setup apply --dry-run        # prints every action first
uv run python -m scripts.lab.splunk_setup apply
```

`apply` renders the app with `datamodels.conf` **empty** (acceleration is stage 3, after the data
exists — the doc's forced order). The committed tree under
`scripts/lab/splunk_setup/app/portal5_hunt_setup/default/` is the **stage-3** state (acceleration
on); `app --check` proves it is exactly what the renderer produces.

**The conf files it installs** (committed, generated — `scripts/lab/splunk_setup/app/portal5_hunt_setup/default/`):

| file | what it binds |
|---|---|
| `props.conf` | `INDEXED_EXTRACTIONS=json` for `suricata`; index-time `TRANSFORMS-ph_ix_*`; search-time `EVAL-*` aliases to CIM names |
| `transforms.conf` | one regex per index-time field (auditd `acct`/`exe`/`addr`/`terminal`/`uid`; auth `user`/`src`; access-log `c_ip`/`cs_method`/`cs_uri_stem`/`sc_status`; fast-log `signature`/`src`/`dest`; dnsmasq `dns_query`/`src`) — one `[ph_ix_*]` stanza per field, each with `WRITE_META = true` |
| `fields.conf` | `INDEXED = true` for every index-time field, incl. the JSON keys the doc names (`alert.signature`, `dns.rrname`, `http.url`, …) |
| `eventtypes.conf` + `tags.conf` | the CIM tag constraints: `authentication`, `web`, `ids`+`attack`, `network`+`communicate`, `network`+`resolution`, `endpoint`+`process`+`report` |
| `datamodels.conf` | empty at stage 1; stage 3 writes acceleration for the six models, `acceleration.earliest_time = -10y` |
| `savedsearches.conf` | one `collect` per tuned index (stage 4) |

The `cim_*_indexes` macros are **not** in this app: `apply` POSTs them to
`/servicesNS/nobody/Splunk_SA_CIM/configs/conf-macros/<macro>` with
`definition = (index=hb_kyoushi_s1_v2 OR index=hb_ait_santos_v2 OR index=hb_ait_russellmitchell_v2)`.
A copy under `portal5_hunt_setup` was rendered until 2026-11-21; it loses to Splunk_SA_CIM's
empty `()` default in every app context, so it was dropped. An app install left on the box by an
earlier run may still hold it — it is inert (it loses too) and `rollback`'s app removal takes it
out with the rest of the app.

**Index-time fields need `WRITE_META = true`.** A `TRANSFORMS-*` stanza extracts the value, but
without `WRITE_META` Splunk keeps it out of the tsidx — so `tstats` cannot group by it — and
because `fields.conf` marks the same names `INDEXED = true`, search-time extraction does not fill
the gap either. The failure is silent: `| tstats … by acct` returns 0 rows and no error. Measured
live 2026-11-21 on the first `santos` reindex; the orchestrator's `WRITE_META` hotfix then
answered `by acct exe` on a single HEC probe event. Every `[ph_ix_*]` stanza the renderer emits
now carries the flag, and stage 5's `verify` asserts the **rows**, not the conf text. The flag is
an index-time setting, so it cannot be applied to an index that was already built — that index has
to be dropped and re-shipped (stage 2).

The 2026-11-21 hotfix lives in the box's `local/transforms.conf`. `local/` wins over `default/`,
so once the regenerated app is installed that copy is redundant and would silently override any
later change to the default. Remove it, then re-install:

```bash
ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST \
  "pct exec 301 -- docker exec -u splunk splunk rm -f /opt/splunk/etc/apps/portal5_hunt_setup/local/transforms.conf"
uv run python -m scripts.lab.splunk_setup apply      # re-installs default/ and restarts Splunk
```

**Why the window is `-10y` and not a SOC's `-30d`:** `acceleration.earliest_time` is relative to
*now*; these corpora are 2021-03 and 2022-01. A `-90d` window would accelerate nothing at all and
every `tstats summariesonly=true` would return 0 rows — the exact silent failure the doc warns
about (§6 rule 4).

**Retention on the new indexes** (`INDEX_SETTINGS`): `frozenTimePeriodInSecs = 365000000`
(≈11.5 y), `maxTotalDataSizeMB = 20000`. A 10-day retention, as the doc's §5.5 suggests for the
*families' data span*, is measured from **event time**: on 4-year-old events it would freeze and
delete the entire index during ingest. The span is small; the retention must cover 2021–2022.

**Verification** (expect each line to match):

```bash
ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST \
  "pct exec 301 -- docker exec -u splunk splunk /opt/splunk/bin/splunk show config props" \
  | grep -c 'INDEXED_EXTRACTIONS = json'          # >= 1  (our stanza is loaded)
```

```bash
ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST \
  "pct exec 301 -- docker exec -u splunk splunk /opt/splunk/bin/splunk show config transforms" \
  | grep -c 'WRITE_META = true'                   # >= the renderer's [ph_ix_*] stanza count
```
→ compare against `grep -c '^\[ph_ix_' scripts/lab/splunk_setup/app/portal5_hunt_setup/default/transforms.conf`.
Fewer means the installed app (or a stale `local/` copy) lost the flag — see the `WRITE_META`
paragraph above. This is still a conf check; the property itself is stage 5's `entity_indexed`.

```spl
| rest /services/data/indexes | search title=*_v2 | table title maxTotalDataSizeMB frozenTimePeriodInSecs
```
→ exactly 3 rows; `frozenTimePeriodInSecs = 365000000`.

```spl
| rest /servicesNS/nobody/Splunk_SA_CIM/configs/conf-macros | search title=cim_Web_indexes | table title definition
```
→ one row whose `definition` is `(index=hb_kyoushi_s1_v2 OR index=hb_ait_santos_v2 OR
index=hb_ait_russellmitchell_v2)`.

**The conf row is not the proof.** Splunk_SA_CIM's `()` default still exists behind that row and
still wins if the local override is not the one being resolved. The property is the **parser
expansion**, and `verify` reads it from the search job's `normalizedSearch` for each of the six
macros (a `` search `cim_Web_indexes` | head 0 `` probe):

```bash
uv run python -m scripts.lab.splunk_setup verify | tee coding_task/scratch/splunk_setup/verify.json | head -90
```
→ the first six entries are `"probe": "cim_macro:cim_<Model>_indexes"`, each `"failed": false`
with an `"expansion"` that names all three `_v2` indexes. **Fail if** an expansion is
`litsearch ()`, or names a non-`_v2` index — that is the 2026-11-21 finding, and it means the
override did not land in Splunk_SA_CIM's local config. `rollback` restores the seven defaults
(`definition = ()`).

```spl
| tstats count where index=hb_ait_santos by sourcetype
```
→ **unchanged** ~126 rows (the original index is untouched; no event was written to it).

**Rollback** (≈2 min, deletes nothing but the app):

```bash
uv run python -m scripts.lab.splunk_setup rollback --index santos --dry-run   # shows what changes
uv run python -m scripts.lab.splunk_setup rollback --index santos
```

It resets the seven `cim_*_indexes` macros in Splunk_SA_CIM to CIM's own `()` default (a no-op for
`cim_Change_indexes` unless `--with-change` was applied) and prints, for you to run: remove
`/opt/splunk/etc/apps/portal5_hunt_setup`, restart, and
`POST …/apps/local/<ta>/disable` for every TA the stage enabled.

---

## Stage 2 — reindex each family into `<index>_v2` (one stage per index)

**What it does:** ships each input named in the existing ingest receipt, byte-for-byte (same
record splitter, same timestamp parser, same host/source as `scripts/hunt_bed/ingest_native.py`),
with an **explicit sourcetype** from the mapping table, into `<index>_v2`. Noise files are not
shipped at all.

**Why the receipt and not a directory walk:** the receipts *are* the definition of what is in the
index today. Re-globbing the corpus would change the host/file set (the original kyoushi ingest
included 11 of the 32 host directories), and `keys.jsonl` joins on `(host, source, line)`. Using
the receipt keeps the digests identical — verified offline on one file per corpus: the reindex's
`sha256("host|source|raw")[:24]` equals `digests.jsonl` (`acme_mail/auth.log`,
`cloud_share/apache2/error.log`, `cloud_share/apache2/error.log.1`). Pointing the hunt at `_v2`
therefore needs **no** key rebuild.

**Cost** (measured ingest rates from the receipts: 52 k ev/s kyoushi, 31 k ev/s santos/russell):

| stage | events shipped | duration | disk added (estimate) |
|---|---:|---|---|
| `kyoushi` | 2,465,043 | ≈50 s send + index lag → **2–4 min** | ≈0.2–0.5 GB |
| `santos` | 4,474,600 | ≈145 s + lag → **3–5 min** | ≈0.4–0.9 GB |
| `russellmitchell` | 4,191,003 | ≈136 s + lag → **3–5 min** | ≈0.4–0.9 GB |

Disk is an estimate: kept events × ~104 B/event compressed (botsv2's measured 23.5 GB / 226 M),
then +40–100 % for index-time extraction (doc §5.4 — an estimate, to be measured on the first
index). Each `_v2` index is capped at 20 GB (`INDEX_SETTINGS`) against ≈0.5 GB of data, so there
is no capacity risk.

**Commands** (per index; `santos` shown):

```bash
uv run python -m scripts.lab.splunk_setup plan --index santos      # routing table + files_resolvable
uv run python -m scripts.lab.splunk_setup reindex --index santos   # dry run: reads + parses only
uv run python -m scripts.lab.splunk_setup reindex --index santos --ship
```

`plan` must print `"files_missing": []` and `files_resolvable` = 250 (santos) / 218 (kyoushi) /
257 (russellmitchell) before anything is shipped. `--ship` refuses to start when the target index
already holds events (re-running would duplicate them); `--resume` continues a stopped run from
`coding_task/scratch/splunk_setup/reindex/<index>.receipt.json`.

**Noise routing (brief item 5).** Dropped from `_v2` by default:
`stats.log` (89 % / 81 % / 82 % of each family) and the metricbeat `system.*` metric files
(`-system.{cpu,diskio,filesystem,fsstat,load,memory,network,process,…}.log`, the Linux analogue of
perfmon). `botsv2`'s `perfmon:*`/`mysql:*`/`collectd` cannot be routed at index time — it is
pre-indexed and is the untuned control; the hunt must still classify that noise structurally
(realism doc §6 rule 9), which is a read-policy requirement, not an index setting.
`--keep-metrics` ships the metric files into `_v2` instead (for a before/after comparison) —
default is out.

**Verification** (after the index's `reindex` returns):

```spl
| eventcount summarize=false index=hb_ait_santos_v2
```
→ `count` = 4,474,600 (± a few events; HEC is exact per event, and the count settles within ~1 min).

```spl
| tstats count where index=hb_ait_santos_v2 by sourcetype
```
→ **≤ 16 rows**, one per data type. **Fail if** any name matches `^\d{4}-\d{2}-\d{2}-` (the
per-day names survived) or the row count is anywhere near 126.

```spl
| tstats count where index=hb_ait_santos_v2 sourcetype="stats.log"
```
→ 0 rows (noise routed out).

```spl
| tstats count where index=hb_ait_santos_v2 by acct | head 5
```
→ >0 rows with real account names. This is the whole point of stage 2+4: an **entity field in the
tsidx**, which the lab has never had (`user`/`src`/`acct` were search-time only, §2.6).
**Fail if 0 rows** — that is the 2026-11-21 failure: the transform extracted the field but did not
write it to the metadata (`WRITE_META`), and `fields.conf`'s `INDEXED = true` stopped the
search-time fallback from filling the gap. Fix stage 1's `transforms.conf`, then rebuild this
index — the flag acts at index time, so `rollback --index santos` and `reindex --index santos
--ship` again; a restart alone changes nothing already indexed. `verify --index santos` now fails
on exactly this, by row count.

```spl
| tstats count where index=hb_ait_santos_v2 sourcetype="suricata" by event_type
```
→ rows for `alert`, `flow`, `dns`, `http` (JSON index-time extraction working).

**Rollback** (instant, deletes only the copy):

```bash
uv run python -m scripts.lab.splunk_setup rollback --index santos
# curl -X DELETE $LAB_SPLUNK_URL/services/data/indexes/hb_ait_santos_v2
```

Re-running the stage after a rollback is a clean re-ingest from the corpus (the corpus is on
disk and unchanged).

---

## Stage 3 — accelerate the six models over `-10y` (~5–15 min, 100–300 MB)

**What it does:** writes `datamodels.conf` (acceleration on, window, cron `*/10`,
`max_concurrent = 1` so the build is serial on a 14-core VM), re-installs the app, restarts, and
waits for the first build. `Change` is opt-in (`--with-change`) and is **not** recommended here:
its volume is `winregistry`, which only exists in `botsv2`, which is the control.

**Cost:** a build is one search per model over its events. Measured `tstats`-class scan rates put
each family's six-model build at ~10 s per model (doc §5.3), so **~3 min of compute** plus up to
10 min waiting for the `*/10` cron tick. Summary size is the doc's 5–15 % assumption, scaled to
these volumes: **≈100–300 MB** total, against ~1.5 GB of `_v2` data. Verified after the build
from `/services/admin/summarization`, not before.

**Command:**

```bash
uv run python -m scripts.lab.splunk_setup apply --accelerate     # re-render + install + restart
```

`--accelerate` refuses to run until every `_v2` index holds events (it reads `eventcount` for
each), so the "accelerate an empty index" mistake cannot happen silently. It also enables the
`Change` model if `--with-change` is passed.

**Verification:**

```spl
| tstats summariesonly=true count from datamodel=Authentication by Authentication.user
```
→ **> 0 rows in ≈0.1 s, scanCount 0** (a summary read, not a scan). Before the change the same
query returned 0 rows in 0.12 s; unaccelerated (`summariesonly=false`) the model took 199.9 s to
count 2.59 M events on `botsv2`.

```spl
| rest /services/admin/summarization | table title summary_size complete
```
→ six entries with `complete = 1` and `summary_size > 0`. `summary_size` replaces the 5–15 %
assumption with a measurement — record it.

**Control probe (the degradation must survive):**

```spl
| tstats summariesonly=false count from datamodel=Authentication by Authentication.user
  earliest=2017-08-01 latest=2018-10-30
```
→ **0 rows** (and `scanCount` 0): `botsv2` is outside the CIM macro allowlist, so the model does
not even look at it. `summariesonly=false` is the point — with `true` the probe would return 0
rows whether or not the macro worked. If this returns the 2.59 M events the realism doc measured,
the macro precedence went the wrong way (stage 1's `verify` would already have failed) — fix before continuing.
Second check: `| rest /services/admin/summarization | table title earliest latest` must show no
entry covering 2017-08..2018-10.

**Rollback:** re-run `apply` **without** `--accelerate` (one command: strips `datamodels.conf`,
installs, restarts). Existing summaries stop being maintained and are removed by Splunk after the
window; no index is touched.

---

## Stage 4 — one `collect` summary per index (~1 min, <1 MB)

**What it does:** enables the three saved searches installed in stage 1, one per tuned index,
each writing per-entity first/last seen to the (currently empty) `summary` index:

```spl
index=<index>_v2 sourcetype="linux_audit"
| stats count dc(host) as hosts min(_time) as first_seen max(_time) as last_seen by acct
| addinfo
| collect index=summary marker="hunt_entities_index=<index>, hunt_source=portal5_hunt_setup"
```

`marker` is a comma+space-separated key=value string (that is the only form Splunk parses into
fields), and `addinfo` supplies the fields `collect` wants for a manual/backfill run.

**Cost:** the summary search reads only `linux_audit` (19–25 k events per family) — **<10 s per
index** — against the doc's "one scan per day" budget.

**Command:**

```bash
uv run python -m scripts.lab.splunk_setup summary --run-now
```

**Verification:**

```spl
index=summary hunt_entities_index=hb_ait_santos | stats count | head 1
```
→ a non-zero count (the marker is parsed at search time, so use `search`, **not** `tstats` — a
`tstats by hunt_entities_index` returning nothing would be the silent-zero trap this whole setup
exists to remove). Then `index=summary hunt_entities_index=hb_ait_santos | head 1 | fields *`
→ fields `acct`, `count`, `hosts`, `first_seen`, `last_seen`.

**Rollback:** disable the searches (`rollback --index santos` prints the call); optionally
`index=summary hunt_entities_index=<index> | delete` (needs the `can_delete` role).

---

## Stage 5 — the full verification pass

```bash
uv run python -m scripts.lab.splunk_setup verify --index santos | tee coding_task/scratch/splunk_setup/verify.json
```

It runs the six `cim_*_indexes` parser expansions, then an `entity_indexed:<index>` probe for
**every** tuned index (the `by acct` tstats, so one pass covers all three), then — when `--index`
is given — that index's other probes (events / sourcetypes / accelerated model), then the three
control probes. It reports `rows`, `scan_count`, `run_seconds` and the expected result for each,
and **fails on a probe that returned fewer rows than it declares**, not only on a failed job. What
"worked" looks like, in one place:

| probe | expected | what a failure means |
|---|---|---|
| `cim_macro:cim_<Model>_indexes` ×6 | the expansion names all three `_v2` indexes | the override is not in Splunk_SA_CIM's local conf — re-run `apply` |
| `eventcount index=<i>_v2` | = the table's kept count | a file failed to ship — `--resume` |
| `tstats … by sourcetype` on `_v2` | ≤16 rows, no date-in-filename names | mapping missed a class |
| `entity_indexed:<i>_v2` (`tstats … by acct`) ×3 | >0 rows | the transform did not write meta (`WRITE_META` missing) or the index predates the fix — rebuild the index, a restart cannot repair it |
| `tstats summariesonly=true from datamodel=Authentication` | >0 rows, scan 0 | tags or acceleration missing |
| `tstats … index=botsv2 sourcetype="WinEventLog" by host` | 0 rows | the control was normalised — stop |
| `tstats … index=botsv2 sourcetype="wineventlog:security" by host` | >0 rows | the two-name split changed — stop |
| `tstats … from datamodel=Authentication` (`summariesonly=false`) over 2017-08..2018-10 | 0 rows, scan 0 | the allowlist lets the control into CIM — stop |

Then re-measure the four rows of the realism doc's §3 table on a `_v2` index and record the
before/after in that document — the numbers there are what the next slice (S1 Tier B) is
accepted against.

---

## 6. What is measured and what is estimated

| number | status |
|---|---|
| events in / kept / dropped per index; file counts | **measured** from the three ingest receipts |
| the sourcetype → data-type mapping (227 names → 15 data types) | **measured** against those receipts; every name classified, none unmapped; 14 are shipped (`stats.log` dropped, `metricbeat:system` opt-in) |
| digest parity with `digests.jsonl` | **checked** on one real file per corpus (3 of 3 match) |
| ship duration | **estimated** from each corpus's own measured ingest rate |
| `_v2` disk use | **estimate** (104 B/event proxy, +40–100 % extraction) until `dbinspect` after stage 2 |
| acceleration build time | **estimate** from the doc's measured scan rates; `cron */10` adds up to 10 min of waiting |
| summary size | **assumption** (doc's 5–15 %); replaced by `summary_size` after stage 3 |
| macro precedence over the CIM defaults | **measured live 2026-11-21** — the app copy loses to Splunk_SA_CIM's `()` defaults in every app context, so `apply` now writes the override into Splunk_SA_CIM's local conf and `verify` asserts the parser expansion |
| that an index-time field reaches the tsidx | **measured live 2026-11-21** by the orchestrator — without `WRITE_META` the `santos_v2` `tstats … by acct` answered 0 rows; with it, one HEC probe event answered `by acct exe`. Not yet re-measured on a full re-shipped index |
| that the live Splunk accepts this conf | **unproven** — no stage was run |

## 7. Promotion (after stage 5 passes)

Only after `verify` is clean: point the hunt's `--index` at `<index>_v2` for the families and
re-run S1 Tier A/B. Then, and only then, consider mirroring the setup onto `botsv2` (which needs a
from-raw reindex that does not exist on disk — i.e. it needs the BOTS archive re-ingested, not
this script). The original indexes stay as they are until a `_v2` index has produced a scored run.

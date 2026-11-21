# OrcaCyber deep dive #2 — why the tuned lab run fell short, and the replan

Round 2 of the hunt lane, 2026-11-21. Reads first: `ORCACYBER_HUNT_PLAN.md` (the S0–S7 plan),
`ORCACYBER_CODE_REVIEW.md` (the build it was written from), `SPLUNK_REALISM_AND_SETUP.md` and
`SPLUNK_SETUP_RUNBOOK.md` (the lab tuning), and `coding_task/REPORT_HUNT_VERDICT_santos.md` (the
stored-run verdict this dispatch starts from).

Everything below is either **[live]** (a query I ran in this session against the lab Splunk or a
stored run's DuckDB/ledger on disk, command in §9), **[code]** (a line I read) or **[reasoned]**.
Where a number already existed in a prior report I re-derived it rather than quoting it, and I say
so when my re-derivation disagrees with the earlier report — twice below it does.

Held-out sets untouched: `hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1` were never opened, queried
or read in this session. Training families only (`hb_ait_santos{,_v2}`,
`hb_kyoushi_s1{,_v2}`, `hb_ait_russellmitchell{,_v2}`; `botsv2` was touched for one
read-only estate-map probe of its multi-file sourcetypes, §6).

---

## 0. The answer in one page

**The `_v2` run did not fall short because the re-ingest renamed the fields the spine was tuned
on. It fell short because the re-ingest changed what a "source" *is*, and every coverage decision
in the read path still assumes one source = one file.** 227 sourcetypes became 14; the per-source
budget, the source-name route (capped at eight files), the `head N` window sample and the per-source
read receipt were all written for the pre-consolidation world. On `_v2` each of them silently
samples the *union of many files*, so per-file coverage is uncontrolled and unrecorded.

That has three consequences, all measured:

1. **The read targeted the wrong files, not fewer events.** Behaviour-stage volume is flat
   (santos 213,233 rows on `_v2` vs 224,253 on the control; kyoushi +11 %, russell −13 %) but the
   Apache access logs — where every web step lives — were starved. On santos the file carrying
   87 % of the attacker's HTTP evidence (`/apache2/intranet.smith.santos.com-access.log`, 8,254 of
   its 9,462 events from the attacker IP) ranked **14th of 21** files in its sourcetype and was
   dropped by the 8-file route cap entirely. On kyoushi and russell the labelled file *was* in the
   route and still received 313 and 57 events respectively, because `| head N` over the pooled
   route returns whatever arrival order gives it.

2. **The hunt and the estate speak different field vocabularies.** The setup delivered exactly what
   the plan asked for — index-time `c_ip`, `vhost`, `cs_uri_stem`, `acct`, `exe`, `signature`,
   `dns_query`, and six complete accelerated CIM models — and the hunt asks for none of it. Its card
   roles on template-parsed sources are *slot names the parser invented* (`template`, `program`,
   `v1..v6`); 20 of the 32 value lists it ran on santos were `stats … by <slot name>`, which no
   search can answer, so they could only ever return `empty`. Meanwhile the estate answers the
   lists it actually needs in **0.3–0.4 s each**: `access_combined` `dc(c_ip)=18` (complete),
   `linux_audit` `dc(acct)=13` (complete), `dc(exe)=7` (complete), `suricata:fast`
   `dc(signature)=22` (complete).

3. **The measurement could not see any of this, and two of its numbers are artefacts.** The
   `_v2` keys file was never rebuilt after noise routing deleted a labelled file, so
   `crack_passwords` is unreachable *by construction* (44/44 labelled lines in
   `2022-01-17-system.cpu.log`, present 3,840 times in the original index and **0 times** in
   `_v2`). And the "read fraction rose from 1.44 % to 5.75 %" in the santos verdict is a
   denominator effect — the index fell from 25.1 M to 4.47 M events, and the fraction's numerator
   includes `cards`-stage metadata rows (116,688 on the control vs 15,962 on `_v2`), not new
   evidence.

The orchestrator's schema-seam hypothesis is **half right and half falsified**. Falsified: the
spine does not read the Splunk schema at all — it parses raw text with its own field plan, so a
renamed sourcetype cannot untype an entity. The `fields_typed 5 vs 31` line in the santos verdict
is a source-count artefact (the same six template slots multiplied by 131 source ids on the control
versus 17 on `_v2`), and most of what it "lost" was noise (`GET`, `Closing`, `Opening`, `is`, `to`
were all typed as *users* on the control). Confirmed: there *is* a schema seam — it sits between
the hunt's field vocabulary and the estate's, and it is the single largest recoverable win in the
system (§3.2).

Two further defects are independent of the re-ingest and would have bitten any run:

- **S5 never reached the run.** The scoreboard measures the marginal weights correctly
  (deviation 9, similar_to_known 1, others 1) but the run merged on `DEFAULT_WEIGHTS`
  (`weights_source: "default"`, deviation 26 / similar_to_known 31). So **31 of the 50 head slots
  went to a label-trained generator whose measured reliability AUC on this family is 0.443** —
  below chance — that uniquely contributes **one** step, while the generator that contributes nine
  got 26.
- **S6 rung 1 is dead in code, not merely unexercised.** Acceleration is live and complete
  (every model root reports `summary.complete = 1`; `Network_Resolution` 72.6 MB,
  `Intrusion_Detection` 4.2 MB) and
  `| tstats summariesonly=true count from datamodel=Authentication by Authentication.user` answers
  in 0.58 s. The hunt still reports `accelerated: []` because `ACCEL_QUERY` selects
  `datamodel_name`, a field `/services/admin/summarization` does not have — `title` and `id` do.
  The runbook documented exactly this trap; the code was not updated for it.

The honest reading of the santos S6 bar: **the tuned run lost three steps outright and the ratio
moved for a fourth reason.** Net step coverage at @50 within reachable steps went 11 of 12 to 8 of
11 — and the eight are a strict subset of the eleven minus the three web steps. No step was newly
covered at @50.

---

## 1. What I did (and what it cost)

| action | scope | result |
|---|---|---|
| re-scored 6 stored runs (3 families × {`_v2`, control}) with the current scoreboard | offline | §2.1 table |
| re-derived the C0 per-step cause and reachability per run | offline | §2.2, §3.1 |
| re-ran the spine's entity typing per run, in-process, on the stored `behaviours.duckdb` | offline | §3.4 |
| reconciling the keys against the `_v2` index membership | offline + 2 live counts | §3.3 |
| 21 read-only Splunk probes (job API, `scanCount`/`runDuration` recorded) | lab Splunk 10.2.5 | §9 |
| read `sample.py`, `behaviours.py`, `inventory.py`, `spine.py`, `cards.py`, `merge.py`, `run.py`, and the setup app's `props`/`transforms` | code | §3 |

No lab configuration was changed. No held-out index was touched. `.env` was read by key name only,
never sourced. Scratch scripts: `coding_task/scratch/deepdive2/`
(`spl.py`, `diag_spine.py`, `routes.py`, plus the score JSON/txt).

---

## 2. The measurement, re-derived

### 2.1 Six runs, side by side

Scoreboard at `a23b18446`, keys unchanged from the stored runs, logs on disk.

| family | run | index events | behaviour rows read | sources read | recall line @50 | C0 reachable steps | C0 recall-of-reachable @50 | labelled lines read verbatim |
|---|---|---:|---:|---:|---|---|---|---|
| kyoushi | control | 24,504,858 | 179,719 | 33 | 11/12 | **11/12** | 11/11 | 1,944 / 408,038 |
| kyoushi | `_v2` | 2,465,043 | 198,703 | 15 | 11/12 | **7/12** | 7/7 | 287 / 408,038 |
| santos | control | 25,143,873 | 224,253 | 48 | 15/21 | **12/21** | 11/12 | 866 / 47,367 |
| santos | `_v2` | 4,474,600 | 213,233 | 14 | 16/21 | **11/21** | 8/11 | 3,002 / 47,367 |
| russell | control | 25,522,335 | 205,120 | 63 | 15/22 | **15/22** | 14/15 | 725 / 61,862 |
| russell | `_v2` | 4,191,003 | 177,428 | 15 | 13/22 | **11/22** | 9/11 | 2,502 / 61,862 |

[live, `scoreboard --json`, §9]

Three things follow immediately.

- **The regression is not santos-specific.** The C0 ceiling fell on all three families
  (11→7, 12→11, 15→11). A santos-only diagnosis would have been wrong.
- **Raw recall and C0 disagree, and C0 is the comparable one.** Santos raw recall *rose*
  (15→16) while its ceiling fell: the coverage rule credits a notable whose evidence query names a
  literal that occurs in the labelled line, whether or not the run read it — it scans the raw log on
  disk [code `scoreboard.py:_coverage`]. Only the C0 ceiling is read-relative.
- **Read volume is flat; read placement is not.** `_v2` read 198,703 / 213,233 / 177,428
  behaviour rows against 179,719 / 224,253 / 205,120 — a −13 %…+11 % band. The tuned index did not
  read less. It read different files, and on all three families it read the *wrong* ones.

**Correction to the santos verdict.** Its `read fraction 0.057489 vs 0.014434` is total ledger
rows over index events [code `scoreboard.py:_cost`], not evidence coverage: the numerator includes
`cards`-stage metadata rows (santos `_v2` 15,962 vs control **116,688** — `tstats by sourcetype
source/host` returns many more rows over 131 sourcetypes) and the denominator fell 5.6× because
20.7 M events were routed out. The comparable number is the behaviour-stage row count in the table
above.

### 2.2 Which steps the tuned read lost, and which it found

Per-step C0 reachability, `_v2` vs control [live]:

| family | steps the `_v2` read lost | steps it newly reached |
|---|---|---|
| kyoushi | `attacker_http`, `dirb`, `webshell_cmd`, `webshell_upload` | — |
| santos | `attacker_http`, `dirb`, `wpscan` | `attacker_change_user`, `exfiltration-service` |
| russell | `attacker_http`, `dirb`, `wpscan`, `webshell_cmd`, `webshell_upload` | `exfiltration-service` |

**Every lost step is a web/access-log step.** No DNS, audit, auth or VPN step was lost on any
family. That is the signature of one mechanism, not of a general read regression — and it points
straight at `sourcetype=access_combined`.

Globally (not read-relative) the @50 sets move too, and not always for a read reason: santos `_v2`
loses `webshell_upload` and gains `dns_scan` + `traceroute`; russell loses `webshell_cmd` and
`webshell_upload`; kyoushi's global @50 set is identical (11 steps). The santos gains are
claim-matching against the raw log on disk, on lines the run never read, so they are not findings —
which is the whole reason the acceptance has to be read-relative.

The steps `_v2` *newly* reached are worth naming because they change the story of the ranker:
`attacker_change_user` (rank 95), `attacker_vpn` (143) and `exfiltration-service` (never covered)
are steps the control could not reach at all. The tuned index did not make the ranker worse; it
made three of the ranker's blind spots visible for the first time. That is progress that the
`recall-of-reachable` ratio records as a *fall*, because the denominator moved from 12 to 11 with
harder members. **A ratio is the wrong instrument here** (§5).

**The arithmetic the D1 fix buys, and what it does not.** The three steps santos lost currently sit
at `first_rank` 42 (`attacker_http`), 42 (`dirb`) and 28 (`wpscan`) — i.e. a notable already claims
each of them, inside the @50 cut; the run simply never read the lines. So D1 alone moves santos to
**14 reachable, 11 covered @50 = 11/14 = 0.786**, still below the plan's `11/12 = 0.917`. The
remaining three are `attacker_change_user` (95), `attacker_vpn` (143) and `exfiltration-service`
(never). **The S6 bar cannot be met by coverage work alone on this corpus; it needs D8 as well.** Stated
as a step set instead of a ratio, the target is unambiguous: reachable = every step the index can
contain, and `covered ∩ reachable` ⊇ the control's set.

---

## 3. Root causes

### 3.1 RC1 (P0, CONFIRMED) — a "source" is now a sourcetype; every coverage decision still assumes one file

The evidence chain, three families, two independent methods (stored store + live Splunk).

**(a) The route drops files silently at eight.** `route_filter` builds the read's `source=` OR-list
from `facts.sources[:BEHAVIOUR_SOURCES]` with `BEHAVIOUR_SOURCES = 8` [code `sample.py:21,478-480`],
and `facts.sources` is ranked **by event volume** [code `sample.py:455`]. On `_v2` santos,
`access_combined` has 21 files; sorted by count, the file carrying the whole web intrusion is #14:

```
 1 /horde/horde-access.log                              119321
 ...
13 /apache2/cloud.smith.santos.com-access.log             9570
14 /apache2/intranet.smith.santos.com-access.log          9462   <-- never queried
...
21 /apache2/intranet.smith.santos.com-access.log.2        1706
```

[live `| tstats count where index=hb_ait_santos_v2 sourcetype=access_combined by source`; and the
run's own ledger row for `by sourcetype source` agrees token for token]

The behaviour read's query for that source contains eight `source="…"` names, none of them the
intranet file [live, `ledger.jsonl` stage `behaviours`]. The card's own facts say
`source_count: 21`, and only 12 survive into `sources.json` [code `cards.py:519`].

**(b) When the file *is* in the route, `head N` starves it anyway.** kyoushi's labelled file is
rank **1 of 26** (408,477 of 726,213 events) and russell's is rank **4 of 21**, so both were inside
the eight-name route — and the store holds only 313 (kyoushi, of 14,330 access events
read) and 57 (russell) events from the labelled host [live, DuckDB `select host,count(*)
from events where source_id like '%access_combined' group by 1`].

Proved live at the same query shape, russell:

```
search index=hb_ait_russellmitchell_v2 (source="…/horde-access.log" OR …eight names…) | head 1250
  -> mail 620, webserver 618, davey_mail 12, intranet_server 0        scan 3,481, 0.47 s
search index=hb_ait_russellmitchell_v2 source="…/intranet.smith.russellmitchell.com-access.log.2"
  | head 1250
  -> 1,250 rows                                                       scan 2,792, 0.50 s
```

[live] `head` is a first-N-in-index-order sample of the union, not a per-file allocation. Under one
file per query that was harmless; under 26 files it is the difference between reading the attack and
not.

**(c) The consequence is total for santos.** That single file is 8,254/9,462 attacker-IP requests
[live `| tstats count … by c_ip`] and 7,786 of the family's 47,367 labelled lines. With it unread,
`attacker_http` (7,828 labelled lines), `dirb` (4,485) and `wpscan` (3,312) cannot be reached by
any ranking.

**(d) Nothing in the receipt can tell you this happened.** The receipt reports one
`events_available`/`share_of_source` for the whole sourcetype and never a per-file line
[code `behaviours.py` receipt]. `files_routed / files_indexed` does not exist anywhere, so a
coverage collapse of this size is invisible in every artefact the run writes.

### 3.2 RC2 (P0, CONFIRMED) — the hunt and the estate use different field vocabularies, and the estate's is the cheap one

The setup's whole point was index-time entity fields and accelerated CIM models. They are there:

| what I asked the index | answer | cost |
|---|---|---|
| `dc(c_ip)` on `access_combined` | **18** values (complete) | 0.31 s, 329,442 scanned |
| `dc(cs_uri_stem)` on `access_combined` | 13,963 (cappable) | 0.34 s |
| `dc(acct)` on `linux_audit` | **13** (complete) | 0.34 s |
| `dc(exe)` on `linux_audit` | **7** (complete) | 0.34 s |
| `dc(signature)` on `suricata:fast` | **22** (complete) | 0.34 s |
| `dc(dns.rrname)` on `suricata event_type=dns` | 19,463 | 0.39 s |
| `dc(dns_query)` on `dnsmasq` | 20,031 | 0.34 s |
| `summariesonly=true from datamodel=Authentication by Authentication.user` | real users (gmorgan, root, www-data, …) | 0.58 s |

[live, §9]

What the run asked instead, from `inventory.json` [live, stored run]: **32 lists, of which 20 are
`stats … by template`, `by program` or `by v1..v6` — names that exist only inside the hunt's own
template parser** and are not Splunk fields at all. Every one of them returned `empty`. The two
`access_combined` slot lists (`v3`, `v5`) and the three `suricata:fast` slot lists (`v4`,`v5`,`v6`)
are structurally incapable of a non-zero answer, and each costs a full scan to discover it — the
exact silent-zero class `SPLUNK_REALISM_AND_SETUP.md` §4.2 warns about, in a new form.

Where the two vocabularies happen to coincide — the JSON `suricata` source, whose keys are both the
parse fields and the indexed fields — `tstats` works perfectly: 5 complete lists at 0.44 s each.
**The mechanism is proven; the field selection is what fails.**

This is the faithful reading of the santos verdict's "the `_v2` spine typed 5 fields vs 31". The
spine types *fields*, not index fields; on `_v2` it typed `(source, v3)`, `(source, v2)`,
`(source, v6)` and `(source, system.service.name)`; on the control the same four names plus the same
slots repeated across per-day souretype ids. Counted by *name* the two runs type 4 and 7; most of
the extra seven are noise — the control's user entities are headed by `GET` (16,746),
`Closing` (23,532), `Opening` (23,196), `PHP`, `Declaration`, `is`, `to`, `from` [live, DuckDB].
`fields_typed` is a source-count metric wearing an entity-typing name.

### 3.3 RC3 (P0, CONFIRMED) — one `_v2` step can never be reached, and the scoreboard cannot say so

The runbook's claim that "pointing the hunt at `_v2` needs no key rebuild" holds for the 250 files
that were shipped and fails for the ones noise routing dropped. Stage 2 routes out the metricbeat
`system.*` files; the santos keys put **44 labelled lines** inside those files:

```
crack_passwords            0/44 labelled lines survive in _v2   <-- no evidence exists at all
escalate                  47/91 (44 lost)
```

[live: `| tstats count where index=hb_ait_santos source="*2022-01-17-system.cpu.log"` → 3,840;
the same on `hb_ait_santos_v2` → **0**]

So the `_v2` santos ceiling is hard-capped at 20/21 before a single read, and the scoreboard's
`labelled_lines` denominator (47,367) is the same number on both runs even though 44 of those lines
cannot exist in one of them. `crack_passwords` was already unreachable on the control (the read
never touched the file), so it is not a *regression* — but it is an acceptance criterion
(`recall-of-reachable ≥ 11/12`) computed against a step that one run cannot ever reach, and the
report gives no hint. This is the same class of honesty failure S0 exists to prevent.

### 3.4 RC4 (P1, CONFIRMED) — the S2 "spine failure" is one numeric identity and one source-count artefact

Recomputing `verify_steps` in-process on both stores [live, `diag_spine.py`]:

- The two `_v2` failures are **one physical line**, labelled with both `attacker_change_user` and
  `escalate` — fix that line's typing and both steps pass (11/11):

  ```
  type=LOGIN msg=audit(1642420697.752:2279): pid=20750 uid=0 old-auid=4294967295
  auid=1002 tty=(none) old-ses=4294967295 ses=318 res=1
  ```

  Its only identity is a **numeric** `auid`. `classify()` takes a value as a user only through a
  field name in `_USER_FIELDS` (this record's field is `auid`) or through `_user_shaped`, which
  requires at least one letter [code `spine.py:347-348`]. `1002` is therefore not an entity, and
  the record contributes nothing to the spine. The identical blindness exists on the control
  (751/7,788 audit events without an entity) — it only surfaced on `_v2` because `_v2` finally
  *read* that line (the control never did).

- `fields_typed 5 vs 31` is explained in §3.2: it is `len(overrides)`, keyed by `(source_id, field)`
  [code `spine.py:661`], so it multiplies by the source count. It is not evidence of a schema seam.

- The spine receipts' `episodes 19,296 vs 34,499` and `links 25,037 vs 62,928` are the same
  artefact: episodes are keyed `(entity, source_id, part)` [code `spine.py:606`], so 131 per-day
  source ids fragment the same entity into more groups. Neither number measures quality.

**The fix is verified offline, not argued.** I rebuilt the `_v2` santos spine from the stored store
into `coding_task/scratch/deepdive2/spine-v2-patched/` (hardlinked `behaviours.duckdb`, nothing in
the proof run touched). The baseline rebuild reproduces the stored receipt exactly
(`fields_typed 5`, `events_without_entity 3,351`, `verify 9/21`). Adding `uid`,`auid`,`gid`,`euid`,
`sid` to `_USER_FIELDS` then gives:

```
patched rebuild: events_without_entity 3,351 -> 2,958   user entities 134 -> 139
patched verify:  9/21 steps -> 11/21 steps             lines_without_entity 2 -> 0
```

[live] So D4 is a five-word change that takes the santos S2 acceptance from 9/11 to 11/11 and
removes 393 untyped audit records; the only reason it looked like a "schema seam" is that the tuned
index read the record for the first time.

One genuine seam-adjacent loss does exist: **parse coverage**, see RC5.

### 3.5 RC5 (P1, CONFIRMED) — one card per sourcetype, but a consolidated sourcetype carries two shapes

`linux_secure` on `_v2` holds both plain syslog (`/auth.log`, `/auth.log.1`) and the filebeat JSON
copies shipped from `monitoring/logstash/*/202*‑system.auth.log`
[live `| tstats count … sourcetype=linux_secure by source`: 14 files, 9,864 events].
One card, one format → the JSON lines fail the syslog template:

```
linux_secure            events_read 8,403  out_of_structure 2,921  unparsed 34.8 %
control auth.log        events_read 6,744  out_of_structure 1,049  unparsed 15.6 %
```

[live, run receipts] The same happens to the access logs: `_v2 access_combined` unparsed 11.8 %
vs 0.0–3.1 % for each of the six access sources on the control. The parser's own shape machinery
(`MIN_PARTITION_DISTANCE`, partitions up to 8) could have split them; the card is keyed on
sourcetype and the reads never apply the partition predicate unless a card declares one on a field.

### 3.6 RC6 (P1, CONFIRMED) — S5: the instrument measured the marginals and the run threw them away

Scoreboard on the stored `_v2` santos notables:

| generator | kept | attribution@50 | marginal@50 | merge weight (measured) | weight the run used |
|---|---:|---|---:|---:|---:|
| deviation | 123 | 9 steps (0.563) | **9** | 9 | 26 |
| similar_to_known | 300 | 7 steps (0.438) | **1** | 1 | **31** |
| misfit | 23 | 0 | 0 | 1 | 6 |
| alerts | 76 | 0 | 0 | 1 | 0 |
| peer_rare | 300 | 0 | 0 | 1 | 0 |
| relate | 0 | 0 | 0 | 1 | — |

[live `scoreboard --json`; `progress.json:stages.notables.merge.weights_source = "default"`]

So the measured marginal works (S5's *instrument* is done and correct), the run did not consume it,
and the practical effect is that the head gives 31 of 50 slots to a generator whose measured value
is one step and whose label-trained reliability on the held-out families is
`reliability_auc 0.443` [live, `honesty` block] — below chance. `PORTAL_HUNT_MERGE_WEIGHTS` was
never set for either run.

### 3.7 RC7 (P1, CONFIRMED) — rung 1 is dead in code while acceleration is live on the box

```
| rest /services/admin/summarization by_tstats=1 | eval model=title
| table model summary.complete summary.size summary.earliest_time
-> tstats:DM_Splunk_SA_CIM_Authentication        complete=1 size=311,296
   tstats:DM_Splunk_SA_CIM_Intrusion_Detection   complete=1 size=4,206,592
   tstats:DM_Splunk_SA_CIM_Network_Resolution    complete=1 size=72,630,272
   … every model root complete, all earliest 1616425561 / latest 1643094189 (covers both families' spans)
| tstats summariesonly=true count from datamodel=Authentication by Authentication.user
-> real users, 0.58 s
```

[live] And yet: `inventory.json accelerated: []`, `model_probes: 0`, `probe_failures: []` — the
probe succeeded and parsed nothing, because `ACCEL_QUERY` reads `row.get("datamodel_name")` and the
summarization endpoint has no such field [code `inventory.py:32-35,350-372`]. `SPLUNK_SETUP_RUNBOOK.md`
§3 says so in as many words. Rung 1 therefore cannot fire on any Splunk, ever, regardless of what
stage 3 builds — and the runbook's own control probe (`summariesonly=true` answering 0.1 s) is what
the hunt was supposed to consume.

### 3.8 RC8 (P1, CONFIRMED) — a capped list keeps nothing

`_values` returns `("capped", [])` as soon as the aggregate exceeds `INVENTORY_MAX_VALUES`
[code `inventory.py:478-480`]. The plan requires the opposite: "keep per-host top-k and the rarest
values, never pretend it is exhaustive" (`ORCACYBER_HUNT_PLAN.md` §2.2). Live consequence on santos:
`suricata:dns.rrname` — the object field of the DNS model and the carrier of the `dnsteal` scenario —
is `status: capped, values: []`. `dnsmasq.dns_query` (20,031 values) is the same. Two high-cardinality
lists that could carry the exfil domain contribute exactly zero.

### 3.9 RC9 (P2, CONFIRMED) — a partitioned card's read ignores the partition

The two `suricata` activity cards declare `part.event_type = dns` and `= flow`, and each read
25,000 events — but the read query carries no `event_type=` predicate:

```
search index="hb_ait_santos_v2" (source="/suricata/eve.json" OR source="/suricata/eve.json.1") | head 1250
```

[live, ledger] So the same pooled events are read twice under two different field plans (25,000 × 2
= 25 % of the whole santos behaviour budget), and each part's identity plan is applied to records
from the other part. The inventory *does* apply the part predicate; the behaviour read does not.

### 3.10 RC10 (P1, CONFIRMED) — the tuning left a duplicate copy of the estate inside the tuned index

Noise routing dropped `system.cpu.log` and friends but not the **service-state** shipper logs:

```
| tstats count where index=hb_ait_santos_v2 source="*system.service.log"   -> 1,856,634
| eventcount summarize=false index=hb_ait_santos_v2                       -> 4,474,600
```

[live] **41.5 % of the "tuned" index is a filebeat copy of `system.service.log`**, indexed under
`sourcetype=syslog`, and the hunt reads it (`syslog` receipt: 11,250 events, 14 windows) and types
its contents as users (41 user entities, including `auditd.service`, `cloud-final.service`,
`smbd.service`). The same shipper copies duplicate the auth logs (`/logstash/*/system.auth.log` →
`linux_secure`, 1,090 events whose `user` is corrupt, see below) and the syslog.

Related setup defect, same class: `ph_ix_linux_secure_user` is
`REGEX = (?:…|for user )(\S+)` [code `scripts/lab/splunk_setup/…/transforms.conf:5-8`]. On compact
filebeat JSON there is no whitespace after the username, so `\S+` swallows the rest of the record:

```
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_secure by user | where length(user)>64
-> /logstash/internal-share/2022-01-13-system.auth.log   366 events   (user = 'ait","@version":"1",…')
```

[live] `fields.conf` marks `user INDEXED=true`, so there is no search-time fallback: the CIM
`Authentication` model's `user` for those events is that blob. This is an index-time defect in the
setup the lane was told to trust, not in the hunt.

### 3.11 RC11 (P2, CONFIRMED) — the flow signal has never had a real input, and consolidation removed its only spurious one

`_flows` keeps a value seen in 2–12 sources [code `inventory.py:274-312`]. On the control, all 17
flows are `mail.info`↔`mail.log` pairs — **the same file ingested twice** — so the only "cross-source"
fact the signal ever found was a duplicate, and `relate` discarded all 17 as `censored.flow_roles`
[live, `inventory.json`, `relate` receipt]. On `_v2` the two duplicate sources collapsed into one, so
`flows: 0`. The DNSteal scenario has 38,561 dnsmasq lines, one attacker address, a DNS object and an
internal-share audit trail — a textbook ingress→exfiltration pair — and not one flow, because a flow
requires the value to appear in two *sourcetypes* and the story lives inside one (`dnsmasq` query →
`suricata` flow → `access_combined` request are three different values, and none repeats across
sources).

---

## 4. What the plan and the setup got wrong or left out

| # | where | what | evidence |
|---|---|---|---|
| 1 | plan §2.2 | "Field choice: from card roles … plus parse fields" — assumes card roles name fields the estate has. On template-parsed sources they name *parser slots*. No acceptance check ever asked "does the estate expose this name?" | RC2, 20/32 lists structurally empty |
| 2 | plan §2.3, S6 | "a source whose full event count fits the budget is read whole; otherwise anchored" and "receipts report read fraction per source" — both assume source = file. Under consolidation there is no per-file number, so a 0 % read of the file that matters is invisible | RC1 |
| 3 | plan S1 acceptance | never says the (source, field) pair must be *nameable in a search*; `empty` still absorbs "this name cannot exist" | RC2 |
| 4 | plan S6 acceptance | "no build-family regression: recall-of-reachable @50 ≥ 11/12" compares a ratio across **different reachable sets**. On santos the 8/11 set is the 11/12 set minus three web steps plus three ranker misses — a ratio hides both facts | §2.2 |
| 5 | plan §3 C0 | `keys_reachable` is defined over read stores, but nothing checks that a labelled line *exists in the index*. A re-indexed family needs a keys-rebuild step; the runbook says none is needed | RC3 |
| 6 | plan S2 acceptance | "every graded step's carrier entity has an episode" is satisfiable only if the spine can type the carrier. Numeric Linux identities (`auid`, `uid`) are untypeable by construction | RC4 |
| 7 | plan §2.4 signal 4 (flows) | "value in ≥2 sources with different role vectors" is a *cross-file* notion that consolidation erased, and it never distinguished duplicates from transitions | RC11 |
| 8 | plan §2.2 capped lists | requires top-k/rarest retention; delivered `[]` | RC8 |
| 9 | runbook stage 2 | noise routing list omits `system.service.log` / `system.auth.log` / `system.syslog.log` — 41.5 % of the tuned index is a duplicate shipper copy | RC10 |
| 10 | runbook stage 2 | 227 sourcetypes → 15 collapses two raw shapes (`plain syslog` + `filebeat JSON`) under one sourcetype, and one `vhost_combined` + `combined` pair under `access_combined`; the card layer has one format per sourcetype | RC5 |
| 11 | runbook stage 1 | `ph_ix_linux_secure_user` is not JSON-safe; `user` is corrupted (and `INDEXED=true` blocks the fallback) | RC10 |
| 12 | runbook stage 1 | no index-time `auid`, though `auid`/`acct` is the identity the auditd su-chain uses; `acct` exists but the hunt never selects it | RC2, RC4 |
| 13 | runbook §3 / code | the field-absence trap it documents (`datamodel_name` does not exist) was never applied to `ACCEL_QUERY`; rung 1 is dead | RC7 |
| 14 | pipeline execution | `RUN_HUNT_REDESIGN.sh` never sets `PORTAL_HUNT_MERGE_WEIGHTS` and never passes `--weights`; the marginal instrument is unreachable from the only script that runs the plan | RC6 |

---

## 5. The replan — slices ready to farm

**The bar is reset before anything else.** Ratios across changing denominators produced this
dispatch. Every slice below is accepted on a **step-level, read-relative** property, and the
scoreboard must print the two sets (covered ∩ reachable) so a loss is a named step, never a moved
ratio.

The acceptance, stated so it cannot be gamed:

- **No regression:** `reachable ⊇` the control run's reachable set, and `covered@50 ∩ reachable ⊇`
  the control's covered set. For santos that is the 12 reachable steps and the 11 covered at @50
  the control has today.
- **Stretch (the plan's real goal):** reachable = every step whose evidence the index contains —
  kyoushi 12/12, santos 20/20 (`crack_passwords` excluded, RC3), russell 22/22 — with
  `evidence_absent` counted separately. A family that cannot reach one of those prints which step
  and why, and that is a finding, not a failure.
- **No ratio in any headline.** Ratios stay in the appendix, beside their denominators.

Dependency order: **D0 → D1 ‖ D2 ‖ D5 → D3 → D4 → D6 ‖ D7 ‖ D8**, with D9 anytime.
Parallel groups a set of lanes can take at once: **(D1 ‖ D2 ‖ D5)** touch different files
(`behaviours.py`/`sample.py`, `inventory.py`, `inventory.py`'s probe only — split by file, not by
function), **(D7 ‖ D8 ‖ D9)** are independent of each other, and **D6** is operator-owned and can run
alongside anything.

### D0 (P0, blocks everything, S) — measurement truth: keys ∩ index, and step-level diffs

**Build.** (i) `scoreboard.py`: for each family, compute `keys_present` — the labelled line's
`(host, source, line)` resolves in the run's *index* (`| tstats count … source=… ` or a first/last
window check) — and report per step `evidence_absent: n/N`, excluded from `keys_reachable`
denominator. (ii) Print a **step-set diff** against a named baseline run: `lost`, `gained`,
`reachable_lost`, `reachable_gained`. No ratio in the headline. (iii) `--baseline <run>` flag.
**Property.** A step whose evidence the index cannot contain is never counted as unreachable; a
regression is a list of step names.
**Live proof.** santos `_v2`: `crack_passwords evidence_absent 44/44`, step denominator 20; the
step diff against the control prints `loss: attacker_http, dirb, wpscan` /
`gain: attacker_change_user, exfiltration-service`. Same command on kyoushi and russell prints their
lists (§2.2).
**Test.** fixture keys with one line in a file the index lacks → `evidence_absent`, not `unreachable`.
**Why first.** Every other slice is scored by this, and it is the only defence against the next
false alarm.

### D1 (P0, M) — the read approximates a per-file read

**Build.** In `sample.py`/`behaviours.py`: keep every indexed source path with its count and host
(no 12/8 truncation); choose windows **per file** (or per `(file, host)`), issue one read per file
with its own `head`; budget per file = `min(per_window, ceil(share × source_budget))`. Emit one
ledger row and one receipt line per `(source_id, file, window)`, with `events_available` per file.
Keep a declared cap (`READ_FILES_MAX`) that, when hit, writes a ledger row per *omitted* file with a
reason.
**Property.** Every indexed file under a card's sourcetype is either read or has a ledger row saying
why not, and no file is sampled by arrival order alone.
**Live proof.** santos `_v2`: the read contains `source="/apache2/intranet.smith.santos.com-access.log"`
with ≥ 1,250 rows; the store holds ≥ 1,000 `intranet_server` access events; `attacker_http`, `dirb`,
`wpscan` become reachable (C0 ceiling 11 → 14). kyoushi store `intranet_server` ≥ 1,700 (control
parity); russell ≥ 725.
**Test.** 21-file fixture, labelled file rank 14 → routed and read; `head` pool fixture asserting
per-file counts are non-zero for every file.
**Cost.** Live evidence that per-file reads are cheaper *per read*: a single-file `head 1250` scans
2.8–3.2 k events in ≤ 0.8 s, where the pooled read scans 3.5 k and returns nothing from the wanted
file. **But the search count multiplies**: santos `access_combined` alone is 21 files × 14 windows =
294 searches against the 785 the entire `_v2` santos run issued. Allocate the *row* budget per file
so total rows stay at today's level, cap `files × windows` with `READ_FILES_MAX`, and report
`searches_by_stage` so the 720 s deadline is measured rather than hoped for. The wall cost is search
overhead, not scan volume.

### D2 (P0, M) — one field vocabulary: the estate's, joined to the parse

**Build.** In `inventory.py`: before a list is attempted, resolve `(sourcetype, field)` against the
**estate vocabulary** — `| tstats … by <f>` (one field), else `search … | head 1 | fields <f>` — and
select from `card roles ∪ structural parse fields ∪ indexed fields the probe proves`. A name that is
parse-local (`template`, `program`, `v1..v6` and any name no probe can see) must be labelled
`parse_only: true` and **never turned into a query**; it costs nothing and is not reported as
`empty`.
**Property.** Zero searches whose `by` clause names a parse-only field; a status of `empty` means
"present and 0 values", never "this name cannot exist".
**Live proof.** santos `_v2` inventory contains complete (`values > 0`, `mechanism: tstats`,
`events_scanned`, `seconds ≤ 5`) lists for `access_combined:c_ip` (18), `linux_audit:acct` (13),
`linux_audit:exe` (7), `suricata:fast:signature` (22); `stats`/`tstats by template|program|v*`
count = 0.
**Test.** a card whose roles are `v1..v6` and whose source exposes `c_ip/acct` → the exposed fields
are selected; a name that neither probe sees → `unavailable:<name>`, never `empty`.
**Cost (measured).** A field probe is ~0.5 s either way: `search … | head 1 | fields <f>` scans
51–57 events in 0.50–0.58 s, `| tstats count … by <f> | head 1` scanned a 567,569-event sourcetype in
0.63 s. Fifteen sources × three role fields ≈ 25 s, in place of 32 full scans with 20 guaranteed
empties.

### D3 (P1, S) — capped lists keep the tail

**Build.** `_values`: over `LIST_MAX`, keep per-host top-k plus the rarest values (and their
`first_seen`), status `capped` with `values` non-empty and `capped_share` reported.
**Property.** `status: capped` implies `values > 0`; the rarest decile is represented.
**Live proof.** santos `_v2`: `suricata:dns.rrname` `capped` with ≥ 500 values, including domains
whose index-wide count is 1–12; `dnsmasq:dns_query` likewise. (Expected cardinalities measured
live: 19,463 and 20,031.)
**Test.** 1,001-row fixture at `LIST_MAX=1000` → 1,000 kept, not 0.

### D4 (P0, M) — the spine types identities the estate actually uses

**Build.** `spine.py`: add a numeric identity class — a field named `uid`/`auid`/`gid`/`sid`/`euid`
(or a value that is an all-digit field inside those names) yields `user` entities; then, when the
same source carries `acct` for that id, record both. Also: a partitioned card's *part* is part of
the entity key so `event_type=dns` and `flow` never merge.
**Property.** An audit record whose only identity is numeric still carries an entity and lands in an
episode.
**Proof already run offline (§3.4).** Rebuilding the santos `_v2` spine under the change reproduces
the baseline exactly and then takes `verify_steps` from 9 of 11 read steps to **11 of 11** with
`lines_without_entity 0`; the control stays 12 of 12. The orchestrator's live proof is the same
rebuild on a fresh run: `python -m …hunt.notables.spine --out <run>/v2/santos --family santos
--keys …` → `steps_pass == steps_read`, `lines_without_entity 0`.
**Test.** the exact LOGIN line as a fixture → ≥ 1 entity.

### D5 (P0, S) — rung 1 fires

**Build.** `ACCEL_QUERY` → `title`/`id`; map `tstats:DM_Splunk_SA_CIM_<Model>` → `<Model>`; keep a
model only if its `summary.earliest/latest` covers the read window; use
`tstats summariesonly=true … from datamodel=<Model>` for localisation, and record
`mechanism: accelerated`, `scanCount`, `seconds`.
**Property.** `accelerated` is non-empty whenever a complete summary covers the window, and rung 1 is
chosen before rung 2 when it answers.
**Live proof.** santos `_v2`: `inventory.accelerated` = every complete model root (≥ 6), `model_probes > 0`, at least one
localisation receipt with `mechanism: accelerated` and `scanCount ≈ 0` in < 1 s; the same run's
CIM list `Authentication.user` (10 users incl. `gmorgan`) appears as a complete value list.
**Test.** fixture of the real endpoint payload (no `datamodel_name`) → models parsed.

### D6 (P1, S) — setup: route out the shipper copies, fix the `user` regex, add `auid`

**Build** (operator-owned, `scripts/lab/splunk_setup` + one reindex): add
`*/system.service.log`, `*/system.auth.log`, `*/system.syslog.log`, `*/system.journal*` to the noise
list (or give them their own `filebeat_system` sourcetype so `syslog`/`linux_secure` hold one shape);
make `ph_ix_linux_secure_user` JSON-safe (`for user ([A-Za-z0-9_.@-]+)`); add `ph_ix_linux_audit_auid`.
**Property.** A tuned index contains each event family once, one raw shape per sourcetype, and the
index-time `user`/`auid` are the field's real values.
**Live proof.** `| tstats count where index=hb_ait_santos_v2 by sourcetype` → `syslog` < 300 k, total
< 2.7 M; `| tstats count … linux_secure by user | where length(user) > 64` → 0; `… linux_audit by auid`
→ > 0 rows.
**Test.** the runbook's verify gains `service_log_absent`, `user_clean`, `auid_indexed` probes.

### D7 (P1, S) — the merge consumes the measured marginal

**Build.** `RUN_HUNT_REDESIGN.sh` (and any product job) runs the scoreboard's marginal pass first and
exports `PORTAL_HUNT_MERGE_WEIGHTS`; `merge.py` refuses to merge on defaults when a measured file is
present but unparsed (fail loud, not silent).
**Property.** `progress.json:stages.notables.merge.weights_source != "default"`; the head's
composition is reported beside each generator's `attribution@50`/`marginal@50`.
**Live proof.** re-run santos `_v2` with the exported weights → `weights_source: "measured"`,
`{deviation 9, similar_to_known 1, …}`, and a head whose top 50 is no longer 31/50 below-chance
label matches.
**Test.** env var round-trip; a missing key leaves `default` **and** writes a receipt note.

### D8 (P1, M) — cases lift verified members, and the singleton step finally has a route

**Build.** `relate.py`: promotion may only lift a member whose evidence resolves to ≥ 1 event and
whose carrier entity appears in the returned row (the deterministic check exists — make it a
precondition, not a post-hoc label); case recall credited strictly, never through a raw line.
Add the *set-novelty* signal the plan already specifies (`unit`, `systemd` unit names, file-extension
class sets) so a two-event step has a unit that can hold it.
**Property.** No promoted row is unjudged in a judged-only view; a case's members each verify.
**Live proof.** santos `_v2`: `promoted_unjudged = 0`; `case_member_recall @50 > 3/21`;
`exfiltration-service` (`type=SERVICE_START unit=ut`, 2 events on `internal_share`) appears as a
set-novelty candidate with a verifiable evidence query, or is explicitly reported as
`not_generically_surfaceable` with the reason.

### D9 (P2, S) — flows on the consolidated estate

**Build.** A flow is `(entity, host)` ordered across role-vector-different sources inside the
entity's own span; a value present in two sources with an identical raw digest is a *duplicate*, not
a flow.
**Property.** Duplicate-ingest pairs are never flows; at least one real ingress→execution pair exists
on a family where both endpoints were read.
**Live proof.** santos `_v2`: `flows > 0`, `flows_skipped` accounts for the rest, and at least one
flow's two endpoints are `access_combined`/`dnsmasq` → `linux_audit`/`linux_secure` on one host.
**Test.** `mail.info`/`mail.log` duplicate fixture → 0 flows; two-source ordered fixture → 1.

### D10 (P2, S) — S0 cause, delivered

**Build.** `scoreboard.py`: emit `C0 causes` for line-mode families too (`covered | instrument |
not_surfaced | unreached | censored`, derived from the per-step ledger read row); `run.py`: write the
`honesty` block into `progress.json` (it is `null` there for both santos runs today, so the
`weights_source`/knowledge facts exist only under `stages.notables.merge`).
**Property.** No family reports an empty cause; `progress.json:honesty` is never null when a run
exists.
**Live proof.** santos `_v2` score prints `C0 causes` with `unreached: crack_passwords (44/44 absent)`,
`censored: …`, `not_surfaced: attacker_change_user`.

### 5.1 Live proof ladder the orchestrator runs (in order)

```bash
# 0. images current, .env keys exported by name, PIPELINE_API_KEY present
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261121
keys_s=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl

# 1. D0 offline: keys ∩ index + step diff (no Splunk, no judge)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out <run>/v2/santos --keys santos=$keys_s --weights --json \
  --baseline <run>/control/santos
# pass: prints step sets and `evidence_absent`; crack_passwords absent 44/44; no ratio in the headline

# 2. D1/D2/D5 on the tuned santos index (cards + behaviours + notables; judge off)
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out <run>/v2/santos --stage behaviours --family santos
# pass: receipt lists every access_combined file with its own events_read; inventory shows
#       access_combined:c_ip=18 complete, linux_audit:acct=13 complete, accelerated ≥6 model roots,
#       zero `by template|program|v*` searches, `capped` list with values > 0

# 3. the same for kyoushi and russell, then the scoreboard
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out <run> --keys kyoushi=… --keys santos=$keys_s --keys russell=… --baseline <control run>
# pass: reachable ⊇ control (kyoushi 11, santos 12, russell 15) and covered@50 ⊇ control's set;
#       `evidence_absent` lists crack_passwords 44/44 on santos; lost = [] for all three
```

---

## 6. What I did not do / what is still unproven

- **No re-run of the pipeline.** Every `_v2`-vs-control comparison above is a re-score of the stored
  runs plus read-only Splunk probes, and the slice proofs in §5 are commands and expected shapes
  unless a slice says otherwise. **D4 is the exception and it is verified**: its spine rebuild was
  run against a hardlinked copy of the stored store (§3.4), reproducing the baseline before the
  change. D1/D2/D5/D7 need a real read and have only query-level evidence.
- **The D1 counterfactual is proved per query, not end-to-end.** I showed the single-file read
  returns 1,250 rows where the pooled read returns 0–313 and that the file holds 87 % attacker
  traffic; I did not rebuild a store with the fixed route and re-score it. The projected ceiling
  (11 → 14 on santos) is arithmetic on labelled-line counts plus the current `first_rank` values,
  i.e. [reasoned], and it depends on D8 for the three steps that stay uncovered at @50.
- **`botsv2` was not run this round, but I did measure its exposure.** 4 of its 104 sourcetypes
  exceed eight files — `pan:traffic` 32 files / 1,883,556 events, `winhostmon` 9 / 3,413,063,
  `pan:system` 32 / 40,073, `ms:o365:management` 15 / 4,480 [live
  `| tstats count where index=botsv2 by sourcetype source | stats dc(source) as files sum(count) as
  events by sourcetype | where files > 8`]. **No botsv2 graded key's locator names any of them**
  (the 34 keys are entity keys on `stream:*`, Windows and Suricata), so botsv2 would not currently
  score the defect either way — it is structurally exposed but not a measuring instrument for it.
  Correctness of the D1 fix on a wide estate therefore remains unproven.
- **The `linux_secure` regex defect is measured on the index, not reproduced from the app tree at
  HEAD.** I read `transforms.conf` in the repo and observed the corrupted values live; I did not
  check whether a `local/transforms.conf` override is present on the box (the runbook says one may
  be).
- **`exfiltration-service` may not be generically surfaceable.** Two `type=SERVICE_START/STOP
  unit=ut` events with no observable link to exfiltration, on the one host the scenario uses. D8's
  set-novelty signal is the best available route; if it fails, the honest outcome is a label-quality
  note, not a code change. Do not tune to it.
- **The 41.5 % duplicate-service figure is one index.** kyoushi/russell were not measured for the
  same class (their `system.service.log` volumes were not queried).
- **Ranker quality beyond step coverage was not judged.** `case_quality`, case purity and judge
  ordering are reported by the scoreboard and not assessed here.

---

## 7. Files touched

- `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` — this document.
- `coding_task/scratch/deepdive2/` — `spl.py` (read-only Splunk job client), `diag_spine.py`
  (re-derives the spine's typing per run), `routes.py` (labelled-file vs read-route ranking), the
  six score JSON/txt files, `spine-v2-patched/` (hardlinked copy of the stored store used to rebuild
  the spine under the D4 hypothesis). Scratch only, gitignored.

No production code was changed: the brief asks for the diagnosis and the replan, and the code
changes belong to the lanes that farm §5.

---

## 8. Reproduce

```bash
cd /Users/chris/projects/portal-5-orcacyber-deep-dive-2
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700
s=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
k=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl
r=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl

for f in "v2/santos santos $s" "control/santos santos $s" \
         "v2/kyoushi kyoushi $k" "control/kyoushi kyoushi $k" \
         "v2/russell russell $r" "control/russell russell $r"; do
  set -- $f
  uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
    --out "$run/$1" --keys "$2=$3" --json > "coding_task/scratch/deepdive2/$2-$(dirname $1).json"
done

uv run python coding_task/scratch/deepdive2/routes.py        # labelled file vs the 8-file route
uv run python coding_task/scratch/deepdive2/diag_spine.py v2 # per-line entity typing
uv run python coding_task/scratch/deepdive2/diag_spine.py control
```

---

## 9. Receipts (commands actually run this session)

All Splunk reads: job API, basic auth, credentials read from the live checkout's `.env` by key name
(never sourced), `verify=False`, training indexes only. Every row below names its query and the
server's own `scanCount`/`runDuration` where relevant.

```spl
# --- estate map of the tuned santos index
| tstats count where index=hb_ait_santos_v2 by sourcetype                      -- 14 rows
| tstats count where index=hb_ait_santos_v2 sourcetype=access_combined by source
    -> 21 rows; /apache2/intranet.smith.santos.com-access.log = 9,462, rank 14 by count
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_secure by source   -- 14 rows, 9,864 ev
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_audit  by source   -- 1 row, 24,042 ev

# --- the file the attack lives in (counterfactual for RC1)
| tstats count where index=hb_ait_santos_v2 sourcetype=access_combined
    source="/apache2/intranet.smith.santos.com-access.log" by c_ip
    -> 172.21.128.119 = 8,254 of 9,462   (scan 9,462, 0.35 s)
search index=hb_ait_russellmitchell_v2 (source="/horde/horde-access.log" OR …eight names…) | head 1250
    -> mail 620, webserver 618, davey_mail 12, intranet_server 0   (scan 3,481, 0.47 s)
search index=hb_ait_russellmitchell_v2 source="…/intranet.smith.russellmitchell.com-access.log.2"
  | head 1250
    -> 1,250 rows   (scan 2,792, 0.50 s)
search index=hb_ait_santos_v2   source="…/intranet.smith.santos.com-access.log" | head 1250  -> 1,250
search index=hb_kyoushi_s1_v2   source="…/intranet.company.cyberrange.at-access.log.4" | head 1250 -> 1,250

# --- the estate's field vocabulary, all tstats, all ≤ 0.4 s (RC2)
| tstats dc(c_ip)         as values where index=hb_ait_santos_v2 sourcetype=access_combined      -> 18
| tstats dc(cs_uri_stem)  as values where index=hb_ait_santos_v2 sourcetype=access_combined      -> 13963
| tstats dc(vhost)        as values where index=hb_ait_santos_v2 sourcetype=access_combined      -> 1
| tstats dc(acct)         as values where index=hb_ait_santos_v2 sourcetype=linux_audit          -> 13
| tstats dc(exe)          as values where index=hb_ait_santos_v2 sourcetype=linux_audit          -> 7
| tstats dc(signature)    as values where index=hb_ait_santos_v2 sourcetype=suricata:fast        -> 22
| tstats dc(dns.rrname)   as values where index=hb_ait_santos_v2 sourcetype=suricata event_type=dns -> 19463
| tstats dc(dns_query)    as values where index=hb_ait_santos_v2 sourcetype=dnsmasq             -> 20031
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_audit by auid                      -> 0 rows
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_audit by acct  | sort -count|head   -> root 7577 …

# --- acceleration is live; the hunt's probe cannot see it (RC7)
| rest /services/admin/summarization by_tstats=1 | eval model=title
  | table model summary.complete summary.size summary.earliest_time summary.latest_time
    -> 6 models complete=1; Network_Resolution 72,630,272; earliest 1616425561 latest 1643094189
| rest /services/admin/summarization by_tstats=1 | head 5    (fields: no `datamodel_name`)
| tstats summariesonly=true count from datamodel=Authentication by Authentication.user
    -> 10 real users, scan 7,287, 0.58 s
| tstats summariesonly=true count from datamodel=Web by Web.http_method
    -> GET 10,564 / POST 6,892 / OPTIONS 12 / unknown 161, 0.17 s

# --- the keys/`_v2` mismatch (RC3)
| tstats count where index=hb_ait_santos     source="*2022-01-17-system.cpu.log"   -> 3,840
| tstats count where index=hb_ait_santos_v2  source="*2022-01-17-system.cpu.log"   -> 0
| tstats count where index=hb_ait_santos_v2  source="*system.service.log"          -> 1,856,634
| eventcount summarize=false index=hb_ait_santos_v2  -> 4,474,600
| eventcount summarize=false index=hb_ait_santos     -> 25,143,873

# --- the wide corpus's structural exposure to the same route cap (RC1, §6)
| tstats count where index=botsv2 by sourcetype source
  | stats dc(source) as files sum(count) as events by sourcetype | where files > 8 | sort - events
    -> pan:traffic 32 files/1,883,556 ev; winhostmon 9/3,413,063; pan:system 32/40,073;
       ms:o365:management 15/4,480   (scan 226,317,740, 9.1 s)

# --- the linux_secure `user` corruption (RC10)
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_secure by user
    -> values like 'ait","@version":"1","log":{"offset":110323,…
| tstats count … sourcetype=linux_secure by source user | eval ulen=length(user)
  | where ulen > 64 | stats sum(count) by source
    -> 12 logstash paths, 1,090 events
```

Offline:

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out <run>/<fl>/<fam> \
  --keys <fam>=<keys> [--json]            # six runs, §2.1
uv run python coding_task/scratch/deepdive2/routes.py      # §3.1(a)
uv run python coding_task/scratch/deepdive2/diag_spine.py v2|control   # §3.4

# D4 proof: rebuild the spine on a hardlinked copy, baseline then patched (writes only under scratch)
d=coding_task/scratch/deepdive2/spine-v2-patched
ln <run>/v2/santos/{behaviours.duckdb,sources.json,progress.json} $d/
uv run python - <<'PY'
import sys; sys.path.insert(0,'.')
from pathlib import Path
import portal.modules.security.core.hunt.notables.spine as S
out=Path('coding_task/scratch/deepdive2/spine-v2-patched')
print(S.spine_from_store(out)['events_without_entity'])          # 3351, matches the stored receipt
S._USER_FIELDS |= {"uid","auid","gid","euid","sid"}
print(S.spine_from_store(out)['events_without_entity'])          # 2958
PY
```

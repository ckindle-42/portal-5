# Splunk realism and setup — what the lab is, what a real SOC is, and what the hunt may assume

Round 2 of the OrcaCyber hunt lane, 2026-11-20. Reads first: `ORCACYBER_CODE_REVIEW.md` (the
code-and-live walk of the build) and `ORCACYBER_HUNT_PLAN.md` (the rebuild plan whose one open
question was whether the hunt may use full-index search-time `stats`, index-time extraction or
`tstats` only).

The operator's answer was: *"tstats is preferred, but we need what will work, not what is the
easiest… it also means we need to improve our stock Splunk setup to be more tuned to a real setup
so it's accurate."* This document answers that with measurement: what the lab Splunk is, how far
it is from a well-run SOC, what the tuning would cost, and what the hunt may therefore assume.

**All Splunk access was read-only, training indexes only** (`botsv2`, `hb_kyoushi_s1`,
`hb_ait_santos`, `hb_ait_russellmitchell`). No configuration was changed. Held-out indexes
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never queried. Credentials were exported by
name from the live checkout's `.env` (`LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`, `LAB_SPLUNK_PASSWORD`);
the file was never sourced. Every number below carries its command in §9.

---

## 0. The answer in one page

1. **`tstats` is the only mechanism the hunt may *rely* on, and today it can see exactly one
   field: `host`.** Across the four training indexes, 59 of 59 probes of a role field
   (`user`, `src`, `dest`, `EventCode`, `uri`, `http_method`, `src_ip`, `alert.signature`,
   `event_type`, `Image`, `CommandLine`, `app`, `action`, `exe`, `uid`, `comm`, `query`,
   `program`, `unit`, …) returned **0 rows** to `| tstats … by <field>`. 5 of 5 probes of `host`
   returned rows. The only fields in the tsidx are `index`, `host`, `source`, `sourcetype` and
   the `date_*`/`punct`/`linecount` defaults (§2.6).
2. **Everything else is a scan, and a scan is priced in events, not queries.** Measured on this
   VM: ~30 k events/s on the botsv2 Windows/stream data, ~220 k events/s on the AIT `eve.json`
   streams. So a full-index search-time `stats` costs **~2 h for botsv2** (226.3 M events),
   **~2 min for one AIT family whole** (24.5 M), **~11 s for the AIT huntable volume** (≈2.5 M,
   excluding `stats.log`). One `tstats` aggregate over the same index: **1–3 s** (§3).
3. **A real, well-run SOC has four things the lab mostly lacks**: a TA per sourcetype (so the
   fields exist at all), CIM tags (so the models populate), 4–8 accelerated data models over a
   rolling window (so `tstats … from datamodel=` is the default fast path), and tiered retention
   with high-volume noise routed out of the security indexes. The lab has: 69 apps, most vendor
   TAs installed and **disabled**; CIM 8.6.0 with 36 data models, **zero accelerated**, tags
   reaching **one of four corpora and only some models** (`Authentication`/`Web`/
   `Intrusion_Detection` populate on botsv2; `Network_Traffic`/`Endpoint.Processes` are empty;
   the AIT families have no tags at all); `summary` index empty; and the training data indexed
   under ad-hoc, per-day or channel-qualified sourcetypes that no TA binds to (§2, §4).
4. **Cost of closing the gap is small in compute and large in one decision.** CIM-normalised
   acceleration over the security-relevant volume is ~10 min of scan per full backfill on this VM
   and ~100–300 MB of summary (assumption, §5.3); the expensive part is that CIM normalisation
   needs the sourcetypes fixed, and **that needs a reindex** (§5.1), which is the operator's call.
   Index-time extraction is the only thing that makes `tstats` see entities on the *current*
   corpora, and it also needs a reindex and roughly doubles tsidx (§5.4).
5. **The consequence for the hunt is a rule, not a threshold**: full-index `stats` is affordable
   on a build family and not on a wide corpus; and before any read the hunt must probe three
   things — *which access path the field supports*, *which name the source has on that path*, and
   *whether the time range is inside an acceleration window*. Today all three failures are a
   silent empty result (§6).
6. **Two defects found while measuring, both silent, both outside the code review:**
   - The same BOTS v2 Windows events have **two sourcetype names** — `WinEventLog` on the
     raw/search path, `wineventlog:security` on the tsidx/`tstats` path — and each path accepts
     only its own. `search … sourcetype="wineventlog:security" | stats count` returns **0 events**
     after scanning 2,152,467; `| tstats … sourcetype="WinEventLog" by host` returns **0 rows**.
     The stored cards on `botsv2` carry the *tstats* name (`wineventlog:security`,
     `snap_neon_02cc2e3/sources.json`), so a C1 fix that swaps `tstats` for `stats` while keeping
     the card's sourcetype **returns a silent zero** (§4.2).
   - The hunt's REST read accumulates Splunk's **preview** rows (partial aggregates) alongside
     the final rows, so one large aggregate can arrive 2–3× with partial values (§2.8). Measured
     directly: a `| tstats count … by sourcetype` on botsv2 came back as 307 rows for 104
     sourcetypes, and the row sums exceeded the index total by 3×.
   - **Both silent-zero modes cost a full scan to discover.** A group-by on a wrong *name* cost
     67.8 s and a 2.15 M-event scan; a group-by on a wrong *field* cost 57.6 s and a 2.18 M-event
     scan. Neither raises an error; both look like "no data" in a receipt (§4.2).
7. **The honest position on an unseen customer index**: assume `tstats` on `host`/`source`/
   `sourcetype`; assume vendor TAs provide *search-time* fields (names vendor-specific, not CIM);
   assume CIM acceleration may exist for a handful of models over a recent window only; assume
   index-time extraction almost never exists. Everything else must be probed and receipted (§6).

---

## 1. Method

- Endpoint `https://10.0.1.30:8089`, Splunk Enterprise **10.2.5**, basic auth — the same
  credentials and host the code uses (`portal/modules/security/core/siem/spl_backend.py:80-120`).
- Inventory via REST: `/services/apps/local`, `/services/datamodel/model`,
  `/services/admin/summarization`, `/services/data/indexes`, `/servicesNS/-/-/configs/conf-{props,
  transforms,fields,indexes,sourcetypes}`, `/services/server/info`, `/services/server/status/
  resource-usage/hostwide`, `/services/search/jobs`.
- Searches via **job API** (`POST /services/search/jobs` then read the job's `content`), because
  it reports `scanCount` (events read), `runDuration`, `isFailed`, and `messages` — an export
  request reports none of these and silently returns partial rows. See §2.8 for why that matters.
- All timing is **wall clock on the client** and **`runDuration` on the server**, both reported.
  The VM was idle throughout (`cpu_idle_pct 88`, load 0.19): one measurement at a time.
- **Disclosure on the held-out sets.** Two estate-wide inventory queries were run before the
  training filters were applied: `| tstats count where index=* by index` (12 rows: one count per
  index) and `| tstats count where index=* by index sourcetype` (826 rows: name + count per pair),
  plus `| dbinspect index=*` (bucket count and size per index). Those rows name `botsv1`,
  `hb_ait_wheeler` and `hb_cloudobs_aws` and give their **counts/sizes only**. No event, field
  value, key or document from a held-out index was read or queried, and no constant, timing or
  decision in this document uses their counts. Every other query is scoped to the four training
  indexes.

---

## 2. The lab Splunk as it stands

### 2.1 Server

Splunk 10.2.5, Linux (Proxmox VM), **14 cores / 20 vCPU, 96 GB RAM (66 GB used), x86_64**.
Selected REST facts: `mem 96290.172` MB, `cpu_count 14`, `virtual_cpu_count 20`,
`normalized_load_avg_1min 0.19`, `cpu_idle_pct 88.36`.
No search-affecting errors in `/services/messages` (a `Splunk_TA_nessus` modular-input init
failure, a KV-store 4.2 upgrade warning, an empty `allowedDomainList` warning).

### 2.2 Apps and technology add-ons — 69 installed

The vendor fleet is *present* and mostly *not doing anything* for the training data:

| app | version | label | enabled |
|---|---|---|---|
| Splunk_SA_CIM | 8.6.0 | Common Information Model | yes |
| Splunk_Security_Essentials | 3.8.3 | Security Essentials | yes |
| DA-ESS-ContentUpdate | 6.2.0 | ES Content Updates | yes |
| Splunk_TA_windows | 10.1.2 | Microsoft Windows add-on | **no** |
| TA-microsoft-sysmon | 10.6.2 | Sysmon add-on | **no** |
| Splunk_TA_nix | 10.3.1 | Unix/Linux add-on | yes |
| Splunk_TA_paloalto | 8.1.3 | Palo Alto add-on | yes |
| Splunk_TA_aws | 8.2.0 | AWS add-on | yes |
| TA-MS-AAD / splunk_ta_o365 / TA-MS_O365_Reporting | 4.2.0 / 6.0.2 / 2.0.1 | cloud identity | yes |
| Splunk_TA_apache, Splunk_TA_microsoft-iis, Splunk_TA_cisco-asa, Splunk_TA_fortinet_fortigate, Splunk_TA_symantec-ep, TA-suricata-4 | 3.0.0, 2.0.0, 6.1.1, 1.6.10, 4.0.0, 2.3.4 | — | **no** |
| splunk_app_stream, splunk_app_osquery, utbox, jellyfisher, SA-cim_vladiator | 8.1.6, 0.6.0, 1.9.4, 1.0.1, 2.1 | — | yes (vladiator) / no |

No `SplunkEnterpriseSecuritySuite` (ES itself) — only the ES content-update app. So there is no
ES correlation layer, no ES asset/identity store, no ES notable index.

**Which of this binds to the training data: none.** The TAs key on their own sourcetypes
(`WinEventLog:Security`, `XmlWinEventLog:Microsoft-Windows-Sysmon/Operational`, `linux_secure`,
`auditd`, `suricata`, `pan:traffic`). The training indexes carry `WinEventLog`,
`wineventlog:security`, `xmlwineventlog:microsoft-windows-sysmon/operational`, and on the AIT
families per-day file names (§2.5). Two concrete mismatches, both fatal to extraction:

- The **AIT families' `eve.json`** (Suricata) is not the TA's sourcetype, and `TA-suricata-4` is
  disabled, so `event_type`, `src_ip`, `alert.signature` are not extracted — while the same keys
  in `botsv2`'s `suricata` sourcetype *are* (that app is enabled and its `props` stanza has
  `KV_MODE=json`).
- The **BOTS v2 Windows events** are matched by `botsv2_data_set`'s own 813-stanza `props.conf`
  (EVAL/REPORT/FIELDALIAS for `WinEventLog`, `WinRegistry`, `WinHostMon`), i.e. by a *dataset app*,
  on the raw path's name — not by the Windows TA, and not on the tsidx path (§4.2).

### 2.3 CIM and data models — installed, partly populated, never accelerated

`Splunk_SA_CIM` 8.6.0 is enabled; 36 data models exist: `Alerts`, `Application_State`,
`Authentication`, `Certificates`, `Change`, `Change_Analysis`, `Compute_Inventory`, `Data_Access`,
`Databases`, `DLP`, `Email`, `Endpoint`, `Event_Signatures`, `Interprocess_Messaging`,
`Intrusion_Detection`, `JVM`, `Malware`, `Network_Resolution`, `Network_Sessions`,
`Network_Traffic`, `Performance`, `Splunk_Audit`, `Splunk_CIM_Validation`, `Ticket_Management`,
`Updates`, `Vulnerabilities`, `Web`, plus internal Splunk models.

- **Acceleration: 0 of 36.** Every model's `acceleration.enabled` is `false`.
- `/services/admin/summarization` returns exactly one stale pro-job entry
  (`sid:…_splunk_app_stream…`), i.e. no model has a built summary.
- `| tstats summariesonly=true count from datamodel=Authentication by Authentication.user`
  → **0 rows in 0.12 s** (and the same for `Web`), which is what "no summary exists" looks like.
- **The models do populate — but only on `botsv2`, and only as a scan.** `botsv2_data_set` ships
  the Windows TA's `props` *and* the CIM tag assignments, so one day of that index answers the
  canonical accelerated question in 4.3 s:
  `| tstats count from datamodel=Authentication by Authentication.user` over one day → 10 users
  (`Administrator` 628, `ANONYMOUS LOGON` 28 …), **4.3 s, 37,134 events scanned**; the tag search
  behind it returns 31,352 `tag=authentication` events and 10,238 `tag=web` events in that day.
  Over the whole 451-day index the same query is a scan: **killed at 180.9 s**, 3.77 M events read,
  nothing returned.
- **On the AIT families the models are empty**, because nothing assigns a tag: a sample of
  `2022-01-14-system.auth.log`, `eve.json`, `auth.log` and `eve.json` carries only JSON/KV keys
  (`src_ip`, `event_type`, `uid`) — no `user`, no `src`, no `tag` (measured with `| fields *`).
- `summary` index: exists, **0 events**. No summary indexing, no report acceleration in use.

So CIM is one third of the way there: normalised and tagged on one corpus, empty on three, and
unaccelerated everywhere. That is a *realistic* enterprise state, and a better one to build
against than a clean sheet — but it means the fast path exists on exactly the corpus the hunt is
measured on, which would flatter any score unless the degradation is exercised on the families.

### 2.4 Indexes — sizing, retention, span

| index | events | size (MB) | buckets | retention | `maxTotalDataSizeMB` | span |
|---|---:|---:|---:|---|---:|---|
| botsv2 | 226,337,781 | 23,538 | 59 | 36,525 d (100 y) | 500,000 | 2017-08-01 → 2018-10-29 |
| hb_kyoushi_s1 | 24,504,858 | 985 | 3 | 3,650 d | 20,000 | 2021-03-22 → (2026 bucket end) |
| hb_ait_santos | 25,143,873 | 1,311 | 3 | 3,650 d | 20,000 | 2022-01 |
| hb_ait_russellmitchell | 25,522,335 | 1,369 | 3 | 3,650 d | 20,000 | 2022-01 |
| portal5_lab (not a training set) | 17,786,835 | 3,939 | 13 | 2,184 d | 500,000 | — |
| labelled_corpus (not a training set) | 8,877,181 | 4,686 | 9 | 7,300 d | 500,000 | — |

Two realism notes that matter to a hunter:

- **Retention is effectively infinite everywhere** (`100 y` on botsv2, `10 y` on the families,
  against 451 days and 10 days of actual data). Nothing was ever frozen; `dbinspect` shows 59 live
  buckets for botsv2 and 3 for each family. A real deployment's hot/warm window is 30–90 days and
  the rest is frozen or archived — which decides whether a hunt's time range is even readable.
- **The AIT families are ~85 % noise.** `stats.log` alone is 22.0 M of kyoushi's 24.5 M (90 %),
  20.4 M of santos's 25.1 M (81 %), 21.0 M of russell's 25.5 M (82 %). BOTS v2 is ~89 %
  perfmon/mysql/collectd/registry (`winregistry` 55.5 M, `perfmon:process` 49.3 M, the two mysql
  transaction sourcetypes 53.7 M, `collectd` 22.4 M). A real SOC routes that class to a metrics
  index or drops it; here it inflates every "events available" number the hunt reads
  (`index_facts`) by 4–10×, which is exactly the number the read budget is divided by.

### 2.5 Sourcetypes — the lab's biggest structural gap

`botsv2`: **104** sourcetypes, headed by `winregistry` 55.5 M, `perfmon:process` 49.3 M,
`mysql:server:stats` 26.9 M, `mysql:transaction:details` 26.8 M, `collectd` 22.4 M,
`mysql:variables` 4.1 M, `winhostmon` 3.4 M, `perfmon:logicaldisk` 3.05 M, `mysql:status` 2.87 M,
`perfmon:physicaldisk` 2.51 M, `stream:ip` 2.47 M, `wineventlog:security` 2.18 M, `suricata`
2.16 M, `perfmon:memory` 2.15 M, `stream:tcp` 2.06 M, `perfmon:cpu` 2.03 M, `pan:traffic` 1.88 M,
`access_combined` 1.71 M, `stream:http` 1.42 M, `stream:dns` 1.19 M,
`xmlwineventlog:microsoft-windows-sysmon/operational` 1.11 M, … then 84 small ones
(`linux_audit` 457 k, `auditd` 453 k, `linux_secure` 310 k, `osquery_results` 47.9 k …).

`hb_kyoushi_s1`: **36** sourcetypes — `stats.log` 22.0 M, `eve.json` 1.03 M, `dnsmasq.log` 427 k,
four access logs 0.4–0.07 M, `syslog` 56.6 k, `system.journal.txt` 39 k, `audit.log` 25 k,
`mainlog` 23.7 k, `fast.log` 15 k, `auth.log` 9.0 k, `suricata.log` 6.1 k, `openvpn.log` 4.1 k.

`hb_ait_santos`: **126** sourcetypes; `hb_ait_russellmitchell`: **127**. Beyond `stats.log` /
`eve.json` / `dnsmasq.log` / `horde-access.log` / `fast.log` / `suricata.log` / `audit.log`, the
bulk are **per-day file names**: `2022-01-14-system.service.log`, `2022-01-15-system.cpu.log`,
`logstash-plain-2022-01-17-1.log`, `2022-01-13-system.auth.log`, …

Why this is the central realism failure: **a real SOC has one sourcetype per data type** — 10–30
per index — because the sourcetype is the contract that binds a TA, a `props` stanza, a CIM tag
and a data model. Here the AIT families have 126/127 sourcetypes where a real Linux estate would
have ~10 (`linux_secure`, `linux_audit`, `syslog`, `access_combined`, `apache:error`,
`suricata:eve`, `ossec`, `postfix_syslog`, `dhcpd`…), and 89 of each family's 126/127 are a *date in a filename*.
Consequences, in order of cost:

1. No TA matches → no `FIELDALIAS`/`EVAL`/`LOOKUP` → no CIM field names (`user`, `src`, `dest`,
   `action`, `dvc`) → `| tstats … from datamodel=` can never populate.
2. A card per day-file, not per data type: the estate map multiplies a source by its days
   (a 5-day campaign becomes 5 "sources"), and the read budget is divided by that inflated count.
3. `sourcetype` can no longer be used as a selection predicate in a hunt query — so the read path
   falls back to `source=` predicates (which is what `sample.py:243-256` already does), and
   `tstats`, which has no `source=` fast path for most questions, is unusable on those sources.

### 2.6 Indexed vs search-time fields — measured, and decisive

The config is as bare as it can be. `conf-fields` (32 stanzas) marks only defaults as indexed:
`host`, `source`, `sourcetype`, `index`, `_sourcetype`, `_indextime`, `date_*`, `punct`,
`linecount`, `splunk_server`. **Not** `user`, `src`, `dest`, `EventCode`, `Image`, `uri`,
`action`, `query`, `uid`, `exe`. `conf-props` has `INDEXED_EXTRACTIONS` for 42 sourcetypes
(`_json`, `aws:*`, `iis`, csv/TSV metrics, `dsappevent`…) — **none of them a training sourcetype**.
So no training index has index-time extraction of anything.

Confirmed behaviourally, 64 probes, each one query
`| tstats count where index=<I> sourcetype="<S>" by <field>`:

| index | probes | returned rows | fields that worked |
|---|---:|---:|---|
| botsv2 | 24 | 0 | — (none, not even `host`, when the name was `WinEventLog` — §4.2) |
| hb_kyoushi_s1 | 14 | 1 | `host` |
| hb_ait_santos | 13 | 2 | `host` |
| hb_ait_russellmitchell | 13 | 2 | `host` |

**59 of 59 role-field probes returned zero rows; 5 of 5 `host` probes returned rows.** Fields
probed and empty: `user`, `src`, `dest`, `EventCode`, `http_method`, `cs_method`, `uri`, `status`,
`src_ip`, `dest_ip`, `alert.signature`, `event_type`, `Image`, `CommandLine`, `app`, `action`,
`exe`, `comm`, `uid`, `query`, `program`, `pid`, `unit`, `columns.cmdline`, `process_image`.

One behaviour of `tstats` the fix must respect: **one non-indexed field in the `by` list zeroes
the whole group-by.** `by http_method cs_method uri status host` → 0 rows, while `by host` → 7
rows on the same sourcetype — so a multi-field query cannot tell you *which* field failed, and a
receipt that reports "empty" cannot either. `tstats`' value filter is exact and case-insensitive
(`sourcetype=stream:htp` → 0; `sourcetype=WinRegistry` == `sourcetype=winregistry`), which is how
the name mismatch in §4.2 stays invisible.

A related trap: `| walklex index=X type=field` **is not a field inventory** on this instance. It
returns 2,581 "field" rows for botsv2 — high-frequency *terms* (`2001:428:3801:207`,
`/libhtp`) alongside the real field names, which appear space-prefixed (`' host'`, `' source'`).
A lane that inventories indexed fields with `walklex` will believe it has hundreds of fields when
it has nine. The per-field `tstats … by <field>` probe is the only reliable check, which is what
the 64 probes above are.

Search-time extraction *does* work where the raw is KV or JSON: `stream:http`'s JSON keys
(`accept`) and `linux_audit`'s KV pairs (`uid`, `acct`, `exe`, `addr`) extract normally. On
botsv2's Windows data it is TA-grade: a single `WinEventLog` event exposes `user`, `Account_Name`,
`src`, `src_ip`, `dest`, `dest_nt_host`, `dvc`, `signature`, `action`, `app`, `category`,
`vendor_product` and `tag` at search time (`| … | head 1 | fields *`), because
`botsv2_data_set` ships the Windows TA's props. **None of those is in the tsidx** — so the same
field is free on the raw path and invisible to `tstats`. On the AIT families the search-time
fields are only the JSON/KV keys: `eve.json` has `src_ip`/`event_type`/`dest_ip`, and
`auth.log` extracts `uid` and nothing else.

The gap is not "Splunk cannot extract", it is "nothing tells Splunk what this data is, nothing
tags it into CIM, and nothing puts the result where `tstats` can see it".

### 2.7 props / transforms of note

- 887 `props` stanzas, 1,713 `transforms`, all from the installed apps; **no lab-authored stanza
  for any training index**. There is no `TRANSFORMS-*` routing for the AIT per-day names, no
  `REPORT-*` extraction for them, no `fields.conf` `INDEXED=true` anywhere custom.
- `botsv2_data_set` ships the full Windows TA stanza set *as dataset config*: e.g.
  `[WinEventLog]` with `EVAL-process_name`, `[WinRegistry]` with `FIELDALIAS-dest_for_WinRegistry`,
  `[source::WinEventLog:Security]` with `EVAL-Error_Code`. This is why BOTS v2 has rich
  search-time fields and no tsidx fields: the extraction lives on the raw path only.
- The 61 `TRANSFORMS` stanzas that exist are TA plumbing (PAN sourcetype routing, WinEvent host
  overrides, `force_sourcetype_for_cisco_asa`, metric-store collection). None applies to a
  training sourcetype.
- `AUTO_KV_JSON=1` on all 887 stanzas; `KV_MODE` mostly unset (`auto`), 89 `none`, 76 `json`.

### 2.8 A read-path defect found while measuring (not fixed — out of scope this round)

Splunk's `search/jobs/export` streams **preview** rows (partial aggregates) before the final
result set. `_iter_json_objects` + `_run_search`
(`portal/modules/security/core/siem/spl_backend.py:38-124`) keep **every** object that has a
`result` key, so a streaming aggregate is accumulated 2–3× with partial values. Measured:

```
| tstats count where index=botsv2 by sourcetype        -> 307 rows for 104 sourcetypes
                                                          sums to 331,063,473 vs 226,317,740 events
# same query, keeping only {"preview": false} rows     -> 104 rows, sums to 226,317,740
```

The same run-to-run instability (207 rows, then 307 rows) is the giveaway: preview count depends
on timing. Any hunt number that came from an aggregate response — card `events`, `index_facts`,
`| stats` value lists, `tstats` per-source counts — can be inflated and is not reproducible.
`executor.py` does not filter previews either; the fix is one condition
(`obj.get("preview") is False`) in the JSON-object iterator, plus a unit test with a recorded
export body. **This is a correctness bug independent of the Splunk tuning and it should be fixed
in S0, before any of the setup work is used as evidence.**

---

## 3. Speed on this hardware: the same question four ways

The question is the one C1 asks — *"enumerate the values of one evidentiary field with events,
hosts, first and last seen"* — asked four ways per index on that index's primary detection
stream. Both `wall` (client) and `runDuration` (server) are given; `scan` is events read
according to the job record (candidate events read, which for a scan exceeds the matches).

| index | (a) `tstats` on the default indexed field | (b) `tstats` from a data model | (c) full-index search-time `stats` | (d) localised `stats` (tstats first, then the slice) |
|---|---|---|---|---|
| **botsv2** (226.3 M) | `by host` → 23 rows, **3.0 s** / scan 226.3 M | **not accelerated**: `summariesonly=true` → 0 rows in **0.12 s**; unaccelerated `Authentication` whole index → 2,592,516 in **199.9 s** (scan 4.28 M); `Endpoint.Processes` and `Network_Traffic` → **0 rows in 240 s each** | `sourcetype="WinEventLog"` by `user` → 57 rows, **72.8 s** / scan 2.18 M | `host=mercury` (73 % of the source) → 53 rows, **55.6 s**; **one day** → 38 rows, **3.1 s** / scan 57.5 k |
| **hb_kyoushi_s1** (24.5 M) | `by host` → 17 rows, **1.0 s** / scan 24.5 M | 0 rows in **0.1 s** (no tags at all) | `eve.json` by `src_ip` → 100 rows, **5.1 s** / scan 1.03 M | `eve.json` one 1-h window → 39 rows, **1.0 s** / scan 1,540 |
| **hb_ait_santos** (25.1 M) | `by host` → 16 rows, **1.0 s** / scan 25.1 M | 0 rows in **0.1 s** | `eve.json` by `src_ip` → 100 rows, **5.1 s** / scan 1.13 M | a 1-h window is 1/120 of a 5-day corpus → **<1 s** |
| **hb_ait_russellmitchell** (25.5 M) | `by host` → 16 rows, **1.0 s** / scan 25.5 M | 0 rows in **0.1 s** | `eve.json` by `src_ip` → 100 rows, **5.1 s** / scan 1.12 M | as above |

Supporting numbers, same session:

| measurement | result | what it prices |
|---|---|---|
| `search index=botsv2 sourcetype=stream:http \| stats count` | **50.5 s**, 1,408,636 scanned | raw scan of the stream data: **27.9 k events/s** |
| `search index=botsv2 sourcetype="WinEventLog" \| stats count by host` | **58.3 s**, 2,182,877 scanned | Windows/KV scan: **37.4 k events/s** |
| `search index=botsv2 sourcetype="WinEventLog" \| stats … by user` | 57 rows in **72.8 s** | a *successful* full-index value list |
| same query, `by "Account Name"` (field that does not exist) | **0 rows in 57.6 s**, 2,182,877 scanned | a paid-for empty gate |
| same query with `sourcetype="wineventlog:security"` (name the raw path rejects) | **0 events in 67.8 s**, 2,152,467 scanned | a paid-for empty gate |
| unaccelerated `tstats from datamodel=Authentication`, whole index | 2,592,516 in **199.9 s** (scan 4.28 M) | CIM without acceleration: **21 k events/s** |
| unaccelerated `tstats from datamodel=Network_Traffic` / `Endpoint.Processes` | **0 rows in 239.8 s / 239.9 s** (scan 8.3 M / 34.4 M) | an *empty* model costs 4 min to discover |
| `tstats from datamodel=Authentication` over **one day** | 10 users in **4.3 s** (scan 37.1 k) | the same model, time-localised: 46× cheaper |
| `search … sourcetype=linux_audit \| stats … by exe` (botsv2, 455 k) | 5 rows in **10.1 s** | the cheap tier that works today |
| the three AIT `eve.json` full-index enumerations | 1.03–1.13 M in **4.6–4.8 s** | JSON-over-3-buckets: **217–240 k events/s** |
| `search … sourcetype=winregistry` **one day** | 60 rows in **6.1 s** (scan 1.46 M) | the 55.5 M source: ≈**46 min** for the whole index (extrapolated) |
| `\| eventcount summarize=false index=…` | **0.03–0.16 s**, no scan | the honest way to ask "events available" |

Two readings of the same table:

- **Localisation works, and it works by time, not by host.** Restricting to the busiest host saved
  24 % on `WinEventLog` (55.6 s vs 72.8 s) because the `host` in the tsidx is the collector, not
  the endpoint; restricting to one day saved 96 % (3.1 s). A read policy that localises by host
  will under-deliver on Windows data; one that localises by time span (from `tstats … by _time
  span=`) delivers linearly.
- **Acceleration is the only thing that changes the order of magnitude.** Unaccelerated, the CIM
  path costs as much as a raw scan (21 k events/s) and an *empty* model costs 4 minutes to
  discover; accelerated, the same question is the 0.1 s line.

**What the table means for a budget.** A 30-second query budget — the hunt's current
`query_seconds` (`executor.py:27`) — can read at most ~0.9 M botsv2 events, i.e. **0.4 % of the
index and less than half of one security sourcetype**. The 720-second job deadline
(`job_seconds`, `executor.py:28`) buys ~22 M events at 30 k/s: 10 % of botsv2, but ~90 % of an
entire AIT family. On the wide corpus the current budgets are not "a bit tight"; they are one to
two orders of magnitude short of a full-index question, which is exactly why C1 at 32 searches
was always going to be a sample even if the mechanism had worked.

---

## 4. Gap analysis against a well-run SOC

### 4.1 Item by item

| # | Real SOC | This lab | Effect on what a hunt can see |
|---|---|---|---|
| 1 | One sourcetype per data type, set by a TA/intermediate forwarder | AIT families: 126/127 sourcetypes, 89 of them a date in a filename; botsv2 Windows events share `WinEventLog` with no channel in the raw path | Sourcetype cannot select a data type; cards multiply per day-file; read budget divided by inflated source count; no TA binds |
| 2 | Vendor TA enabled per sourcetype, supplying `FIELDALIAS`/`EVAL`/`REPORT` → CIM names | TAs installed, most **disabled**, none bound to the training sourcetypes; only `botsv2_data_set`'s own copy binds (raw path), so botsv2 gets TA-grade fields (`user`, `src`, `dest`, `Account_Name`, `tag`) and the AIT families get only JSON/KV keys | Field *names* are per-corpus and unknowable in advance; on the AIT families there are no CIM names at all |
| 3 | CIM tags populated by the TAs; `cim_vladiator` reports high coverage | CIM 8.6.0 installed. Tags reach **botsv2 only**, and partially: `Authentication` 2.59 M events, `Web` 0.50 M, `Intrusion_Detection` 13.5 k — but **`Network_Traffic` and `Endpoint.Processes` are empty** despite pan/stream/sysmon data being present. The AIT families have **no tags at all** | `tstats from datamodel=` works on one of four corpora and on a subset of models; discovering an empty model costs 240 s of scan |
| 4 | 4–8 data models accelerated over a rolling window (30–90 d) | **0 of 36 accelerated**, `summary` index empty | The one mechanism that makes entity-level `tstats` cheap does not exist |
| 5 | Index-time extraction only where a TA needs it (JSON/W3C/Windows XML); rare elsewhere | **None** on any training sourcetype; only defaults are `INDEXED=1` | `tstats` sees `host` and nothing else: "a needle is a value in a list" has no cheap implementation |
| 6 | Retention tiered by value: 30–90 d hot, then frozen/archived; noise routed out or dropped | 100-year/10-year retention on everything; ~85 % of each AIT family is `stats.log`, ~75 % of botsv2 is perfmon/mysql/collectd | "Events available" overstates the huntable estate 4–10×; the budget is divided by noise |
| 7 | Summary indexing / report acceleration for recurring aggregates | `summary` index exists with 0 events | No reusable per-entity state across runs; every run re-scans |
| 8 | ES correlation, notable store, asset/identity context | ES content app only; no ES | The estate's own detections are (as the code review found) `activity` cards, not an alert stream |
| 9 | Documented field dictionary and CIM compliance per source | None | A hunter (or the model) must learn field names from the data — which the card mechanism already does, and which is the one realistic behaviour to keep |

### 4.2 The C1 finding as the worked example

C1's claim was *"a needle only has to be a value in a list"*: enumerate each card's role-field
values index-wide with `tstats`, then treat an unseen value as a candidate. On `botsv2` it
returned **0 values, 0 joints, 0 flows** in 16 s. The code review attributed that to search-time
fields being unaggregatable. That is true and it is §2.6. But there is a **second, independent
cause on the same index**, found this round, and it would survive fixing the first:

```
# the card's sourcetype is the tstats name (snap_neon_02cc2e3/sources.json: "wineventlog:security")
| tstats count where index=botsv2 sourcetype="wineventlog:security" by host   ->  9 rows   (tsidx name)
search index=botsv2 sourcetype="wineventlog:security" | stats count          ->  0 events, 2,152,467 scanned
search index=botsv2 sourcetype="WinEventLog" | stats count by host           ->  2,182,877 events   (raw name)
| tstats count where index=botsv2 sourcetype="WinEventLog" by host           ->  0 rows
```

The same events, two names, and each access path accepts only its own:

- `tstats` groups by the **tsidx** value — lowercase and channel-qualified — so the raw search
  path's `WinEventLog` is not a valid `tstats` filter (0 rows).
- the raw search path matches the **event** value — `WinEventLog` — so the card's
  `wineventlog:security` matches nothing (0 events, and it costs a 2.15 M-event scan to find out).

Consequences:

1. **A mechanism swap alone does not fix C1.** "`stats` instead of `tstats`" with the card's
   sourcetype returns a silent zero on every BOTS Windows source. The S1 mechanism probe must
   probe the **name**, not just the field.
2. **`empty` in a receipt cannot be trusted.** 57.6 s of scanning produced `rows=0` for a
   group-by on a field name that does not exist, and 67.8 s produced `0 events` for a sourcetype
   name the raw path rejects. Both are indistinguishable from "this source has no data", which is
   why the review's §2.1 point — statuses must separate `unavailable:<reason>` from `empty` — is a
   correctness requirement, not a nicety. The correct field name is `user`
   (`Account_Name`, `src`, `dest`, `tag` are also present search-time); nothing about the raw event
   tells you which of the two names is the tsidx one.
3. **A real SOC would not have this specific split** (its TAs set the sourcetype once, the same
   name in tsidx and event), but a customer index *can* have a stale or renamed sourcetype — the
   generic lesson stands: one source may answer to different names on different paths.

The same question on a deployment that has TA + CIM + acceleration would be
`| tstats summariesonly=true count from datamodel=Authentication by Authentication.user, Authentication.src`
over the accelerated window: one aggregate, seconds, no extraction cost, every field in the model.
That is the mechanism the hunt was designed around; the lab never had it.

### 4.3 What a hunter can rely on in a customer environment

| assumption | how safe | what to do when it fails |
|---|---|---|
| `tstats` works on `index`, `host`, `source`, `sourcetype` | **near-certain** (defaults everywhere) | nothing to do; this is the floor |
| vendor TA extraction gives search-time fields | **likely**, but names are vendor-native, not CIM | read field names from a sample; never hard-code `user`/`src` |
| CIM tags + models exist | **hit and miss, and per-model**: here `Authentication`/`Web`/`Intrusion_Detection` populate, `Network_Traffic`/`Endpoint.Processes` are empty, on the same index | probe `summariesonly=true` (0.1 s) then a **one-day** `summariesonly=false` (4 s) — never the whole index (240 s); treat 0 rows as "absent", not "empty" |
| data models accelerated for the asked range | **usually yes for a few models, no for history** | declare the accelerated window in the receipt; the remainder is a scan |
| entity fields in the tsidx (`user`, `src`, `dest`, `file_path`) | **rare outside JSON/W3C/Windows-XML TAs** | fall back to search-time `stats` with an events budget |
| summary indexing / report acceleration exists | **sometimes** | never assume; a missing summary must be a fallback, not a failure |
| retention covers the asked range | **yes inside hot, no beyond** | `| metadata`/`dbinspect` first, and say so when the range is partly frozen |
| the estate's own alerts are in a notable/alert stream | **likely in ES shops, no here** | discover detection-shaped sources structurally (S4) |

---

## 5. Target setup, staged, with cost

The order is forced: **sourcetype → TA → tags → acceleration → (optionally) index-time
extraction**. Accelerating before step 1–2 builds empty summaries; that is the mistake the lab
is one config away from repeating.

### 5.1 Stage 1 — normalise the sourcetypes (needs a reindex)

Make the sourcetype mean "data type", not "file that arrived today". Two ways; the first is the
one a SOC actually uses.

- **Preferred (reindex):** set the sourcetype at ingest/forwarder level and re-index from the
  source corpora in `/Volumes/data01/portal5_hunt/corpora/` with an explicit `sourcetype=`
  per input. Then the AIT families become ~10 sourcetypes each.
- **If a reindex is refused (props rename, no reindex):** `props.conf` `TRANSFORMS-<name>` with
  `DEST_KEY = _MetaData:Sourcetype` and a `REGEX` on `source` for the dated names. This fixes the
  *event* name only — it does **not** repair the tsidx name (which is written at index time), so
  `tstats` still needs a name mapping (below). Budget it as a stop-gap.

Mapping (measured sourcetypes → target):

| current | target sourcetype | note |
|---|---|---|
| `2022-01-xx-system.auth.log`, `auth.log` | `linux_secure` | sshd/sudo auth |
| `audit.log`, `linux_audit` | `linux_audit` | auditd |
| `2022-01-xx-system.service.log`, `system.journal.txt`, `messages`, `syslog`, `kern.log`, `user.log` | `syslog` (or `journald`) | |
| `*access.log`, `other_vhosts_access.log`, `horde-access.log`, `access_combined` | `access_combined` | Apache/nginx/horde |
| `error.log`, `apache_error` | `apache:error` | |
| `eve.json` | `suricata` (or `suricata:eve`) | TA-suricata-4 exists; enable it |
| `fast.log` | `suricata:fast` | |
| `dnsmasq.log` | `dnsmasq` | DNS; no vendor TA is installed, so its CIM fields need a small `REPORT` stanza |
| `mail.log`/`mail.info`/`mainlog` | `postfix_syslog` | |
| `openvpn.log` | `openvpn` | |
| `stats.log` | `cyberrange:stats` **routed to a metrics index or dropped** | 81–90 % of each family; not security telemetry |
| `WinEventLog` (botsv2) | `WinEventLog:Security` / `:Application` / `:System` / `:Directory-Service` by channel | channel is recoverable from `_raw` |
| `wineventlog:security` (tsidx) | ditto | requires the reindex to change the tsidx key |
| `xmlwineventlog:microsoft-windows-sysmon/operational` | keep, enable TA-microsoft-sysmon | its `props` stanza is CamelCase |

Cost: reindex = delete + re-ingest of 23.5 GB (botsv2) + 3.7 GB (three families) from the source
corpora. At the measured raw *read* rate (~30 k events/s) a from-scratch reindex of botsv2 is
~2 h of scan plus write; in practice expect 3–5 h. **This is an estimate, not a measurement** —
the lab has never reindexed. The families alone are 15 min each.

### 5.2 Stage 2 — enable the TAs and let CIM populate

Enable: `Splunk_TA_windows`, `TA-microsoft-sysmon`, `TA-suricata-4`, `Splunk_TA_nix`,
`Splunk_TA_apache`, `Splunk_TA_paloalto`, `Splunk_TA_aws` (already on). Keep
`Splunk_TA_nessus`'s failing modular input disabled or fixed; it is noise in `/services/messages`.

Verification is not optional, because a TA that is enabled but whose sourcetype does not match
silently does nothing:

```
| tstats count where index=hb_ait_santos by sourcetype                  # names as the TA sees them
| datamodel Authentication objects                                      # the model's objects
| tstats count from datamodel=Authentication where index=hb_ait_santos  # one day, not the whole index
|cim_vladiator  (app SA-cim_vladiator is installed)                     # per-model coverage
```

Expected outcome on the AIT families: `Authentication` from `linux_secure`/`linux_audit`,
`Endpoint.Processes`/`Filesystem` from `linux_audit`, `Web` from `access_combined`,
`Network_Traffic` from `suricata`/proxy logs, `Network_Resolution` from `dnsmasq`,
`Intrusion_Detection` from `suricata:fast`. On botsv2: `Authentication` from `WinEventLog:Security`
(4624/4625), `Endpoint` from Sysmon, `Network_Traffic`/`Web` from `pan:traffic`/`stream:*`,
`Intrusion_Detection` from `suricata`.

### 5.3 Stage 3 — accelerate a small, named set of models over a stated window

Accelerate only what a hunt needs to aggregate *by entity*:

| model | objects | source volume (botsv2) | source volume (per AIT family) |
|---|---|---|---|
| `Authentication` | Authentication | 2.18 M (winsec) + 0.46 M (linux_audit) + 0.31 M (linux_secure) + 0.45 M (auditd) | ~0.04 M |
| `Endpoint` | Processes, Filesystem, Registry | 1.11 M (sysmon) + winsec 4688 subset; **registry 55.5 M if included** | ~0.03 M |
| `Network_Traffic` | All_Traffic | 1.88 M (pan) + 2.47 M (stream:ip) + 2.06 M (stream:tcp) ≈ 6.4 M | ~1.2 M (eve) |
| `Web` | Web | 1.42 M (stream:http) + 1.71 M (access_combined) ≈ 3.1 M | ~0.5 M |
| `Network_Resolution` | DNS | 1.19 M (stream:dns) | ~0.43 M (dnsmasq) |
| `Intrusion_Detection` | IDS_Attacks | 2.16 M (suricata) + pan:threat | ~0.02 M (fast.log) |
| `Change` | All_Changes | 55.5 M (winregistry) — **expensive; accelerate last or not at all** | ~0 |

Build cost, from the measured scan rates (a build is one search per model over its events):
**≈19 M events → ~10 min** for the six cheap models on botsv2 at 31 k events/s; add ~30 min if
`Change`/winregistry is included. The AIT families are ~2 M events each → **~10 s each**.

Summary size: rule of thumb **5–15 % of the source volume** (state it as an assumption; it is
verified after the build, not before). For ~19 M botsv2 events at ~104 B/event compressed
(23.5 GB / 226 M), that is 100–300 MB of summary against a 23.5 GB index.

**Window.** `earliest_time` in each model's stanza decides how much history is searchable from
summaries. A SOC sets `-30d`/`-90d`; a hunt over these corpora needs the whole span, so either
`earliest_time = -451d` (botsv2) / `-10y` (families) or the hunt must accept that older events
are a scan. The hunt must record which window it got (§6, rule 4).

### 5.4 Stage 4 — index-time extraction, only if `tstats` on entities is required today

This is the only change that makes `tstats` see entity values **on the existing corpus**, and it
requires a reindex (`fields.conf`/`props` `INDEXED_VALUE` apply at index time). Minimum useful
set, per sourcetype class:

| class | fields to index | why |
|---|---|---|
| Windows security | `EventCode`, `Account_Name`, `Logon_Account`, `Source_Network_Address`, `ComputerName` | auth entity + outcome |
| Sysmon / Windows XML | `EventCode`, `Image`, `ParentImage`, `CommandLine`, `User`, `TargetFilename`, `QueryName` | process/file/DNS spine |
| Linux auditd / secure | `exe`, `comm`, `uid`, `acct`, `addr`, `terminal` | exec + auth spine |
| Access logs | `cs_method`, `cs_uri_stem`, `c_ip`, `sc_status`, `cs_user_agent` | web |
| Suricata / Eve | `event_type`, `src_ip`, `dest_ip`, `alert.signature`, `dns.rrname`, `http.url` | IDS + flows |
| Proxy / PAN | `src`, `dest`, `app`, `action`, `url` | egress |

Cost: index-time extraction grows tsidx roughly in proportion to the number and cardinality of the
fields; for this field set expect **+40–100 % index size** (estimate — must be measured on one
sourcetype before committing botsv2), plus the reindex. `tstats` then answers entity questions in
1–3 s across the whole index, and every C1/S1/S6 design becomes a 2-second aggregate instead of a
2-hour scan. **This is the single highest-leverage change for the hunt's ceiling** and the most
expensive in ops.

### 5.5 Stage 5 — sizing, retention, noise

- Route/`stats.log` and `perfmon:*`/`mysql:*`/`collectd` out of the hunt's indexes (metrics index
  or drop). Effect: "events available" drops to the honest huntable number (botsv2 ≈ 20 M, AIT
  ≈ 2.5–4.7 M), and every per-source budget stops being divided by noise.
- Set retention to the evaluation's needs (botsv2 451 d, families 10 d) rather than 100 y, so
  `dbinspect`/`metadata` agree with reality and frozen ranges are visible rather than silent.
- Raise `maxTotalDataSizeMB` on the families only if a reindex will grow them (20 GB cap against
  ~1.4 GB used is currently a non-issue but will bite if `Change`/`Endpoint` duplication grows).

### 5.6 Stage 6 — summary indexing for the hunt's own recurring state

Once Stage 1–3 exist, add **one** scheduled search per training index that writes the hunt's
per-entity first-seen/counts to the (currently empty) `summary` index:

```
index=X sourcetype=... | stats count dc(host) as hosts min(_time) as first max(_time) as last by <entity field>
  | collect index=summary marker="hunt_entities:index:X"
```

Then "has this host ever run this before" is a `tstats` over `summary` instead of a fresh scan,
and the inventory survives across runs. Cost: one scan per day (≈2 min for an AIT family, 2 h for
botsv2 — so schedule botsv2 once, not daily). Do this **after** Stage 1–3; on today's data it
would summarise noise and per-day sourcetypes.

---

## 6. Rules the hunt must follow

These are the conditions for an honest run on an index the tool has never seen. Each one exists
because its absence produced a measured silent zero this round.

1. **Probe the name before the field.** For each `(index, sourcetype)` the card names, run one
   `| tstats count where index=I sourcetype="S"` **and** one `search index=I sourcetype="S" | head 1`.
   Record both; if they disagree, the source has two names and every later query must pick the
   right one for its path. (botsv2 today: `tstats` accepts `wineventlog:security`, raw accepts
   `WinEventLog`.)
2. **Probe fields one at a time.** `tstats` zeroes the whole group-by if any `by` field is not in
   the tsidx, so a multi-field probe cannot attribute the failure. One query per field, cached per
   `(index, sourcetype, field)`, with the answer recorded as `indexed` / `not-indexed`.
3. **Never report `empty` for `unavailable`.** Three distinct states: `empty` (mechanism worked,
   no values), `unavailable:<mechanism>` (the field is not aggregatable), `unavailable:<name>`
   (the source does not answer to that name on this path). A hunt score that cannot tell them
   apart is a hunt that reports a broken probe as a clean negative — C1's 32 "empty" fields were
   one broken mechanism and 32 constants.
4. **Declare the acceleration window in every receipt.** `tstats summariesonly=true` outside the
   window returns nothing; `summariesonly=false` is a scan. The receipt carries
   `accel_window: [start, end] | none` and the searched range, so a partial-coverage read is
   visibly partial.
5. **Budget in events scanned, not queries or seconds.** Measured: ~30 k events/s (botsv2
   Windows/stream), ~220 k events/s (AIT JSON), ~21 k events/s unaccelerated CIM. A 30-second
   `query_seconds` cap silently censors anything over ~0.9 M botsv2 events; state per-read
   `events_scanned` and let the scorer see the fraction of the source.
6. **Full-index `stats` is for a family, not a corpus.** It is ~11 s on an AIT family's huntable
   volume and ~2 h on botsv2. Any list over a >10 M-event source must be localised first
   (`tstats by host`/`by _time span` → read the slice) or replaced by an accelerated aggregate.
7. **Use `| eventcount` for "events available".** 0.03 s, no scan, exact — instead of a count
   search, and instead of trusting a sampled `index_facts` count.
8. **Learn field names per source; never assume CIM names.** On a customer index the TA is
   vendor-native (`Account_Name`, `cs_uri_stem`, `New_Process_Name`), and on this lab's BOTS data
   the names are the dataset's own. The card mechanism already does this; keep it.
9. **Classify noise structurally, not by name.** `stats.log`/perfmon/mysql are "measurement"
   cards by volume, cadence and numeric share; excluding them by sourcetype first character or by
   a hard-coded name is a corpus-specific cheat.
10. **A detection stream is found structurally** (JSON `event_type=alert`, Suricata fast-log
    shape, signature+severity+src/dest) — never by sourcetype name, and never by requiring an
    `action` field (that is the S4 fix the code review already specifies).

---

## 7. Revised plan: S1, S6, the time budget, and what can start now

### 7.1 Which slices depend on the Splunk changes

| slice | depends on Stage 1–3 (setup)? | can start now? | what changes with the setup |
|---|---|---|---|
| S0 truthful measurement + preview fix | no | **yes** | none; the preview fix is a prerequisite for every number (§2.8) |
| S5 marginal weights | no | **yes** (stored runs) | none |
| S4 estate detections | partly (TA enables Suricata/eve fields) | **yes** | on botsv2 `suricata` already has JSON fields; on the AIT families `eve.json` needs TA-suricata enabled or search-time `spath` |
| S2 spine/episodes | no for building; Stage 4 for `tstats` joins | **yes** on stored stores | with Stage 4 the spine can be *derived* by aggregate instead of by scan |
| S1 enumeration | **yes for the wide corpus**; no for a family | **yes, scoped** | becomes 32 × 2 s aggregates instead of 32 × minutes-to-hours scans |
| S6 localise-then-read | partly (acceleration makes localisation cheap) | **yes, scoped** | `tstats from datamodel` replaces `tstats by host` as the localiser |
| S3 cases/promotion | no (operates on S1/S2 output) | **yes** | case recall improves with the spine, not with the Splunk config |
| S7 judge over cases | no | **yes** | none |

### 7.2 S1 — enumeration that works (revised)

The acceptance in the plan ("≥ 1 complete list whose values are parse-derived role values on
botsv2; `first_seen_replaced > 0`") is **not achievable on botsv2 today** — not because of the
field mechanism, but because a list over 2.15 M Windows events costs 68 s and every role field is
search-time. Restate it as two tiers:

- **Tier A (achievable now).** On `botsv2`, a complete list over `linux_audit.exe` (457 k events,
  ≲15 s) or `stream:http.accept` (1.42 M, ≲50 s); on an AIT family, `eve.json.src_ip` (1.13 M,
  5 s). Prove: `values > 0`, `status: complete`, `first_seen_replaced > 0` for at least one
  behaviour, and the query is `stats` (not `tstats`) with a recorded `events_scanned`.
- **Tier B (needs Stage 3 or 4).** A complete list over a *wide* source (`wineventlog:security`,
  `winregistry`) in ≤5 s, via `tstats from datamodel=…` or `tstats by <indexed entity>`.
- **New mechanism requirements** (each is a unit test):
  1. name probe per `(index, sourcetype)` with both paths, cached, and `unavailable:<name>` when
     the chosen path rejects the card's name;
  2. one field per probe query (never a multi-field `by` for the probe);
  3. status vocabulary `complete | capped | unavailable:<mechanism> | unavailable:<name>`, and
     `empty` only when the mechanism is proven to work on that source;
  4. mechanism chosen per field by the probe (`tstats` if `indexed`, else `stats`), with the
     events budget attached to the `stats` route;
  5. the receipt carries `events_scanned`, `mechanism`, `name_used`, `accel_window`.
- **Regression test for §2.8:** the response parser drops `preview:true` objects; a recorded
  307-line export body must yield 104 rows.

### 7.3 S6 — localise-then-read (revised)

The read policy changes from "cadence ladder over equal slices" to a **three-rung ladder**, each
rung guarded by a probe:

1. **Accelerated aggregate** (if a model covers the source and the range): `tstats
   summariesonly=true … from datamodel=…` → seconds, whole range. Record `accel_window`.
2. **Indexed-field aggregate**: `tstats … by host, _time span=<width>` on the default fields →
   1–3 s. This yields *where* and *when*, never *who*.
3. **Narrowed scan**: `search` restricted by the host and the window rung 2 produced, with a
   declared events cap; `stats` for the value list. Measured: a 1-h `eve.json` window is ~1/10 of
   the 5 s full read; a single-host Windows slice is ~70 % of the full sourcetype (host pruning
   is weak on `WinEventLog`, because the host in the tsidx is the *collector*, not the endpoint).

Explicit non-goals: no whole-read tier on a source above ~10 M events (it is a 5-minute read);
no per-day sourcetype treated as its own source once Stage 1 lands.

Acceptance changes accordingly: `keys_reachable ≥ 12/24` on botsv2 is **conditional on Stage 3
or 4**; before that, the honest target is the current 8/24 with the *cause* recorded per key
(`unreached` vs `censored` vs `name_mismatch`), and no build-family regression.

### 7.4 The time budget (replaces "30 s per query")

| budget | today | measured meaning | proposed |
|---|---|---|---|
| `query_seconds` | 30 s | 0.9 M botsv2 events ≈ 0.4 % of the index | keep as a *safety* cap; add `query_events` |
| `query_events` | — | — | 250 k (botsv2-class), 2 M (JSON/accelerated) per query |
| `job_seconds` | 720 s | 22 M events at 30 k/s = 10 % of botsv2, 90 % of an AIT family | 720 s on a family; 1800 s for a wide-corpus run (an explicit, declared difference) |
| `requests` | 2000 | — | unchanged, but 32 enumeration searches must not be able to eat the budget before any evidence read: reserve ≥50 % for evidence |
| per-run read fraction | undeclared | botsv2 0.118 % | must be declared per source and per run, and must rise to ≥1 % on the sources that carry candidates |

The one number that must not be tuned: the **read fraction is reported, not raised** to hit a
recall target.

### 7.5 Revised slice order

```
now:        S0 (preview fix + instrument)  →  S5 (marginal weights)  →  S4 (detections)
parallel:   S2 on stored stores            →  S1 Tier A (family + cheap botsv2 lists)
                                             →  S3 cases on family output
blocked on setup: S1 Tier B, S6 rung 1, the botsv2 12/24 acceptance
after setup: S2 re-derivation by aggregate, S6 full ladder, S7 judge over cases
```

Nothing in the first row needs a Splunk change, and nothing in the last row is meaningful before
Stage 1–3.

---

## 8. Decisions needed from the operator

1. **Reindex the corpora to normalise sourcetypes (Stage 1)?** This gates Stage 2–3 and therefore
   the whole CIM/acceleration path. It is a delete-and-reingest of 27 GB from the corpora in
   `/Volumes/data01/portal5_hunt`. Without it, CIM stays empty and no data model can be accelerated
   into anything but a full scan.
2. **Index-time extraction on the entity fields (Stage 4)?** It is the only change that makes
   `tstats` see entities on today's corpus, and it too needs a reindex. Cost estimate: +40–100 %
   tsidx (to be measured on one sourcetype first).
3. **Acceleration scope and window (Stage 3):** which models, and does acceleration cover the
   whole corpus span (`-451d` botsv2, `-10y` families) or a rolling window with the history left
   as a scan? A hunt over 2017–2018 botsv2 needs the former.
4. **Keep one untuned index as the degradation control?** If every training index is tuned, the
   tool's honest-failure path (missing TA, missing acceleration, `unavailable` statuses) stops
   being exercised. Recommendation: tune the families, keep `botsv2` untuned until S1 Tier B is
   proven on a tuned index, then mirror it.
5. **Which deployment is the pass bar?** "Works on a well-run SOC" and "works on this lab today"
   are different claims; the plan's §5 bar measures the former, and the current lab cannot host
   it until Stage 1–3 land.

Until 1–3 are decided, the build lanes can proceed on S0/S5/S4/S2/S3 and on S1 Tier A, which is
where the reachability win actually is today.

---

## 9. Receipts

All commands read-only, training indexes only, credentials exported by name from
`/Users/chris/projects/portal-5/.env` (`LAB_SPLUNK_URL`, `LAB_SPLUNK_USER`,
`LAB_SPLUNK_PASSWORD`; never sourced). Helper: `coding_task/scratch/spl.py` (job API + REST;
drops `preview:true` rows). Artifacts in `coding_task/scratch/inv/`.

```bash
# inventory
curl -sk -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" "$LAB_SPLUNK_URL/services/apps/local?output_mode=json&count=0"
curl … /services/datamodel/model                     # 36 models, acceleration.enabled=false on all
curl … /services/admin/summarization                 # one stale stream pro-job, no model summaries
curl … /services/data/indexes                        # sizes, retention, caps (§2.4)
curl … /servicesNS/-/-/configs/conf-fields           # only defaults INDEXED=1
| tstats count where index=* by index                # 12 indexes (inventory only)
| tstats count where index=* by index sourcetype     # 826 (index, sourcetype) pairs
| dbinspect index=* | stats count sum(sizeOnDiskMB) by index
| walklex index=botsv2 type=field                    # lexicon, not a field list — see §2.6 note
| metadata type=sourcetypes index=botsv2             # event-path names (WinEventLog, WinRegistry…)

# field probes (64, one query each)
| tstats count where index=botsv2 sourcetype="wineventlog:security" by user      -> 0 rows
| tstats count where index=botsv2 sourcetype="stream:http" by http_method        -> 0 rows
| tstats count where index=botsv2 sourcetype="stream:http" by host               -> 7 rows
| tstats count where index=hb_ait_santos sourcetype="eve.json" by src_ip         -> 0 rows
| tstats count where index=hb_ait_santos sourcetype="eve.json" by host           -> rows

# the two names for one source (botsv2 Windows)
| tstats count where index=botsv2 sourcetype="wineventlog:security" by host      -> 9 rows
search index=botsv2 sourcetype="wineventlog:security" | stats count              -> 0 (scan 2,152,467, 30.3 s)
search index=botsv2 sourcetype="WinEventLog" | stats count by host               -> 2,182,877 (58.3 s)
| tstats count where index=botsv2 sourcetype="WinEventLog" by host               -> 0 rows

# timing (job API: runDuration, scanCount, isFailed, messages)
| tstats count where index=botsv2 by host                                        -> 23 rows, 2.1 s
search index=botsv2 sourcetype=stream:http | stats count                         -> 50.5 s (1.41 M scanned)
search index=botsv2 sourcetype="WinEventLog" | stats … by user                    -> 57 rows, 72.8 s (2.18 M)
search index=botsv2 sourcetype="WinEventLog" host=mercury | stats … by user       -> 53 rows, 55.6 s (1.59 M)
search index=botsv2 sourcetype="WinEventLog" earliest=1501545600 latest=1501632000
  | stats … by user                                                              -> 38 rows, 3.1 s (57.5 k)
search index=botsv2 sourcetype="WinEventLog" | stats … by "Account Name"          -> 0 rows, 57.6 s (2.18 M)
search index=botsv2 sourcetype=linux_audit | stats … by exe                       -> 5 rows, 10.1 s (455 k)
search index=hb_kyoushi_s1 sourcetype=eve.json | stats … by src_ip                -> 100 rows, 5.1 s (1.03 M)
search index=hb_kyoushi_s1 sourcetype=eve.json earliest=1616889600 latest=1616893200
  | stats … by src_ip                                                            -> 39 rows, 1.0 s (1,540)
search index=botsv2 sourcetype=winregistry earliest=1501545600 latest=1501632000
  | stats … by process_image                                                     -> 60 rows, 6.1 s (1.46 M)
| tstats summariesonly=true count from datamodel=Authentication by Authentication.user -> 0 rows, 0.12 s
| tstats count from datamodel=Authentication                                      -> 2,592,516 in 199.9 s
| tstats count from datamodel=Authentication (one day)                            -> 10 users, 4.3 s (37.1 k)
| tstats count from datamodel=Web                                                 -> 495,712 in 24.8 s
| tstats count from datamodel=Intrusion_Detection                                 -> 13,507 in 9.4 s
| tstats count from datamodel=Network_Traffic                                     -> 0 rows, 239.8 s (8.3 M)
| tstats count from datamodel=Endpoint.Processes                                  -> 0 rows, 239.9 s (34.4 M)
| eventcount summarize=false index=botsv2                                          -> 226,337,781 in 0.16 s

# read-path preview duplication (§2.8)
| tstats count where index=botsv2 by sourcetype   # export body: 205 preview + 104 final rows
                                                  # naive accumulation -> 307 rows / 331 M events
```

---

## 10. Unproven / limits

- **No Splunk configuration was changed**, so every "after Stage N" number is an estimate:
  acceleration summary size (5–15 % assumption), reindex duration (3–5 h estimate from the
  measured read rate), index-time-extraction tsidx growth (+40–100 % estimate). Each has the
  command that will replace it after the first build (`/services/admin/summarization` for
  `summary_size`, `dbinspect` for bucket sizes).
- **`| metadata type=sourcetypes` and `tstats … by sourcetype` disagree on botsv2 Windows names.**
  I demonstrated the disagreement and its operational effect; I did not find the config stanza
  that creates the tsidx name (`botsv2_data_set` ships 813 `props` stanzas and the dataset was
  indexed off-cluster, so the ingest-time sourcetype is not visible in the current config).
- **One timing per cell.** Each number is a single run on an idle VM; run-to-run variance was not
  measured (the preview-row instability is a separate, client-side effect now filtered).
- **`winregistry` (55.5 M) was priced per day and extrapolated**, not run whole; the extrapolation
  is labelled where used.
- **The AIT families' 220 k events/s** is measured only on `eve.json` (3 buckets); a source spread
  over many buckets (botsv2 has 59) is 7× slower per event, so the rate is not portable across
  bucket layouts.
- **No customer index was available.** §4.3's "what a hunter can rely on" is reasoned from the
  lab plus standard Splunk deployment practice, not measured on a customer estate.
- **The hunt was not re-run** (no code changes this round); S1/S6 revisions are design, and their
  acceptance is unproven until a lane builds them.
- **The two defects this document reports are not fixed**: the `preview:true` accumulation in
  `siem/spl_backend.py` and the absence of a name probe in `inventory.py`. Code changes were out
  of scope for this round; both are specified as S0/S1 work in `ORCACYBER_HUNT_PLAN.md`, and every
  stored number that came from an aggregate stays suspect until the first is fixed.

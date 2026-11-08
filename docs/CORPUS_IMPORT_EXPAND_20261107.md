# Corpus import expand — measured 2026-11-07

Lane: `corpus-import-expand`. Question: is there additive labelled attack telemetry to bring in,
and can it be indexed as a separate, droppable evaluation corpus?

Summary: the only source with material missing from this lab is the anchor source itself,
`splunk/attack_data`. The pin was 85 days behind upstream; upstream carries 47 manifest-bearing
episodes (10 technique IDs) this tree did not have. Those 46 labelled episodes (3,170 events) are
now in a new index, `attack_data_refresh_20261107`. No other surveyed source cleared the bar.

All numbers below were measured on 2026-11-07 from the local trees, the live Splunk REST API and
the live index. Nothing here is a test result standing in for a measurement.

## 1. What is missing from the sources we already have

Local pins versus upstream heads:

| Source | Local commit | Upstream head | Drift |
|---|---|---|---|
| `splunk/attack_data` | `4145e8b60fd8` (2026-08-10) | `c8af10d015d3` (2026-11-03) | **119 files added, 2 removed; 47 new episodes** |
| `OTRF/Security-Datasets` (Mordor) | `d9d40ef123d2` (2023-09-20) | same | none |
| `sbousseaden/EVTX-ATTACK-SAMPLES` | `4ceed2f4706d` (2023-01-24) | same | none |
| `mdecrevoisier/EVTX-to-MITRE-Attack` | `474856008f03` (2026-05-21) | same | none |
| `invictus-ir/aws_dataset` | `4667aa9c2633` (2023-07-12) | same | none |

`attack_data`, pinned tree versus upstream tree (parsed from every YAML carrying a `datasets:` list,
plus a technique-ID scan of the paths):

| Measure | Pinned `4145e8b` | Upstream `c8af10d0` |
|---|---:|---:|
| tracked files | 3,695 | 3,812 |
| manifest-bearing episodes | 1,107 | 1,154 |
| distinct technique IDs in manifests | 307 | 317 |
| technique-named directories | 343 | 349 |
| payload bytes of added files | — | 2,626,355 (2.63 MB: 69 LFS + 50 regular) |

The 10 technique IDs declared upstream and not by any manifest at the pin:
`T1021.008`, `T1027.004`, `T1059.002`, `T1071`, `T1176.001`, `T1211`, `T1555.006`, `T1562.010`,
`T1586.001`, `T1685`. New technique directories: `T1021.008`, `T1071`, `T1555.006`, `T1562.010`,
`T1586.001`, `T1685`.

Two of the 47 new episodes are manifest changes over pre-existing data files, not new data:

- `T1218/lolbas_with_network_traffic` — at the pin this was `lolbas_with_network_traffic_old.yml`,
  which has no `datasets:` list, so `load_manifest_catalog` never read it and its log had never been
  ingested. Upstream replaced it with a proper manifest. The log itself is unchanged.
- `suspicious_behaviour/cisco_ai_defense_alerts` — same `_old.yml` conversion, but the new manifest
  declares `mitre_technique: []`. It carries no ATT&CK label and was excluded from the ingest.

Confirmed absent from the corpus as well as from the tree: none of the 47 new `p5_item` ids exists in
`labelled_corpus` (`| tstats count ... by p5_item`, 1,682 distinct items compared, 0 overlaps).

## 2. Sources surveyed for genuinely additional labelled telemetry

Bar: per-event or per-episode ATT&CK labels, real telemetry (not generation recipes), raw events,
no account/API key/payment. "Verified" means I read the repo tree, README or API metadata on
2026-11-07; "inferred" is publisher-stated or unread.

| Source | What it holds | Label attaches to | Formats / raw events | Licence | Size / last push | Verdict |
|---|---|---|---|---|---|---|
| [splunk/attack_data](https://github.com/splunk/attack_data) | 1,154 manifest episodes of publisher-recorded attacks | per-episode, `data.yml` `mitre_technique` list | XML, JSON, syslog, Zeek, CloudTrail; raw events yes | Apache-2.0 | 69 MB repo, 23 GB local; 2026-11-03 | **Ingested (refresh)** |
| [OTRF/Security-Datasets](https://github.com/OTRF/Security-Datasets) | Mordor episodes | per-dataset `_metadata` | JSON, EVTX, Zeek; raw events yes | MIT | 830 MB; 2024-03-20 | already at head |
| [sbousseaden/EVTX-ATTACK-SAMPLES](https://github.com/sbousseaden/EVTX-ATTACK-SAMPLES) | Windows EVTX samples | per-file path | EVTX; raw events yes | GPL-3.0 | 6.3 MB; 2023-01-24 | already at head |
| [mdecrevoisier/EVTX-to-MITRE-Attack](https://github.com/mdecrevoisier/EVTX-to-MITRE-Attack) | 270+ EVTX samples | per-file path | EVTX; raw events yes | CC0-1.0 | 3.3 MB; 2026-05-21 | already at head |
| [invictus-ir/aws_dataset](https://github.com/invictus-ir/aws_dataset) | CloudTrail from a Stratus scenario | dataset-level scenario | CloudTrail JSON; raw events yes | MIT | 368 KB; 2023-07-12 | already at head |
| [invictus-ir/o365_dataset](https://github.com/invictus-ir/o365_dataset) | Real M365 Unified Audit Logs from BEC intrusions | dataset-level only: README maps the corpus to `T1114`, `T1098`, `T1078.004`; no per-record/per-episode label file | JSON/CSV inside `auditrecords.7z`; raw events yes | CC-BY-4.0 | 599 KB; 2026-08-12 | **no** — label is a three-technique bag over the whole set; 9,608 records is publisher-stated (inferred) |
| [invictus-ir/gws_dataset](https://github.com/invictus-ir/gws_dataset) | Google Workspace audit logs "containing several attacks" | none described | JSON; raw events yes | MIT | 505 KB; 2022-08-15 | **no** — unlabeled |
| [sbousseaden/macOS-ATTACK-DATASET](https://github.com/sbousseaden/macOS-ATTACK-DATASET) | 73 Elastic Endpoint Security JSON files on macOS, one per technique | tactic directory + technique slug in filename; no explicit T-IDs, no metadata file | JSON; raw events yes | GPL (README links EVTX-ATTACK-SAMPLES licence) | 131 KB; 2021-09-10 | **no** — technique must be inferred from filenames; that is filename-derived labelling, and the `value_has_leak` path-token scrubber would strip it |
| [Sonnetica/windows-attack-telemetry](https://github.com/Sonnetica/windows-attack-telemetry) | 1,275-row CSV normalised from four `attack_data` recordings | 3 techniques only; README says labels "are not independently established ground truth" | CSV; raw events are a derivative | none declared | 95 KB; 2026-10-09 | **no** — derivative of the anchor source, not independent, no licence |
| [OTRF/SimuLand](https://github.com/OTRF/SimuLand) | Caldera abilities, ARM templates | recipes | none | GPL-3.0 | 52 MB; 2021-03-03 | **no** — generation recipes |
| [FiveDirections/OpTC-data](https://github.com/FiveDirections/OpTC-data) | DARPA OpTC ground-truth PDF and eCAR/Bro schema | ground-truth PDF per scenario | ~1 TB compressed JSON, hosted on Google Drive | public domain (README) | 428 KB; 2020-06-17 | **no** — not scriptable without a Drive quota; the local copy is the manifest only |
| [arXiv 2606.18190](https://arxiv.org/abs/2606.18190) | 870 sessions / ~2.3 M events, per-entry ATT&CK, 12 tactics / 53 techniques | per-event IDs (as described) | multi-source logs | CC-BY (per acquisition manifest) | paper source only; no data link in abstract or HTML (verified) | **no** — no public host as of 2026-11-07 |
| [Azure/Azure-Sentinel `Sample Data`](https://github.com/Azure/Azure-Sentinel/tree/master/Sample%20Data) | ASIM connector schema samples | none | CSV per connector | MIT | repo 47k files; current | **no** — schema samples, not labelled episodes |
| [RedCanaryCo/atomic-red-team](https://github.com/RedCanaryCo/atomic-red-team), [DataDog/stratus-red-team](https://github.com/DataDog/stratus-red-team), [splunk/security_content](https://github.com/splunk/security_content), [SigmaHQ/sigma](https://github.com/SigmaHQ/sigma), [elastic/detection-rules](https://github.com/elastic/detection-rules), [OTRF/OSSEM](https://github.com/OTRF/OSSEM) | atomics / rules / data dictionaries | n/a | no event store in tree (verified top-level trees) | various | current | **no** — recipes or rules, not telemetry |
| [sbousseaden/PCAP-ATTACK](https://github.com/sbousseaden/PCAP-ATTACK) | post-exploitation PCAPs | none | PCAP; the ingester deliberately reads text members only | none | 5.6 MB; 2021-04-29 | **no** — no label file, and packet data is out of scope for this path |

No surveyed source other than the `attack_data` refresh both (a) ships raw events and (b) attaches
ATT&CK labels at episode granularity or finer without an account.

## 3. What was ingested

Plan stated before the write:

- source: `splunk/attack_data` at `c8af10d015d392fca97f9eb65181e9f06bc18e40`
- materialised into a new empty directory:
  `/Volumes/data01/portal5_hunt/corpora/corpus_expand_20261107/attack_data_refresh/`
  (119 added files plus the 2 data files referenced by the converted manifests; each verified
  against its LFS sha256 or git blob sha1 before use)
- expected: 47 episodes, 3,171 events, 2.63 MB of source payload
- index: `attack_data_refresh_20261107` (new; did not exist)
- exclusions: `cisco_ai_defense_alerts` — `mitre_technique: []`, 1 event, no label

The write used the existing path, not a parallel ingester: `corpus_reingest.read_attack_data`
(`corpus_ingest.load_manifest_catalog`), `corpus_reingest.resolve_event` and
`corpus_reingest.ship_inputs`. `ship_inputs` gained two optional keyword arguments (`index`,
`fields`) so a corpus can go to its own index with its provenance; the default call is unchanged.
Every event carries `p5_item`, `publisher=attack_data`, `label_basis=data_yml`,
`evidence_origin=imported_observed`, `evidence_provenance=external_corpus`, `corpus_source` and
`corpus_commit`.

Receipt, live after the write:

- `| eventcount summarize=false index=attack_data_refresh_20261107` → **3,170**
- `| tstats count where index=attack_data_refresh_20261107` → **3,170**
- `| tstats count ... by p5_item` → **46** distinct items, min 1 / max 2,001 events; every item count
  equals the planned count; the only difference from the plan is the excluded 1-event item
- `| tstats count ... by publisher label_basis evidence_origin evidence_provenance corpus_commit`
  → one row, `3,170`, with the values above
- index metadata: `currentDBSizeMB=2`, `maxTotalDataSizeMB=4096`, `datatype=event`,
  `minTime=2022-10-07T17:39:05Z`, `maxTime=2026-11-11T14:43:59Z`

Per-sourcetype receipt:

| Sourcetype | Events |
|---|---:|
| `zeek:http` | 1,997 |
| `aws:cloudtrail` | 679 |
| `XmlWinEventLog` | 365 |
| `auditd` | 46 |
| `nginx:plus:kv` | 43 |
| `azure:monitor:aad` | 10 |
| `_json` | 9 |
| `osquery:results` | 6 |
| `sysmon:linux` | 4 |
| `cisco:sfw:estreamer` | 3 |
| `cisco:nvm:flowdata:v2` | 2 |
| `nginx:plus:error` | 2 |
| `zeek:ssh` | 2 |
| `apache:access:kv` | 1 |
| `apache:error` | 1 |

The 46 shipped episodes declare 38 distinct technique IDs.

## 4. Disk and time

Before the write:

- `/Volumes/data01`: 1.8 TiB total, 1.4 TiB used, **421 GiB available**
- `labelled_corpus` index: 4,687 MB; `portal5_lab` index: 3,939 MB
- `attack_data_refresh_20261107`: did not exist

After the write:

- `/Volumes/data01`: 1.4 TiB used, **421 GiB available** (unchanged at GiB resolution)
- `attack_data_refresh_20261107`: **2 MB** index, 4,096 MB cap
- source payload kept for retraction: 2.8 MB on disk (2.63 MB of file bytes)

Time:

- shipping call, 3,170 events in batches of 500: **1.1 s**
- eventcount reached 3,170 about 12 s after the call returned (indexing/search lag)
- materialisation: 119 files downloaded and digest-verified once; not separately timed

## 5. Label leakage in `_raw`

Scanned every shippable event with `corpus_truth.raw_leaks_label` (`T####`, `Atomic Red Team`,
`Stratus Red Team`), before the write, and re-measured live after it:

| Measurement | Result |
|---|---|
| offline scan, 3,171 planned events | **19 leaked (0.60%)** |
| live `_raw` scan, `search index=attack_data_refresh_20261107 earliest=0 \| eval leaked=if(<LEAK_MATCH>,1,0) \| stats count sum(leaked)` | **19 / 3,170 (0.60%)** |
| metadata-only `residual_leaks` from the planner | **0 / 3,170** — confirms the known blind spot |

All 19 are in one episode: `datasets/attack_techniques/T1546.003/atomic_red_team_wmi_subscription`
(19 of its 69 events). The matching text is the WMI consumer name
`AtomicRedTeam-WMIPersistence-CommandLineEventConsumer-Example` — the test tool named itself in the
telemetry. Those 19 events cannot anchor or be scored; the remaining 50 events of that episode are
clean. No event names a literal `T####`.

For context, the existing `labelled_corpus` was not re-scanned; the key generator's 1,764 / 363,214
figure from the brief is a sample of that corpus.

## 6. Fidelity notes observed during the scan

These come from the pre-existing `value_has_leak` scrubber, which treats any token from a test path
or filename as an answer token. 105 of 3,170 events (3.3%) had a declared sourcetype replaced:

| Episode | Declared | Indexed as | Events |
|---|---|---|---:|
| `T1068/vghost` | `sysmon:linux` | `XmlWinEventLog` | 96 |
| `emerging_threats/php2shell` | `suricata` | `_json` | 3 |
| `T1071.001/zeek_http_encoded_post` | `zeek:http` | `_json` | 2 |
| `T1071/zeek_http_unusual_method` | `zeek:http` | `_json` | 2 |
| `T1059/utility_socat_*` (2 episodes) | `osquery:results` | `_json` | 2 |

The trigger is the filename: `sysmon.log`, `suricata.log`, `http.log`, `osquery.log` contribute
`sysmon` / `suricata` / `http` / `osquery` to the path-token set, and the declared sourcetype
contains that token. `labelled_corpus` does hold 709,615 `sysmon:linux` events, so this is not a
blanket mapping — it is this filename pattern. The 96 Linux Sysmon events in `vghost` are therefore
indexed as Windows XML events. Not fixed here: changing the scrubber changes the shared ingest path.

Other observations:

- 197 of 3,171 planned events (6.2%) had no event timestamp and used the `data.yml` date; no event
  had a missing time.
- 261 events (8.2%) have `host=unknown`; 105 events (3.3%) have a replaced/unknown sourcetype.
- One episode (`T1098.003/aws_iam_role_created_with_external_trust`) carries an event stamped
  `2026-11-11T14:43:59Z`, four days after this run. It is the index `maxTime`; a `latest=now`
  search excludes it.
- Upstream removed two `_old.yml` files and no data files.

## 7. Gates (all run in this worktree after `uv sync --all-extras --frozen`)

```
uv run pytest tests/unit -q -n 4       5160 passed, 116 skipped in 125.17s
uv run pytest tests/security -q        1014 passed in 22.34s
uv run pytest tests/wfe -q             1414 passed, 1 skipped in 372.82s
uv run ruff check .                    All checks passed!
uv run ruff format --check .           1857 files already formatted
uv run mypy portal/                    Success: no issues found in 670 source files
python3 scripts/complexity_report.py --gate
  [complexity] GATE OK — data_lines 12,452 <= 13,370; god_lines 70,938 <= 71,192;
  unwired_scripts 23 <= 25; identical_pairs 0 <= 0; committed_blob_bytes 1,792,894 <= 1,873,616
```

## 8. Hand-off notes

- The new index is `attack_data_refresh_20261107`, 46 episodes, 3,170 events, all traceable by
  `p5_item`; every event carries its `p5_item` and the publisher/commit fields. The plan and the
  receipt are under the data root, not the repo:
  `${PORTAL_DATA_ROOT}/reports/review_eval/corpus_expand/20261107T000000Z__attack_data-c8af10d015d3/`
  (`plan_items.json`, `receipt.json`).
- It is not a truly independent source: it is later material from the anchor publisher. It is
  unseen material relative to `labelled_corpus` (0 overlapping `p5_item`s), which is the only sense
  in which it is "anchored elsewhere". The only independent candidate that shipped raw events and
  ATT&CK guidance (o365_dataset) has no per-episode label, so it was not ingested.
- No prediction about detection results is made here.

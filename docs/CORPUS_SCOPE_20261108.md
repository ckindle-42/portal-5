# Corpus scope — 2026-11-08

Which corpora current work may anchor on, score against, or cite as evidence.
Operator decision, recorded here so a later run does not silently re-adopt an
archived source.

## ARCHIVED — ignore for now (do not anchor, score, or cite as evidence)

| index | events | why archived |
|---|---:|---|
| `botsv1` | 33,413,837 | old data (2016-2017 vintage), not current; superseded for label purposes |
| `botsv2` | 226,337,781 | old data (2017 vintage), not current |
| `botsv3` | 2,030,855 | old data (2018-2020 vintage), not current |

Operator decision 2026-11-08: BOTS is "possible but not current"; focus moves
to modern third-party datasets. Its published CTF question/answer lookups
(`splunk/SA-ctf_scoreboard_admin/lookups/`) were NOT pursued — the BOTSv3 Q&A
request to `bots@splunk.com` is explicitly dropped.

**Data is retained, not deleted.** The index data stays on the lab Splunk
`splunk-etc` volume (`apps/botsv*_data_set`, ~32 GB) with LXC 301 snapshots
`corpus-loaded` and `current` intact. Nothing was removed.

**Code was NOT un-wired, deliberately.** `bully/corpus_bed.py` declares
`BOTS_INDEXES` as Lane A, the *haystack floor* (`MIN_HAYSTACK_RECORDS =
100_000`, `is_haystack`), and validation gates EX-FD include the haystack
floor plus FD's permanent non-haystack regression case. `bully/run_preflight.py`
calibrates its whole cost model on BOTS density (~84,583 rec/hr for botsv3;
botsv2 ~4x that). Stripping BOTS out would trip the floor and invalidate the
cost model, so the hunt path keeps its references. Archived means *new work
does not use it as a source*, not that the symbols are gone.

Verified 2026-11-08 that the new-data path carries no BOTS dependency:
`scripts/corpus_ingest.py`, `scripts/corpus_reingest.py` and
`scripts/load_attack_data_anchors.py` have zero `botsv*`/`BOTS`/`corpus_bed`
references and import none of `corpus_bed`, `run_preflight`, `inject_plane`,
`cousin_inject`. BOTS mentions in `review/window.py`, `siem/spl_backend.py`
and `bully/telemetry_behavior.py` are comments recording what was
live-verified against BOTS, not runtime dependencies.

## IN SCOPE — modern third-party, downloaded 2026-11-08

Under `/Volumes/data01/portal5_hunt/corpora/thirdparty_20261108/`, each in its
own directory, untrusted until read. 53 files, 8.82 GB.

| slug | dataset | published | size | licence | label attaches to |
|---|---|---|---:|---|---|
| `cam_lds` | Cyber Attack Manifestations (CAM-LDS) | 2026-01-27 | 7,410.9 MB | CC-BY-4.0 | ATT&CK technique; 36 scenario variants |
| `kyoushi` | Kyoushi Log Data Set | 2021-12-14 | 1,321.6 MB | CC-BY-NC-SA-4.0 | multi-host scenario; affected servers only |
| `cloud_obs` | Attack Observability in Cloud Telemetry | 2026-03-26 | 71.5 MB | CC-BY-4.0 | AWS/Azure/GCP logs + the attack scripts |
| `soc_mld` | SOC-MLD session-aware multi-layer | 2026-10-02 | 9.9 MB | CC-BY-4.0 | 32 classes; attack-instance-disjoint protocol |
| `mawa` | Multi-Attacker Web Attack | 2026-10-12 | 8.4 MB | CC-BY-4.0 | responsible attacker per stage |

CAM-LDS's filenames encode the cousin axis directly -- `scenario_1_racecondition_{pam,localaccount,sshkey}`,
`scenario_1_{pwnkit,validaccount,autostart}_localaccount` -- the same scenario
with systematically varied technique/persistence pairs, i.e. cousins supplied
by the publisher rather than by our own MUT stage.

## Still in scope, unchanged

| index | events | role |
|---|---:|---|
| `labelled_corpus` | 8,877,181 | attack_data + Mordor, per-item `data.yml` ATT&CK labels |
| `attack_data_refresh_20261107` | 3,170 | attack_data refresh; unseen but NOT independent (same publisher as anchors) |
| `portal5_lab` | 17,786,835 | our lab; note it also holds imported `corpus:raw` dated 2019-2023, so it is not a clean benign source wholesale |

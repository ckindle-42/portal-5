# FINDING — hunt replan D6: route out the shipper copies, JSON-safe `user`, index `auid`

Lane `lane/hunt-d6`, 2026-11-21. Implements slice D6 of
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 (RC10, and the `linux_secure` mix in RC5). **No stage was
run from this lane** — D6 is index-time, so the re-apply and reship below are the orchestrator's,
and every number here is offline: the reindex plan's arithmetic over the three ingest receipts,
and the index-time regexes applied to the corpus bytes on disk.

Slice D6 of `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 (RC10, RC5-adjacent). Operator-owned by the
brief; **no live stage was run from this lane** — the re-apply and reship are the orchestrator's.

## The property

> A tuned index contains each event family once, one raw shape per sourcetype, and the index-time
> `user`/`auid` are the field's real values.

Three changes in `scripts/lab/splunk_setup` (the app tree is regenerated from them):

1. **Routing** (`plan.py`): `*-system.{auth,service,syslog}.log` — filebeat's `system` module
   re-shipping a host's logs as one JSON object per line — and the journald system export
   (`system.journal.txt`) route to noise. Per-user journals (`user-<uid>.journal.txt`) stay in
   `syslog`: measured offline, 2,161 such lines on santos share no message body with the host's
   system journal, so they are not a duplicate.
2. **`user`** (`conf.py`): `…|for user )([A-Za-z0-9_.@-]+)` instead of `(\S+)`.
3. **`auid`** (`conf.py`): a new `ph_ix_linux_audit_auid` stanza, `(?:^|\s)auid=(\d+)`.
4. **Verify** (`plan.py`, `cli.py`): `service_log_absent`, `user_clean`, `auid_indexed` probes;
   `Probe.max_rows` lets an absence probe fail on a non-empty result.

## Proof, per property (offline, on the real receipts and the real corpus bytes)

| property | proof |
|---|---|
| each event family once | `plan.build_reindex_plan` over the three ingest receipts: `_v2` totals become **kyoushi 2,425,851 / santos 2,573,164 / russell 2,261,780**, `syslog` **kyoushi 86,713 / santos 84,674 / russell 58,908**. santos drops 1,863,907 filebeat-copy events (36 files: 1,856,634 `system.service` + 3,120 `auth` + 4,153 `syslog`) and 37,529 journal events. The deep dive's independent live `source="*system.service.log"` count, 1,856,634, matches the receipt to the event. |
| no graded evidence is routed out | every line of all three `keys.jsonl` joined to the receipts on `(host, source)`: **0** labelled lines on a file D6 routes out (kyoushi 408,038 / santos 47,367 / russell 61,862 checked). The only labelled lines on any routed-out file are the pre-existing `2022-01-17-system.cpu.log` 44 (santos, RC3) and `2022-01-24-system.cpu.log` 49 (russell) — the metric files stage 2 already dropped, untouched by D6. |
| `user` is the real value | on the shipper copies (the only JSON `linux_secure` shape): old `\S+` captured >64 bytes for **1,090 of 2,227** matches on santos and **1,075 of 2,230** on russell (e.g. `root","@version":"1","log":{"offset":0,…`); the new class **0 of 2,227 / 0 of 2,230**. On the files that stay (`auth.log*`) neither class exceeds 64 bytes: santos 6,137 users, russell 6,206, kyoushi 8,108. |
| `auid` is the real value | every `linux_audit` line matches: 25,090 (kyoushi) / 24,034 (santos) / 18,692 (russell), 5–6 distinct ids incl. `1002`. `\bauid` was wrong: in `uid=0 old-auid=4294967295 auid=1002` it captures **4294967295** (the pre-change id) because `-` is a word boundary; `(?:^|\s)` captures `1002`. |
| verify judges the index, not the conf | `test_verify_fails_a_zero_row_entity_tstats` now drives all three probes both ways: rows returned → `service_log_absent` + `user_clean` FAIL with `got more than 0 rows`; empty → clean pass. |

## Files changed

- `scripts/lab/splunk_setup/plan.py` — routing rules, `Probe.max_rows`, three verify probes, `syslog` note.
- `scripts/lab/splunk_setup/conf.py` — JSON-safe `user` class, `auid`.
- `scripts/lab/splunk_setup/cli.py` — `_probe_row` enforces `max_rows`.
- `scripts/lab/splunk_setup/app/portal5_hunt_setup/default/{transforms,props,fields}.conf` — regenerated.
- `tests/unit/test_splunk_setup.py` — routing case extended, one new test for the index-time values, verify test extended.
- `docs/hunt/SPLUNK_SETUP_RUNBOOK.md`, `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` — the change, its measured volumes, the three probes.

## The orchestrator's live proof

D6 is an index-time change, so the `_v2` indexes must be **dropped and re-shipped**; a restart or
re-`apply` changes nothing already indexed.

```bash
set -a; export $(grep -E '^LAB_SPLUNK_(URL|USER|PASSWORD|HEC_URL|HEC_TOKEN)=' .env | xargs); set +a

# 1. the box's 2026-11-21 hotfix copy wins over default/ and holds the OLD user regex: remove it
ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST \
  "pct exec 301 -- docker exec -u splunk splunk rm -f /opt/splunk/etc/apps/portal5_hunt_setup/local/transforms.conf"

# 2. install the regenerated app (restarts Splunk)
uv run python -m scripts.lab.splunk_setup app --check          # in_sync: true
uv run python -m scripts.lab.splunk_setup apply --dry-run
uv run python -m scripts.lab.splunk_setup apply

# 3. drop each _v2 index and re-ship it from the corpus (3-5 min per family)
curl -sk -u $LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD -X DELETE \
  $LAB_SPLUNK_URL/services/data/indexes/hb_kyoushi_s1_v2
curl -sk -u $LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD -X DELETE \
  $LAB_SPLUNK_URL/services/data/indexes/hb_ait_santos_v2
curl -sk -u $LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD -X DELETE \
  $LAB_SPLUNK_URL/services/data/indexes/hb_ait_russellmitchell_v2
uv run python -m scripts.lab.splunk_setup reindex --index santos --ship
uv run python -m scripts.lab.splunk_setup reindex --index kyoushi --ship
uv run python -m scripts.lab.splunk_setup reindex --index russellmitchell --ship

# 4. the three new probes
uv run python -m scripts.lab.splunk_setup verify --index santos
```

Expect (`verify` rows, plus the deep dive's own SPL):

- `service_log_absent:hb_ait_santos_v2` → `ok: true`, `rows=0`.
- `user_clean:hb_ait_santos_v2` → `ok: true`, `rows=0`.
- `auid_indexed:hb_ait_santos_v2` → `ok: true`, `rows>0`.
- `| tstats count where index=hb_ait_santos_v2 by sourcetype` → `syslog` **84,674** (< 300 k),
  total **2,573,164** (< 2.7 M), 14 rows, no `2022-…` names.
- `| tstats count where index=hb_ait_santos_v2 sourcetype=linux_secure by user | where length(user) > 64` → 0 rows.
- `| tstats count where index=hb_ait_santos_v2 sourcetype=linux_audit by auid` → >0 rows, incl. `1002`.

Fails if: `service_log_absent` returns rows (the DELETE did not happen or `--force` was used on a
populated index), `user_clean` returns rows (the `local/transforms.conf` was still in place, or the
index was not rebuilt), or `auid_indexed` is empty (same two causes).

## Not proven here

- Nothing above was measured on a live index: the totals are the reindex plan's arithmetic over
  the receipts, the regex results are the corpus bytes.
- The live `syslog`/total eventcounts, the `verify` rows, and `auid`/`user` in the tsidx are the
  orchestrator's to read.
- `kyoushi` has no filebeat re-ships (its 2021 capture predates them): only its journal is dropped,
  so the santos/russell volume change is the interesting one.
- D6 does not touch RC3: the 44 labelled lines inside `2022-01-17-system.cpu.log` were already
  unreachable before this slice and still are.

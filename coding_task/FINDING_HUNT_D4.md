# FINDING — hunt replan slice D4 (spine types the numeric identities the estate carries)

Lane `lane/hunt-d4`, 2026-11-21. Implements D4 of `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 on the
root cause in §3.4.

## The change

`portal/modules/security/core/hunt/notables/spine.py`: `uid`, `auid`, `gid`, `euid`, `sid` join
`_USER_FIELDS`, so a record whose only identity is a numeric id (or a Windows SID) carries a
`user` entity and lands in an episode. `acct` was already a user field, so a record carrying both
records both identities. The five names are the field vocabulary the doc's §3.4 proof used.

No other code change was needed. The Build's second clause — a partitioned card's `part` is part
of the entity key so `event_type=dns` and `flow` never merge — is already true at HEAD:
`build_spine` keys entities, episode groups and the episode-id hash on `(kind, value, source_id,
part)` (`spine.py:621`, `spine.py:398-413`). Measured on the rebuilt santos `_v2` spine: address
`10.229.0.4` is two rows, `part=dns` (1,475 events, 21 episodes) and `part=flow` (1,901 events,
20 episodes), and `hb_ait_santos_v2:suricata` has no episode row with an empty part.

## Property, measured offline

The property: an audit record whose only identity is numeric still carries an entity and lands in
an episode. Measured by rebuilding each stored run's spine from its own `behaviours.duckdb` into a
hardlinked copy under `coding_task/scratch/d4/` (the proof run was never written to), and running
`verify_steps` with the corpus keys. The baseline build (the new field names removed in-process)
reproduces each stored `spine.json` receipt exactly.

| run | events_without_entity | user entities | verify steps (read / pass) | lines_without_entity |
|---|---:|---|---|---|
| santos `_v2` before | 3,351 | 134 | 21 (11 / **9**) | 2 |
| santos `_v2` after | **2,958** | 139 | 21 (11 / **11**) | **0** |
| santos control before | 4,814 | 578 | 21 (12 / 12) | 0 |
| santos control after | 4,659 | 586 | 21 (12 / 12) | 0 |
| kyoushi `_v2` before | 5,876 | 1,662 | 12 (7 / **5**) | 2 |
| kyoushi `_v2` after | **5,364** | 1,672 | 12 (7 / **7**) | **0** |
| russell `_v2` before | 2,323 | 332 | 22 (11 / 11) | 0 |
| russell `_v2` after | **1,924** | 337 | 22 (11 / 11) | 0 |

The two santos `_v2` steps D4 recovers are `attacker_change_user` and `escalate`, both carried by
the one audit line whose identity is `auid=1002`; `attacker_change_user`'s carrier is now
`user:1002`. kyoushi gains two steps the doc did not measure. Nothing regressed: the control
stays 12/12 and russell stays 11/11, and `lines_without_entity` never rises.

`record both`, measured on the rebuilt store: the `USER_START` record carrying `auid=1002` and
`acct="gmorgan"` yields `user:1002` and `user:gmorgan` on the same event.

## Read-only lab evidence (why the identity is invisible to the index vocabulary)

Job API against `hb_ait_santos_v2`, training family only, credentials read from the live
checkout's `.env` by key name (never sourced):

```spl
search index=hb_ait_santos_v2 sourcetype=linux_audit | stats count
  -> 24,042                     scan 24,042   0.53 s
search index=hb_ait_santos_v2 sourcetype=linux_audit "auid=1002" | table _raw
  -> 2 rows                     scan 8        0.39 s
     type=LOGIN msg=audit(1642420697.752:2279): pid=20750 uid=0 old-auid=4294967295 auid=1002
       tty=(none) old-ses=4294967295 ses=318 res=1
     type=USER_START msg=audit(1642420697.752:2280): pid=20750 uid=0 auid=1002 ses=318
       msg='op=PAM:session_open acct="gmorgan" exe="/lib/systemd/systemd" …'
| tstats count where index=hb_ait_santos_v2 sourcetype=linux_audit by auid
  -> 0 rows                     scan 24,042   0.33 s
```

`auid` is not an index-time field, so no `tstats`/`by auid` query can ever see the identity; the
spine's parse of `_raw` is the only route, which is what D4 makes work.

## Orchestrator proof command

Rebuild the santos `_v2` spine from the stored run (copy under `/tmp` so the stored receipt
survives), then read the receipt:

```bash
cd /Users/chris/projects/portal-5-hunt-d4
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700
d=/tmp/hunt-d4-proof && mkdir -p $d && ln -f $run/v2/santos/behaviours.duckdb $d/
cp $run/v2/santos/sources.json $run/v2/santos/progress.json $d/
uv run python -m portal.modules.security.core.hunt.notables.spine --out $d --family santos \
  --keys /Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
```

Pass: `without_entity=2958`, `kinds={… 'user': 139}`, then `steps=21 read=11 pass=11 …
lines_without_entity=0`. Fail: `without_entity=3351` / `user: 134` / `pass=9` (the change did not
reach the interpreter), or `pass < 11` with `lines_without_entity 0` (a different defect).

Both runs were executed this way on the final tree before this report:
`spine: events=137574 … without_entity=2958 … 'user': 139` then `steps=21 read=11 pass=11
lines_read=8990 lines_with_episode=8990 lines_without_entity=0`, and on the control
`spine: events=182083 … without_entity=4659 … 'user': 586` then `steps=21 read=12 pass=12 …
lines_without_entity=0`.

The same command against `$run/control/santos` must print `pass=12` (no regression), and against
`$run/v2/kyoushi` `pass=7` / `$run/v2/russell` `pass=11`.

## Reproduce the offline tables

`coding_task/scratch/d4/probe.py <dir> <family>` and `probe_baseline.py <dir> <family>` (scratch,
gitignored), over hardlinked copies of `behaviours.duckdb`, `sources.json`, `progress.json` from
the proof run. Baseline runs remove the five names from `_USER_FIELDS` in-process.

## Unproven

- The live hunt path (`notables` → `spine`) was not run: operator hold, and the orchestrator owns
  the live run. The proof above is a rebuild of an existing store, not a fresh hunt.
- The part-keying clause was not exercised by a new test; it is asserted by code reading plus the
  stored-run query above.
- `user:4294967295` (auditd's "unset" id) and one malformed `user:0)` now exist as entities —
  noise, not a defect for this property; filtering sentinels is not in D4's build.

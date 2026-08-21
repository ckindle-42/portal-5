# BULLY_CORPUS_BED_LANE_A_VERIFY_C2_V1

Lane A (BOTS v1/v2/v3) install-and-verify pass, `TASK_BULLY_CORPUS_BED_V1` C.2.
Run against the live lab Splunk (LXC 301, `splunk` docker container).

## Install

`scripts/lab_bots_install.py` run as the `splunk` user
(`docker exec -u splunk splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py
--workdir /opt/splunk/var/p5corpus`), per
`unit-corpus-injection-inside-lxc-301-as-the-splunk-user-uid-41812-the-apps-dir-is-splunk-owned`.
All three datasets were **already installed** (app dirs present under
`/opt/splunk/etc/apps`) from a prior operator install; the run was idempotent
(`[skip]` for all three) and repaired/confirmed the retention pin
(`frozenTimePeriodInSecs = 3155760000`, 100y) in each app's `local/indexes.conf`.
`splunkd` was already running (KVStore mid-upgrade refused a restart, which
`--no-restart` semantics tolerate) -- the indexes were already searchable, so
no restart was required.

## Verify by counting (`| tstats`, not a scan, per the wiki)

```
| tstats count where index=botsv1 OR index=botsv2 OR index=botsv3 by index
```

| index  | count       | distinct sourcetypes | earliest   | latest     |
|--------|-------------|-----------------------|------------|------------|
| botsv1 | 33,413,777  | 26                    | 2016-08-01 | 2016-08-29 |
| botsv2 | 226,317,740 | 104                   | 2017-08-01 | 2017-08-31 |
| botsv3 | 1,944,092   | 107                   | 2018-08-20 | 2019-09-19 |

**Lane A total: 261,675,609 records**, each index with well over 5 distinct
sourcetypes -- verification criterion met for all three.

For context, `portal5_lab` (Lanes B/C, the index every prior bully run read
exclusively) currently holds 15,786,505 records. Combined real corpus across
all lanes: **~277.5M records**.

## Verdict

`BLOCKED` was not triggered for any dataset -- all three install and verify.
Lane A is live and ready for `corpus_bed.resolve_indexes()` /
`corpus_bed.assess_bed()` to see.

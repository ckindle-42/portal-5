# FINDING — Splunk access logs: vhost_combined lines put the vhost in `c_ip` (stage 2, 2026-11-21)

Lane: `lane/splunk-vhost-cip`. Brief: `coding_task/BRIEF_SPLUNK_VHOST_CIP.md`.

## What was wrong

`other_vhosts_access.log*` is Apache **vhost_combined** — `vhost:port client - - [date] …` — but
`plan.classify("other_vhosts_access.log")` routes it to `access_combined`, whose index-time regex
was `^(\S+) `, i.e. the first token. So `c_ip` became `cloud.dmz.smith.santos.com:443` and is in
the tsidx that way. `c_user` (`^\S+ \S+ (\S+) \[`) did not match at all on those lines: the extra
`vhost:port ` token pushes the `[` one field out, so the field was missing, not wrong.

Measured on the receipts the reindex reads (`/Volumes/data01/portal5_hunt/corpora/…`), not
sampled:

| index | access files / events | of which vhost_combined |
|---|---:|---:|
| `hb_kyoushi_s1` | 29 / 727,925 | 5 files / **54,349** events |
| `hb_ait_santos` | 23 / 329,442 | 4 files / **44,244** events |
| `hb_ait_russellmitchell` | 23 / 148,329 | 4 files / **27,500** events |

Every vhost line is on host `cloud_share`; every other access log (`*-access.log`,
`horde-access.log`, `proxy-access.log`) is plain `combined`. 126,093 of the 1,205,696 access
events are vhost_combined, so all three `_v2` indexes hold them.

## The routing decision: one sourcetype, one optional-prefix regex

**Chosen: keep `access_combined` and make the regex shape-aware.** Reasons, from the real files:

1. **The shape is a `LogFormat` choice, not a filename property.** The same estate writes
   `webserver:/apache2/cloud.smith.santos.com-access.log` in `combined` (first token
   `192.168.104.133`) and `cloud_share:/apache2/other_vhosts_access.log` in `vhost_combined`.
   A sourcetype split keyed on the filename would mis-route the first shape, and a split keyed on
   a head sample cannot be written in `props.conf` at all.
2. **The runbook's mapping is per data type.** `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` §5.1 and
   `SPLUNK_SETUP_RUNBOOK.md` §5.1 send `other_vhosts_access.log` to `access_combined`; CIM `web`
   is a data-type tag, and the Web model, the `ph_web_access` eventtype and every
   `sourcetype=access_combined` hunt already cover both. A second sourcetype would need its own
   `TARGETS` entry, `INDEX_FIELDS` set, `EVALS` set, props stanza, eventtype and tag — six
   duplicated bindings, none of which a hunt would know to union.
3. **The regex is exact because a client address cannot be `host:port`.** The prefix is
   `[^\s:]+:\d+ `, deliberately not `\S+:\d+ `: the clients include IPv6 (`::1`, 21,963 of the
   1.2 M access `c_ip` values; 19,594 of them plain `combined` lines from the intranet hosts).
   `\S+:\d+` would eat `2001:db8::443`-shaped addresses as a vhost; `[^\s:]+` cannot match a
   colon-bearing token at all.

**Property, measured over every access line in the three corpora** (all 1,205,696, receipt file
set): the new `c_ip` regex returns the client on 1,205,696 / 1,205,696 lines, never a
`host:port` value, and captures every colon-bearing client token whole. Against the old regex the
capture changed on exactly the 126,093 vhost lines and on **0** of the 1,079,603 `combined` lines,
so the change is backward compatible by measurement.

## What now owns it

- `conf.INDEX_FIELDS["access_combined"]`: `c_ip` = `^(?:[^\s:]+:\d+ )?(\S+) `, `c_user` =
  `^(?:[^\s:]+:\d+ )?\S+ \S+ (\S+) \[`, and a new index-time `vhost` = `^([^\s:]+):\d+ `.
  `WRITE_META` and `props.conf`'s `TRANSFORMS-ph_ix_*` list are rendered for it automatically.
- `conf.EVALS["access_combined"]`: `site = vhost` — CIM Web defines `site` as "The virtual site
  which services the request"; `dest` stays `host` (CIM: "the destination of the network traffic").
  The vhost is search-time `site` and index-time `vhost`, so both `tstats by vhost` and Web-model
  searches answer.
- `plan.verify_probes`: a `vhost_indexed:<index>` probe (`| tstats count where index=<i>_v2 by
  vhost`, `min_rows=1`), so `verify --index X` fails by row count if the field missed the tsidx.
- Docs: runbook stage 1 (both shapes, the regex and the split decision), stage 2 (the `by c_ip` /
  `by vhost` checks and the reship rule), stage 5 (the new probe); realism doc §5.1 mapping row and
  §5.4 access-log field list.

## Orchestrator's live proof

Index-time change: every `_v2` index built before this app is applied is wrong in `c_ip`, so all
three need a reship — `hb_kyoushi_s1_v2`, `hb_ait_santos_v2`, `hb_ait_russellmitchell_v2`
(54,349 / 44,244 / 27,500 vhost events respectively).

```bash
uv run python -m scripts.lab.splunk_setup app --check          # in_sync: true
uv run python -m scripts.lab.splunk_setup apply                # installs default/, restarts Splunk

# which indexes are still wrong (run before the reship): rows mean the vhost is still in c_ip
#   | tstats count where index=<i>_v2 by c_ip | where c_ip="*:*"      # any row = stale
#   | tstats count where index=<i>_v2 by vhost                        # 0 rows = stale

for key in kyoushi santos russellmitchell; do
  uv run python -m scripts.lab.splunk_setup rollback --index $key    # DELETE the _v2 index
  uv run python -m scripts.lab.splunk_setup reindex --index $key --ship
done

uv run python -m scripts.lab.splunk_setup verify --index santos \
  | tee coding_task/scratch/splunk_setup/verify-vhost.json
```

The property, per index:

```spl
| tstats count where index=hb_ait_santos_v2 by c_ip | sort - count | head 5
```
Worked: only client addresses (`10.…`, `172.…`, `::1`). Did not: any value carrying `:443`/`:80`.

```spl
| tstats count where index=hb_ait_santos_v2 by vhost
```
Worked: rows for `cloud.dmz.smith.santos.com` (43,482 on :443, 762 on :80) — same shape for
kyoushi (`cloud.dmz.company.cyberrange.at`, 53,072/1,277) and russellmitchell
(`cloud.dmz.smith.russellmitchell.com`, 27,158/342). Did not: 0 rows.

`verify --index X` must show `vhost_indexed:hb_*_v2` with `row_count > 0`; a 0-row answer is
`failed: true` with `expected >= 1 rows, got 0`.

## Gate

`uv run pytest tests/unit/ -q` 3020 passed / 22 skipped; `ruff check` and `ruff format --check`
clean; `uv run mypy portal/` = **650 errors in 70 files**, the baseline recorded in
`FINDING_SPLUNK_WRITE_META.md` (pre-existing, none in `scripts/lab/splunk_setup/`).

Net test lines: **+31, −0** in `tests/unit/test_splunk_setup.py` (one new test; no test deleted or
relaxed).

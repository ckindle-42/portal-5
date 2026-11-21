# D2 — one field vocabulary: the estate's, joined to the parse (implemented)

Slice D2 of `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5, branch `lane/hunt-d2`.
No hunt pipeline was run (operator hold); everything below is a read-only replay of the
stored runs' cards against the lab Splunk, or arithmetic on the stored runs' own JSON.

## The defect, measured on the stored runs

`docs/hunt` deep dive §3.2 counted 20 of santos' 32 value lists as structurally empty.
Re-derived from each run's `inventory.json` (all four stored runs, same command):

| run | lists | `empty` | of which a parse-local name (`template`, `program`, `v*`) | seconds spent on those scans | complete |
|---|---:|---:|---:|---:|---:|
| santos `_v2` | 32 | 20 | 20 | 15.0 | 11 |
| santos control | 32 | 19 | 19 | 11.3 | 13 |
| kyoushi `_v2` | 32 | 16 | 16 | 10.4 | 16 |
| russell `_v2` | 32 | 19 | 19 | 13.4 | 13 |

Every one of those lists ran `search … | stats … by <slot>` — a full scan of the source
(0.4–1.4 s each) to learn that the estate has no such field. `status: empty` was therefore
saying "this name cannot exist", which the plan never allowed.

## What changed

`portal/modules/security/core/hunt/notables/inventory.py`:

1. **The vocabulary comes from the estate, not from a list in the code.**
   `| rest /servicesNS/-/-/configs/conf-fields | fields title INDEXED` returns 62 stanzas on
   the lab; after dropping the event's own metadata (`host`, `source`, `sourcetype`, `index`,
   `_*`, `date_*`, `punct`, `linecount`, `splunk_server`) 41 names remain — `c_ip`, `acct`,
   `exe`, `signature`, `dns_query` … No field name is written in the source.
2. **One presence probe per source, not one per name.**
   `search <route> | head 1000 | stats count as sampled, count(f) as p0, …` resolves every
   candidate name in a single bounded read (measured 0.4–1.8 s). A name with `count = 0` is
   recorded as `parse_only: true`, `status: parse_only`, with no mechanism, no
   `events_scanned` and no query.
3. **Selection only turns a proven name into a query**, and takes the lists round-robin
   across sources (rank within card first), so one card can no longer take the whole
   `INVENTORY_MAX_FIELD_SEARCHES` budget — the old global sort by card id did exactly that
   once a template card could contribute eight names.
4. `searches` is now `queries − probe_queries`, so a labelled row can never count as a search.

Effort budgets: `INVENTORY_MAX_FIELD_SEARCHES` 32 → 40 (three lists per source) and two new
probe budgets. Cost measured below.

## Live proof (read-only replay of the stored cards, lab Splunk, santos `_v2`)

Cards, index and window come from the stored run
(`/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/v2/santos/sources.json`);
only the read path changed. 123 queries, 109 s, `probe_failures: []`, `vocabulary: 41`.

| expected by the deep dive | result |
|---|---|
| `access_combined:c_ip` = 18, complete, tstats | **18**, complete, tstats, 0.44 s |
| `linux_audit:acct` = 13, complete, tstats | **13**, complete, tstats, 0.44 s |
| `suricata:fast:signature` = 22, complete, tstats | **22**, complete, tstats, 0.44 s |
| `linux_audit:exe` = 7, complete, tstats | **not selected** — see below |
| searches whose `by` names a parse-local field = 0 | **0 of 123 queries** |
| `empty` means present-and-zero | **0 lists reported `empty`** |

`linux_audit` exposes eight names in this estate (`auid`, `type`, `uid`, `acct`, `addr`,
`dest`, `exe`, `src`); `exe` is its seventh, so reaching it needs a seven-list-per-source
budget. Lifting `INVENTORY_MAX_FIELD_SEARCHES` to 200 (measured) selects all 71 present
lists, includes `exe`, and takes **270 s** — of which 77 s is the eight `syslog` lists, i.e.
the duplicate `system.service.log` shipper copy the deep dive's D6 routes out (RC10). The
budget was left at 40 rather than set to whichever number reproduces the four example
figures.

Other measured effects on santos `_v2`: 35 complete lists over 12 cards (was 11 over 9),
`flows: 1330` (was 0 — the lists now have cross-source values to compare), statuses
`{parse_only: 59, complete: 35, capped: 4, failed:censored: 1}`. The one censored list is
`syslog.dest`, a 1.86 M-event scan cut at the 30 s query budget — RC10 again.

Kyoushi `_v2`, same replay: 63 s, 43 searches, 40 complete lists over 15 cards, 0 `empty`,
0 parse-local queries (`access_combined:c_ip` 23, `suricata:fast:signature` 13).

## Property and test

- `status: parse_only` (new) carries `parse_only: true` and is never queried; `status: empty`
  is only reachable for a name a probe proved present.
- `tests/unit/test_hunt_inventory.py::test_the_estate_vocabulary_replaces_parse_local_names_as_lists`
  — a template card whose roles are `program/template/v1/v2` and whose estate exposes
  `c_ip`/`acct`: the estate names are listed (tstats, complete) and the parse-local names are
  `parse_only`, with no `by template`/`by v1` query. Net test lines: +54.

## Risks

- The vocabulary read is a REST call. If the hunt identity cannot read
  `/servicesNS/-/-/configs/conf-fields`, `vocabulary` is 0 and a template card's lists fall
  back to `parse_only` (no false `empty`, but no estate lists either). `probe_failures` records
  it. Verified working as the lab admin in the replay above.
- `flows` rises from 0 to 1330/4693. That is D9's signal, not this slice's; the number is
  reported, not judged.

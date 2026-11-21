# Slice D3 — a capped value list keeps both ends of the volume distribution

Replan slice D3 of `ORCACYBER_DEEP_DIVE_2.md` §5 (root cause RC8 in §3.8). Code:
`portal/modules/security/core/hunt/notables/inventory.py`.

## The property

`status: capped` implies `values > 0`, and the rarest decile of the list is represented.
A status of `empty` keeps its old meaning ("the field is present and has 0 values").

## What changed

- `_values` no longer discards the rows it read. Over `INVENTORY_MAX_VALUES` it keeps the
  volume head (the highest-count values) plus the rarest rows, up to `LIST_MAX`, and reports
  `capped_share` — kept values over the aggregate's own distinct total.
- Every value aggregate is now bounded server-side (`_bounded`): `eventstats count as
  inventory_distinct | sort 0 -count | head LIST_MAX+1`, so the head query returns the volume
  head rather than an arbitrary prefix, and carries the list's true distinct count.
- A capped list issues one extra tail aggregate (`| sort 0 count | head LIST_MAX/10`) for the
  rarest values, and the record's `seconds` includes it.
- `searches` in `inventory.json` is now the read count the run actually issued
  (`prober.queries - probe_queries`) instead of `fields + joints`, so a capped list's second
  read is visible.

## Measured, read-only against the lab index `hb_ait_santos_v2`

The stored `_v2` santos run recorded `suricata` (`event_type=dns`) `dns.rrname` as
`capped` with `values: []`. Replaying the fixed path on the same index (same card, same
window, job API only, nothing written to the lab):

```
suricata event_type=dns dns.rrname
  status capped  values 5000  capped_share 0.256898  mechanism tstats
  events/count min 1  max 5233  values with count 1-12: 4084

dnsmasq dns_query
  status capped  values 5000  capped_share 0.249626  mechanism tstats
  events/count min 1  max 6553  values with count 1-12: 4251
```

`capped_share` 0.256898 = 5000/19,463 and 0.249626 = 5000/20,031: the denominators are the
counts the deep dive measured independently with `dc()`.

Cost per capped list, measured: head read 0.43–0.51 s, tail read 0.43–0.47 s, on 192,480 and
567,537 scanned events (`search`-route shapes measured separately at 1.26–1.27 s over 567,569
events). The tail is a second search per capped list and nothing more.

## Deviation from the slice text, stated

The build says "keep per-host top-k". The kept head is the top-k **by value volume**; the
record's `hosts` is `dc(host)` per value, and no per-host grouping is issued. A per-host top-k
needs an aggregate keyed `(value, host)`, whose row count multiplies by host, and every
consumer of `inventory.fields[].values` expects one row per value. Not implemented; measured
behaviour above does not depend on it.

## Consumer side effect

`behaviours.anchor_windows` already accepted `status in ("complete", "capped")`; until now a
capped list contributed no spans, so wide sources never anchored on those fields. They now do.
Expect the behaviour receipt's window selection to change for sources that do not fit the row
budget — that is the point of keeping the list, and it should be read in the live run.

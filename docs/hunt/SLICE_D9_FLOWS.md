# Slice D9 — flows on the consolidated estate

Replan slice D9 of `ORCACYBER_DEEP_DIVE_2.md` §5 (root cause RC11 in §3.11). Code:
`portal/modules/security/core/hunt/notables/inventory.py` (`_flows` and its helpers).

## The property

A flow is `(entity, host)` ordered across role-vector-different sources inside the entity's
own span. A value present in two sources with an identical raw digest is a **duplicate**, not a
flow. Every candidate that is not emitted is counted under `inventory.json:flow_skips`.

## What changed

`_flows(records)` became `_flows(records, hosts, prober, index)`, returning
`(flows, flow_skips)`. Each candidate value now passes, in order:

| gate | rule | skip reason |
|---|---|---|
| entity | `_entity_token` (an address, or a token with a letter, ≥4 chars) | `not_entity` |
| sources | present in ≥2, and no more than `FLOW_MAX_SOURCES` (12) sources | `single_source`, `ambient` |
| digest | the ingress step and *every* other source's step carry a different aggregate (`field`,`events`,`first_seen`,`last_seen`) | `duplicate` |
| shape | the later endpoint's card has a different selected role vector (its `(role, field)` plan) from the ingress card's | `same_role_vector` |
| span | the later step starts within `FLOW_MAX_GAP_SECONDS` (4 h, the case-link gap) of the ingress step's last observation | `gap` |
| host | both endpoints name or probe to the same host | `host` |
| budget | at most `FLOW_MAX_FLOWS` (64) emitted | `capped` |

- **Host.** A card whose `facts.host_count` is 1 names its host with no query. A multi-host
  card is asked once per endpoint with `| tstats count where index=… sourcetype=… <field>=<value>
  by host` (only when the field answered on the tsidx path; ≤ `FLOW_MAX_PROBES` = 16 probes per
  index, ≤ `FLOW_HOST_ROWS` = 64 rows). Both endpoints must share a host, otherwise the
  candidate is `host`-skipped. When the host cannot be probed (search-time field, probe budget
  spent) the flow is emitted with `host: ""` and `host_proven: false` rather than dropped.
- A flow carries `status: complete` (so the scoreboard's inventory cells read it), `host`,
  `host_proven`, `ingress`, `later` and the two endpoint steps.
- Capped lists (`status: capped`, D3) do **not** feed flows: a partial value list cannot prove
  a value is absent from an endpoint, and a flow is a presence claim on both sides.

## Measured offline — the six stored runs, replaying the new `_flows`

Read-only against `hunt_proof_20261120T232700`; the host probe reports `offline`, so hosts are
unproven exactly as on a search-time field.

```
run              stored flows   new flows   flow_skips
control/santos        17            0        {'duplicate': 17, 'not_entity': 9, 'single_source': 1404}
v2/santos              0            0        {'not_entity': 7, 'single_source': 1457}
control/kyoushi       21            0        {'duplicate': 21, 'not_entity': 8, 'single_source': 1399}
v2/kyoushi             0            0        {'not_entity': 8, 'single_source': 3667}
control/russell        8            0        {'duplicate': 8, 'not_entity': 9, 'single_source': 210}
v2/russell             0            0        {'not_entity': 8, 'single_source': 802}
```

All 46 stored flows were duplicate-ingest pairs; all 46 are now counted as `duplicate`.

## The duplicate claim, checked two ways

1. The stored payload: the first control/santos flow is `<amanda.watson>`,
   `mail.info` → `mail.log`, both steps `user`, `events 893`, `first_seen 1642139896.0`,
   `last_seen 1642445389.0`. Every one of the 17 pairs has the same property (the replay
   attributes 17 of the 21 cross-source values to `duplicate`; the other 4 fail the entity gate).
2. The field records, independent of the flow payload: `mail.info` and `mail.log` each hold 17
   `user` values, 10,389 events in total, role `actor`, mechanism `stats` — one file ingested
   under two sourcetypes.

## What is not proved here

- **The positive path has no stored-run evidence.** Every `_v2` run has **0** values present in
  more than one source (`v2/santos` 1,464 values, `v2/kyoushi` 3,675, `v2/russell` 810), so the
  New flows column is 0 there for want of a candidate, not for want of a rule. The ordered
  ingress→later pair is proved by the unit fixture
  (`test_value_flow_orders_ingress_before_the_later_source`), which also exercises the tsidx
  host probe.
- **A live flow needs D2's vocabulary first.** On `_v2` the web and audit lists are still
  template slots (`access_combined: template/v3/v5`) and `linux_secure: program` is empty, so
  the estate never enumerates `c_ip`/`acct` for the flow to join on. The slice's live bar
  (`flows > 0` with `access_combined`/`dnsmasq` → `linux_audit`/`linux_secure` on one host)
  therefore depends on D2 landing and will read 0 until it does.

## Consumer side

`relate._flow_units` still applies its own role-transition gate; with the duplicates gone its
`flows_skipped` (recorded under `censored.flow_roles`) should fall to the residue of
same-role-but-different-plan pairs. The behaviour receipt now prints
`flows=<n> flows_skipped=<n> flow_skips={…}`.

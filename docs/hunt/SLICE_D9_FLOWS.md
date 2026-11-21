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
| status | a list is `complete` or `capped` (a capped list proves presence, never absence) | — |
| entity | `_entity_token` (an address, or a token with a letter, ≥4 chars) | `not_entity` |
| sources | present in ≥2, and no more than `FLOW_MAX_SOURCES` (12) sources | `single_source`, `ambient` |
| duplicate | the ingress step and *every* other source's step report a different span (`first_seen`,`last_seen`): the same span is the same raw events, seen twice | `duplicate` |
| order | the later step starts strictly after the ingress step | `order` |
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
- Candidates are taken **rarest first** (total events, then value), so the 64-flow budget and the
  16-probe host budget are spent on traverses rather than on ambient volume.
- Two observations of one value in the *same* second are read as a duplicate (identical span), so
  a genuine traverse inside one second is lost — the case layer still chains those episodes by
  entity key.

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

## Measured on the lab index, read-only — the positive path

No hunt run was issued (operator hold). The two capped domain lists were read straight from
`hb_ait_santos_v2` with the job API (`| tstats count min(_time) as first max(_time) as last …
by <field> host`), reshaped to D3's kept form (the 4,500 highest-count values plus the rarest
500, per list) and handed to the production `_flows`, with a stand-in prober answering the host
probes from the same aggregate. Nothing was written to the lab.

```
dnsmasq  dns_query   36,856 (value,host) rows over 567,569 events, 20,031 values -> kept 5,000
suricata dns.rrname  35,934 (value,host) rows over 192,480 events, 19,463 values -> kept 5,000
flows=64  host-proven=7  skips={'capped': 1104, 'duplicate': 2752, 'order': 109,
                                'single_source': 1940, 'host': 1}
```

- The DNSteal exfil domain (`3x6-…payroll_2014.xlsx.kiirjekuimkpcrcioastvkeodpnimx.biz`)
  appears as a flow `dnsmasq → suricata`, **host `inet-firewall`, proven** by the probe — an
  ingress observation and a later observation of one entity on one host.
- 2,752 domain pairs are `duplicate`: the same span in both sensors (dnsmasq and suricata log
  the same transaction; e.g. `0.s3.envato.com` is `count 2` in dnsmasq and `4` in suricata with
  identical `first`/`last`). Those are the "seen twice" class the rule exists to remove.
- 109 are `order` (same start), 1 `host` (probed and disjoint), 1,104 over the 64-flow budget.

Without capped lists this run has **no** candidate at all: every `_v2` stored run reports 0
values present in more than one source (`v2/santos` 1,464 values, `v2/kyoushi` 3,675,
`v2/russell` 810). Capped lists are therefore what makes the signal reachable on the
consolidated estate — the same reason D3 keeps their tail.

## What is not proved here

- **No hunt run.** The positive numbers above are the production function applied offline to
  live-read aggregates in D3's kept shape; the real run's list shape depends on its own
  `eventstats/sort/head` bounds, so the live count will differ. The ordered ingress→later pair
  also has a unit fixture (`test_value_flow_orders_ingress_before_the_later_source`), which
  exercises the tsidx host probe.
- **The slice's stated endpoint pair is still unreachable today.** `access_combined`'s lists are
  template slots (`template/v3/v5`) and `linux_secure: program` is empty on `_v2`, so the web→auth
  flow the acceptance names needs D2's vocabulary. What fires today is `dnsmasq → suricata`,
  which satisfies `flows > 0` on one host but is not the web→execution pair.
- **The host probe covers 8 candidates.** Beyond the 16-probe budget a flow keeps
  `host: ""`/`host_proven: false`; the live run should read `flows_proven` to see how many of the
  emitted flows are host-checked.

## Consumer side

`relate._flow_units` still applies its own role-transition gate; with the duplicates gone its
`flows_skipped` (recorded under `censored.flow_roles`) should fall to the residue of
same-role-but-different-plan pairs. The behaviour receipt now prints
`flows=<n> flows_skipped=<n> flow_skips={…}`.

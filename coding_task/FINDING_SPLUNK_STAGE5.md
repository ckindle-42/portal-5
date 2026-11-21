# FINDING — Splunk stage 5: the three live defects (2026-11-21)

Lane: `lane/splunk-stage5-fixes`. Brief: `coding_task/BRIEF_SPLUNK_STAGE5_FIXES.md`.

Diagnosis used the lab's REST API read-only (search jobs + GET only); keys were parsed by name
from `/Users/chris/projects/portal-5/.env`, never sourced. No config write was made.

## 1. `verify` reported `absent` because the endpoint has no `datamodel_name`

`| rest /services/admin/summarization by_tstats=t splunk_server=local count=0` returns rows keyed
by **`summary.id`**, not `datamodel_name`. The live ids are `DM_Splunk_SA_CIM_<Model>` for a model
root and `DM_Splunk_SA_CIM_Endpoint.Processes` for a child object; the live answer also has
`summary.complete` and `summary.size`, and no `datamodel_name` field at all. `_summaries_check`
looked up `row["datamodel_name"]`, so every model read `absent` and the count was `0/6` although
five roots were `complete = 1`.

Fix: key the rows on `summary.id` and read the exact root id `DM_<CIM_APP>_<Model>`; the child ids
are ignored. Verified live 2026-11-21: 10 rows, `Network_Resolution` the only `complete = 0`.

## 2. `Network_Resolution` was blocked three ways

The live model row's own `summary.last_error` is the accelerator's word for it:

```
Error in 'lookup' command: Could not construct lookup 'cim_dns_reply_code_lookup, ...'
```

and its base search shows the tag requirements:

```
search (index=* OR index=_) ((`cim_Network_Resolution_indexes`) tag=network tag=resolution tag=dns)
```

- **The CIM app's lookups are on the box as `<name>.csv.default`.** All 31 CIM lookup files are
  named that way (`eai:data = /opt/splunk/etc/apps/Splunk_SA_CIM/lookups/cim_dns_reply_codes2.csv.default`),
  while `conf-transforms` names `cim_dns_reply_codes2.csv`; `| inputlookup cim_dns_reply_code_lookup`
  answers "requires a .csv or KV store lookup definition". The accelerator therefore errors before
  reading a single row. `apply` now copies `cim_dns_reply_codes2.csv.default` to the plain name
  (only that file — the other 30 are the same defect and are reported, not repaired).
- **The app's eventtypes/tags were app-scoped.** They default to `sharing = app`, so they are only
  visible in `portal5_hunt_setup`'s context; the accelerator runs as `nobody` in `Splunk_SA_CIM`.
  Measured on the same data, `tag=process tag=report` = **28** in the app context and **0** in
  `Splunk_SA_CIM`. That is why only vendor-tagged models populated (TA-nix's `authentication`,
  TA-suricata's `network`/`dns`). The app now ships `metadata/default.meta` with `export = system`.
- **The DNS object needs `tag=dns`.** dnsmasq carried `network + resolution` only; both DNS
  eventtypes now carry `dns` too (`tag=dns` over dnsmasq = 0 before, 426,581 in the app context
  once the tag is applied). dnsmasq has no vendor TA, so without this tag it can never populate.
- **The model's fields were native names.** `dnsmasq` extracted `dns_query`/`src`, the model
  renames `query`/`src` into `Network_Resolution.query` etc. Search-time aliases added:
  `query = dns_query` (+ `dest = host`, `vendor_product = "dnsmasq"`) for dnsmasq and
  `query = dns.rrname` for suricata.

## 3. `Endpoint` is empty because the corpus has almost no exec records — map the ones it has

`linux_audit` in the three `_v2` indexes holds **28 `SYSCALL` records** (kyoushi 0, santos 4,
russellmitchell 24) out of ~67 k audit events; the rest are PAM/service/login types. The source
corpus agrees (grep `type=SYSCALL` over `.../audit/audit.log`: 0 in kyoushi, 4/24 in the AIT
families). The realism doc §5.2 expects `Endpoint.Processes/Filesystem` from `linux_audit`; the
data supports **Processes only, from 28 records**, and no Filesystem/Registry/Services stream.

Those 28 already carry `tag=endpoint tag=process tag=report`, and now they reach the accelerator
via the global export. Field aliases were added so the object is not all-null:
`process/process_name = comm`, `process_path = exe`, `process_id = pid`, `parent_process_id = ppid`.
`Endpoint`'s root summary is the `Ports` object (`tag=listening tag=port`) and stays empty; the
verification property is completeness, not size, so `verify` accepts it.

## Files

- `scripts/lab/splunk_setup/plan.py` — `dns` tag on both DNS eventtypes; CIM lookup filename.
- `scripts/lab/splunk_setup/conf.py` — DNS/process aliases; `metadata/default.meta` renderer.
- `scripts/lab/splunk_setup/host.py` — `ensure_lookup_file` (copy `.default` → plain name).
- `scripts/lab/splunk_setup/cli.py` — summaries keyed on `summary.id`; apply repairs the lookup.
- `scripts/lab/splunk_setup/app/portal5_hunt_setup/**` — regenerated tree + `metadata/default.meta`.
- `tests/unit/test_splunk_setup.py` — summaries-id fake, global/alias test, lookup-repair test.
- `docs/hunt/SPLUNK_SETUP_RUNBOOK.md`, `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` — measured facts.

## Unproven

- That the copy restores the lookup and the model then completes: needs a live `apply` + rebuild.
- That `export = system` makes the accelerator see the tags: proved only as a context difference in
  searches, not by an accelerator run after the metadata is loaded.

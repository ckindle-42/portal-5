# FINDING — Hunt S1 Tier B (wide-source enumeration)

Lane `lane/hunt-s1b`, base `475e994f1` (main at dispatch). Work is on top of Tier A
(`745475db3`). Files: `notables/inventory.py`, the inventory print in `notables/__main__.py`,
`tests/unit/test_hunt_inventory.py`; +87 test lines, 0 removed.

## What Tier B is

Plan §S1 Tier B: **a complete list over a wide source (`wineventlog:security` 2.18 M or
`winregistry` 55.5 M) in ≤ 5 s, via `tstats from datamodel=…` or `tstats by <indexed entity>`.**

Tier A already probes the name and the field and picks `tstats` vs `stats`. What it did not do:

1. **No accelerated path.** `accel_window` was hard-coded `null` on every list, and a role field
   absent from the tsidx fell straight to a full `stats` scan — 72.8 s on the named source, or
   `unavailable:mechanism` above the 2 M-event budget. The documented stage-3 output
   (`| tstats summariesonly=true … from datamodel=…`) was unused.
2. **A partition predicate was part of the name probe.** `tstats count where … <part>=<value>`
   is a read filter; a source's name is not defined by its partition.
3. **A joint could scan a wide source.** `_enumerate_joints` had no events-budget guard, so two
   complete lists on a wide card could trigger a full `stats` scan after the field lists had
   correctly refused it.

## What changed

- **Accelerated rung.** One probe of `| rest /services/admin/summarization by_tstats=1
  | fields datamodel_name summary.earliest_time summary.latest_time summary.complete` names the
  models whose summary is **complete** (`summary.complete >= 1`, a fraction, not a percentage).
  For a wide source (`events >= 250 k`) whose field is not in the tsidx, each model's aggregate
  is its own probe:
  `| tstats summariesonly=true count min(_time) as first max(_time) as last from datamodel=<M>
  where index=<I> sourcetype=<tsidx name> by <M>.<field>`.
  A model that returns no rows costs ~0.1 s and falls through to the `stats` rung; it can never
  report a list it did not produce. The sourcetype predicate keeps the list attributable to the
  card instead of the whole model population.
- **Receipt.** Every list carries `accel_window` (`[earliest, latest]` of the summary, `null` for
  a non-summary read) and `searched_window` (`[start, end]` of the query), as
  `SPLUNK_REALISM_AND_SETUP.md` §6 rule 4 requires. The document carries `accelerated` (models +
  windows) and `model_probes`; the stage print shows both.
- **Name probe** no longer carries a partition predicate.
- **Joint guard.** A joint that would be a `stats` scan above the 2 M-event budget is now
  `unavailable:mechanism` (`reason: events_budget`) instead of an unbounded scan.
- **Field selection is unchanged.** The plan's budget policy is "role first, then smallest
  list"; widening or round-robining it would change the list set on the scored botsv2 run.
  Where the 32-search budget leaves a wide source's list out, that is visible in
  `inventory.json` (`fields_selected`, `lists`) and is a follow-up decision, not silently
  worked around.

## Acceptance → proof

Tier B has two halves; the lab can prove the indexed half now (stage 2 wrote the entity fields)
and the accelerated half only after stage 3.

### A. `tstats by <indexed entity>` on a wide `_v2` source — provable now

```bash
# cards first (needs the Pipeline model), then the enumeration stage against the same run dir
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099 PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out coding_task/scratch/s1b-live/santos --stage cards
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out coding_task/scratch/s1b-live/santos --stage behaviours
```

Read the widest list:

```bash
uv run python -c 'import json; d=json.load(open("coding_task/scratch/s1b-live/santos/inventory.json")); print("accel", d["accelerated"], "model_probes", d["model_probes"], "fail", d["probe_failures"]); [print(r["mechanism"], r["name_used"], r["field"], r["status"], r["seconds"], r["events_scanned"], r.get("accel_window"), r.get("searched_window"), len(r["values"])) for r in sorted(d["fields"], key=lambda r: -(r.get("events_scanned") or 0))[:10]]'
```

**Pass:** at least one row `tstats <name> <field> complete < 5.0 <events_scanned> None [start,end]
>0` over a source with ~1 M events (`suricata` / `access_combined` on santos). **Fail:** the row
is `stats` (a scan), `seconds >= 5`, or `unavailable:name`.

Direct Splunk probe (same read the code issues):

```spl
| tstats count min(_time) as first max(_time) as last
  where index=hb_ait_santos_v2 sourcetype="suricata" by src_ip
```

**Pass:** >0 rows, ~1–3 s, index-size independent.

### B. `tstats from datamodel=` after stage 3 — after `apply --accelerate`

```spl
| tstats summariesonly=true count from datamodel=Authentication where index=hb_ait_santos_v2 sourcetype="linux_audit" by Authentication.user
| tstats summariesonly=true count from datamodel=Authentication where index=hb_ait_santos_v2 by Authentication.user
```

**Pass:** the first returns >0 rows (the summaries carry `sourcetype`, so the hunt's scoped
query works). If only the second does, summaries do not carry `sourcetype`; the hunt's rung
returns 0 and falls back — see OPEN.

Then re-run the `--stage behaviours` command above; `inventory.json` gains
`accelerated: [{model, earliest, latest}]`, and any list served from a summary shows
`mechanism: datamodel`, `name_used: "<Model>:<sourcetype>"`, a non-null `accel_window` and
`searched_window ⊆ accel_window`. A model whose `summary.complete < 1` is never used.

### C. Honest negative — no model, wide source

`inventory.json` shows `status: unavailable:mechanism`, `reason: events_budget` — never `empty`,
and no `| stats ` query is issued for that list. Covered by
`test_a_wide_source_with_no_accelerated_model_is_unavailable_not_empty`.

## Limits / what this does not do

- **Model field qualification is the model name.** `Authentication.user` / `Web.user` are the
  documented form. A CIM model whose root dataset is named differently (`Network_Traffic` →
  `All_Traffic`, `Network_Resolution` → `DNS`, `Intrusion_Detection` → `IDS_Attacks`,
  `Endpoint` → child objects) returns 0 rows under this prefix and falls through to
  `stats`/`unavailable`. Resolving it needs the model JSON's object path (`| rest
  /services/data/models/<m> | fields eai:data`), which is deliberately not added blind here.
- **Stage 4 summaries are not consumed as per-source lists.** The documented marker is
  `hunt_entities_index=<index>` + `hunt_source=portal5_hunt_setup`; it names no sourcetype or
  partition, and the collect is a snapshot, so it cannot honestly back a per-source `complete`
  status. S2, which knows the source, is the right consumer.
- **No live run.** This lane was not allowed to hunt; every live claim below is unproven.

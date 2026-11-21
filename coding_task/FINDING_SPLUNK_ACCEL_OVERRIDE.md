# FINDING — Splunk stage 3 acceleration belongs to Splunk_SA_CIM (2026-11-21)

Lane: `lane/splunk-accel-override`. Brief: `coding_task/BRIEF_SPLUNK_ACCEL_OVERRIDE.md`.
Code complete, gates green, unproven against the live box — the orchestrator runs it.

## What was wrong

`apply --accelerate` rendered `portal5_hunt_setup/default/datamodels.conf` with `acceleration =
true` and `acceleration.earliest_time = -10y` for the six models, installed it and restarted. The
model endpoint still answered `enabled: False`, earliest `-1y` / `-3mon`, and no summary was built
(measured live 2026-11-21). Same app-precedence failure the `cim_*_indexes` macros had: the data
model object is Splunk_SA_CIM's, so a row in another app loses to the CIM app's own default.

The conf row is not the property. The property is what
`GET /servicesNS/nobody/Splunk_SA_CIM/datamodel/model/<Model>` reports.

## What now owns it

- `rest.SplunkREST.datamodel_acceleration(app, model)` reads that endpoint and normalises the
  reported `acceleration` object (or flat `acceleration.*` keys) to `{"enabled": bool,
  "earliest_time": str, …}`.
- `rest.SplunkREST.ensure_datamodel_acceleration(app, model, settings)` writes the four keys to
  `configs/conf-datamodels/<Model>` **in Splunk_SA_CIM** and only when the model does not already
  report enabled over the window — idempotent on the property, not on the row.
- `cli.cmd_apply --accelerate` runs that after the restart (`cli._accelerate`), so the read sees
  the post-install state. Plain `apply` writes nothing to the CIM app.
- `rest.SplunkREST.revert_datamodel_acceleration(app, model)` deletes the local row, so the model
  reports the CIM app's own default again (`enabled: false`, its own `earliest_time`) — `rollback`
  calls it for the seven models (like the macros, `--with-change` included) and re-reads to report
  what the model says afterwards.
- `cli._datamodel_probes` + `verify --accelerate` fail per model unless the endpoint reports
  `enabled` over `-10y`; the row `reported` is in the probe output, so a failure shows
  `reports enabled=False -1y`. `--accelerate` is a flag because stage 1/2 `verify` runs before
  acceleration exists and must not fail on it.
- `datamodels.conf` is gone from the renderer and from the committed app tree, and
  `plan.LEGACY_CONF_FILES` makes `conf.write_app` drop a stale local copy and
  `host.install_command` `rm -f` the box's copy before the tar extract (tar overwrites, it never
  deletes). Without that, the dead file would still be in the app and could make the live proof
  pass while the CIM write was broken.
- Runbook: stage 1's conf table, stage 3's what-it-does / verification / rollback, stage 5's probe
  table, and §6's measured/estimated table. Stage 3's summary query is now
  `| rest /services/admin/summarization by_tstats=t | table datamodel_name summary.size
  summary.complete` (the endpoint has no `title` / `summary_size` fields, so the old query returned
  no rows and read as "nothing accelerated").

## Acceptance properties and their proofs

| property | proof |
|---|---|
| `apply --accelerate` writes the four settings into Splunk_SA_CIM, idempotently | `tests/unit/test_splunk_setup.py::test_acceleration_is_written_where_the_model_reports_it` — the fake only honours a POST to Splunk_SA_CIM; the second run issues no write |
| `rollback` restores the CIM defaults | same test: the DELETE of the local row returns the model to `fake.defaults`, and a second rollback is a no-op |
| `verify` asserts the model endpoint, not the conf row | `tests/unit/test_splunk_setup.py::test_verify_fails_a_model_that_reports_no_acceleration` — `-1y` fails even with `enabled: true`; `-3mon` fails; enabled/`-10y` passes |
| the dead `datamodels.conf` is gone from the app, the renderer and the next install | `test_shipped_conf_is_rendered_from_the_plan_and_extracts` — not rendered, not in the committed tree, a stale copy is unlinked, `install_command` names the `rm -f` |

Net test lines: **+103 / −8**, two tests added, none deleted.

## Unproven (live only)

- **`DELETE /servicesNS/nobody/Splunk_SA_CIM/configs/conf-datamodels/<Model>`** is the one REST verb
  here that was not in the orchestrator's measured fix. If Splunk refuses it, `rollback` stops with
  the status in the message; the manual equivalent is
  `POST …/configs/conf-datamodels/<Model> -d acceleration=false`, which leaves the written
  `earliest_time` in place but does disable the model.
- **What the endpoint reports as `earliest_time`.** The idempotency check compares it to `-10y`
  literally. If Splunk normalises the value (epoch, `-3650d`), every `apply --accelerate` rewrites
  and `verify --accelerate` fails — the `reported` field of the probe shows it in one line.
- **`host.install_command`'s `sh -c 'rm -f … && exec tar …'`** through `pct exec` → `docker exec`:
  reasoned from the existing transport, not run. A quoting failure shows as `app install failed`.
- Nothing was applied to the lab box from this lane; no summary was read.

# FINDING — Splunk `verify` aborted on "no parser expansion returned" (stage 5, 2026-11-21)

Lane: `lane/splunk-verify-parser`. Brief: `coding_task/BRIEF_SPLUNK_VERIFY_PARSER.md`.

## What was wrong

`rest.SplunkREST.macro_expansion` ran `` search `cim_Authentication_indexes` | head 0 `` as a
search **job** and read `normalizedSearch`/`optimizedSearch` from
`GET /services/search/jobs/<sid>`'s `content`. A job's content entry does not carry those keys —
the normalized search lives in the **parser** response, not the job — so the field was always
`""` and the first macro check raised `SplunkError`, which `main()` turned into exit 2. The whole
pass died before any check ran.

The parser does expand the macro; the brief's manual call proves the working shape:
`POST /servicesNS/nobody/search/search/parser` with `q=search `cim_Web_indexes`` and
`output_mode=json` returns `normalizedSearch` = `litsearch (index=hb_kyoushi_s1_v2 OR …)`.

## The fix

- `macro_expansion` now calls that endpoint (POST, `q` = the invocation, `nobody/search`
  namespace) and reads the top-level `normalizedSearch`. `SearchResult.normalized_search` was
  removed — nothing else read it.
- `verify` no longer lets one check end the run: every check is wrapped, and a raised
  `SplunkError`/`RuntimeError` becomes that check's `{"ok": false, "detail": "<error>"}` row.
  Exit is 0 when every row is ok and 1 when any row failed; 2 is no longer reachable from
  `verify`.
- Output is one JSON row per check, exactly `{"name", "ok", "detail"}`, on stdout; per-check
  progress lines go to stderr.
- The pass now also reports the stage-3/stage-4 properties the brief names, so stage 5 is a
  single read-only pass over the whole setup:
  - `acceleration_window` — all six `plan.ACCELERATED` models at `acceleration.earliest_time =
    -10y` (via the existing `| rest …/data/models` probe; the pre-state showed `-1y`/`-3mon`/`-1mon`).
  - `summaries_complete` — six `/services/admin/summarization` entries (`by_tstats=t`) with
    `summary.complete = 1`.
  - `summary_index:<source_index>` ×3 — `index=summary hunt_entities_index=<index> | stats count`
    is non-zero.
- Rebased onto `splunk-accel-override` (`cd5d81927`): stage 3's per-model property is now a row
  too — `acceleration:<Model>` ×6, from the model endpoint, only under `--accelerate` (that lane's
  check). `apply --accelerate`, `rollback`'s acceleration revert and the `-10y` window check are
  unchanged. The summaries query was corrected to the fields the endpoint has
  (`datamodel_name`, `summary.complete`, `summary.size`) — the accel lane measured that `title` and
  `summary_size` return no rows.

## Proof run offline (no live stack touched)

`uv run python -m scripts.lab.splunk_setup verify --offline` → exit **1**, 14 rows, keys exactly
`detail`/`name`/`ok`, every row a FAIL carrying its own `SplunkError` (the offline transport
raises), and all 14 checks attempted. Before the change the same command exited 2 on the first
macro and printed no JSON. `--index santos` → 19 rows; `--index santos --accelerate` → 25.

The parser request shape is asserted in
`tests/unit/test_splunk_setup.py::test_macro_expansion_reads_the_parser_endpoint` (method, path,
`q`, response key), the FAIL-row/no-abort and row-schema properties in
`test_verify_judges_the_parser_expansion_not_the_conf_row`, and the `--accelerate` model rows in
`test_verify_fails_a_model_that_reports_no_acceleration`.

## Unproven

Everything against the live instance: that Splunk 10.2.5 actually returns `normalizedSearch` at
the top level of the parser response (the brief's manual call did, but this lane is offline), and
that `/services/admin/summarization` names the six models with `summary.complete = 1` (the field
set is the accel lane's measured query; this lane did not run it).

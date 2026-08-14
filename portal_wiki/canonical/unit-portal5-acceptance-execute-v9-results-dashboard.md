---
id: unit-portal5-acceptance-execute-v9-results-dashboard
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Results + dashboard"
sources:
- type: code
  path: scripts/update_grafana_acceptance.py
- type: code
  path: tests/lib/results.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.696529
updated_at: 1784946220.696529
---

After a run completes, the results file is written to the repository root as
`ACCEPTANCE_RESULTS.md` by `_write_results` in `tests/lib/results.py`, carrying
the date, git SHA, section list, runtime, summary counts, and one row per
check. To publish it, run `scripts/update_grafana_acceptance.py --input
ACCEPTANCE_RESULTS.md`. The explicit `--input` path matters because the script's
default (the `RESULTS_FILE` constant) points at a `tests/`-tree location for the
results file while the runner writes the file to the repo root. The
script parses the markdown table, rewrites the dashboard JSON at
`config/grafana/dashboards/portal5_acceptance.json`, and archives a JSONL
snapshot into `tests/acceptance_corpus/` for the run-trend panel.

Then stage and commit the results and the dashboard together, with a message
that records the run date, the section count, and the pass/total figures, so
the commit history itself shows the outcome of each acceptance run.

## Why

The dashboard and the results file are the durable record of an acceptance run,
and keeping them in sync matters because the Grafana panels are rendered from
the markdown, not authored by hand. The corpus archive additionally preserves a
time series so a section's pass rate can be compared across runs. Wiring the
runner's output path and the updater's input path explicitly prevents the two
sides from silently pointing at different files.

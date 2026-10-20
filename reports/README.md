# reports/ — moved out of the checkout

Raw run output from this directory now lives under `${PORTAL_DATA_ROOT}`
(default `~/AI_Output/portal-data`), mirroring the old relative path:
`${PORTAL_DATA_ROOT}/reports/`. Curated decision summaries stay in `docs/`,
and a doc that cites a moved run names its data-root path and run id.

New runs write only to the data root; the pre-commit path rule rejects
`*.json`, `*.jsonl` and `*.csv` added here.

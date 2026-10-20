# tests/wfe/results/ — moved out of the checkout

WFE campaign manifests, rows and debug captures now live under
`${PORTAL_DATA_ROOT}` (default `~/AI_Output/portal-data`), mirroring this path:
`${PORTAL_DATA_ROOT}/tests/wfe/results/`. The harness default points there, so a
new campaign writes nothing here.

The pre-commit path rule rejects `*.json`, `*.jsonl` and `*.csv` added here.

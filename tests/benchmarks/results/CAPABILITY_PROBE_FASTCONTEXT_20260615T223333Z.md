# Coding Capability Probe — Matrix

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-15T23:56:38Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D4 LongCtx | D6 Security | D7 Domain | D8 PowerShell | D9 PyProd | D10 SecAPI |
|---|---|---|---|---|---|---|
| bench-fastcontext | 1/1 | 0/1 | 2/3 | 1/5 | 0/4 | 0/10 |

## Per-cell detail

- `bench-fastcontext` D10 sec1-nessus-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec10-bigfix-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec2-splunk-search: **FAIL** — no code block in response
- `bench-fastcontext` D10 sec3-solarwinds-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec4-tripwire-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec5-mssql-query: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec6-ssrs-deploy: **FAIL** — no code block in response
- `bench-fastcontext` D10 sec7-changegear-api: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   7 | [0m         [string][36;1m [0m-Uri ($Ba
- `bench-fastcontext` D10 sec9-changegear-powershell: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D4 d4-targeted-change: **PASS** — expected stdout matched
- `bench-fastcontext` D6 d6-modbus-fuzzer: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D7 d7-modbus-parser: **PASS** — expected stdout matched
- `bench-fastcontext` D7 d7-nerc-cip-mapping: **PASS** — expected stdout matched
- `bench-fastcontext` D7 d7-scada-event-correlate: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D8 ps1-pipeline-filter: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-fastcontext` D8 ps3-log-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D8 ps4-json-transform: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D8 ps5-retry-block: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D9 py1-argparse-cli: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D9 py2-subprocess-safe: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D9 py3-retry-fn: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-fastcontext` D9 py4-deep-merge: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500

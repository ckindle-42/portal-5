# Coding Capability Probe — Matrix (V1)

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-13T03:15:01Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D1 Correct | D2 Debug | D3 Constraint | D4 LongCtx | D5 MultiTurn | D6 Security | D7 Domain |
|---|---|---|---|---|---|---|---|
| bench-deepseek-coder-v2 | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-devstral-small-2 | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-gemma4-12b-coder | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-glm | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-laguna | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-omnicoder2 | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-qwen3-coder-30b | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-qwen3-coder-next | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-qwen36-27b | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-qwopus-coder-mtp | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |
| bench-starcoder2 | 0/3 | 0/3 | 0/3 | 0/1 | 0/1 | 0/3 | 0/3 |

## Per-cell detail

- `bench-deepseek-coder-v2` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-deepseek-coder-v2` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-devstral-small-2` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-gemma4-12b-coder` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-glm` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-laguna` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-omnicoder2` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-30b` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen3-coder-next` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwen36-27b` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-qwopus-coder-mtp` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D1 d1-binary-search: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D1 d1-lru-cache: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D1 d1-pandas-transform: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D2 d2-async-race: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D2 d2-mutation-bug: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D2 d2-off-by-one: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D3 d3-httpx-retry: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D3 d3-signature-and-edge: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D3 d3-stdlib-only-csv: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D4 d4-targeted-change: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D5 d5-stack-iterate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D6 d6-injection-review: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D6 d6-log-scrub: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D6 d6-modbus-fuzzer: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D7 d7-modbus-parser: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D7 d7-nerc-cip-mapping: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
- `bench-starcoder2` D7 d7-scada-event-correlate: **FAIL** — harness error: Client error '401 Unauthorized' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401

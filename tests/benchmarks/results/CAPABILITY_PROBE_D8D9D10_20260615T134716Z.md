# Coding Capability Probe — Matrix

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-15T15:48:04Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D8 PowerShell | D9 PyProd | D10 SecAPI |
|---|---|---|---|
| bench-deepseek-coder-v2 | 3/5 | 1/4 | 6/9 |
| bench-devstral-small-2 | 3/5 | 2/4 | 8/9 |
| bench-gemma4-12b-coder | 0/5 | 0/4 | 0/9 |
| bench-glm | 4/5 | 1/4 | 7/9 |
| bench-granite41-30b | 0/5 | 0/4 | 0/9 |
| bench-granite41-8b | 0/5 | 0/4 | 0/9 |
| bench-harness1 | 0/5 | 0/4 | 0/9 |
| bench-laguna | 5/5 | 2/4 | 6/9 |
| bench-lfm25-8b | 0/5 | 0/4 | 0/9 |
| bench-omnicoder2 | 2/5 | 1/4 | 3/9 |
| bench-qwen3-coder-30b | 3/5 | 2/4 | 9/9 |
| bench-qwen3-coder-next | 4/5 | 2/4 | 7/9 |
| bench-qwen36-27b | 0/5 | 0/4 | 0/9 |
| bench-qwopus-coder-mtp | 0/5 | 0/4 | 0/9 |
| bench-r1-0528-abliterated | 0/5 | 0/4 | 0/9 |
| bench-r1-0528-qwen3-8b | 0/5 | 0/4 | 0/9 |
| bench-starcoder2 | 0/5 | 0/4 | 0/9 |

## Per-cell detail

- `bench-deepseek-coder-v2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 42, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-deepseek-coder-v2` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 12, in <module>
    q = build_ssrs_dataset_query("[dbo].[Securit
- `bench-deepseek-coder-v2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 1 open change, got 2[0m

- `bench-deepseek-coder-v2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mMethod wrong: [0m

- `bench-deepseek-coder-v2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  25 | [0m …    throw "Non-retryable error encou
- `bench-deepseek-coder-v2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-deepseek-coder-v2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 33, in <module>
    with_retry(always_fail, max_attempts=2)
  Fi
- `bench-deepseek-coder-v2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 21, in <module>
    assert r["b"] == {"x": 10, "y": 99, "z": 30}
- `bench-devstral-small-2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 38, in <module>
    r = parse_nessus_vulns(data)
        ^^^^^^^
- `bench-devstral-small-2` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  25 | [0m             cs[36;1m-[0mmethod     
- `bench-devstral-small-2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mException: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  19 | [0m …             [36;1mthrow ("Max retrie
- `bench-devstral-small-2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-devstral-small-2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 21, in <module>
    assert r["a"] == 1, f"a={r['a']}"
          
- `bench-gemma4-12b-coder` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-gemma4-12b-coder` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-glm` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 76, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-glm` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-glm` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-glm` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-glm` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-glm` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-glm` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mConvertTo-Json: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  16 | [0m     } | ConvertTo-Json [36;1m-NoT
- `bench-glm` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-glm` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-glm` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-glm` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mWriteError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   6 | [0m         [36;1m$host = $_.host[0m
[3
- `bench-glm` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-glm` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-glm` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 5, in run_command
    result = subprocess.run(cmd, timeout=timeo
- `bench-glm` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-glm` D9 py4-deep-merge: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-granite41-30b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-granite41-30b` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-granite41-30b` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-granite41-30b` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-granite41-30b` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-granite41-30b` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-granite41-30b` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-granite41-30b` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-granite41-30b` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-granite41-30b` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-granite41-30b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-granite41-8b` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-granite41-8b` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-granite41-8b` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-granite41-8b` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-granite41-8b` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-granite41-8b` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-granite41-8b` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-granite41-8b` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-granite41-8b` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-granite41-8b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-harness1` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-harness1` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-harness1` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-harness1` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-harness1` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-harness1` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-harness1` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-harness1` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-harness1` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-harness1` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-harness1` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-harness1` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-harness1` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-harness1` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-harness1` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-harness1` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-harness1` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-harness1` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-laguna` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 65, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-laguna` D10 sec2-splunk-search: **FAIL** — exit 1:   File "/code", line 12
    (| where {where_clauses})
     ^
SyntaxError: f-string: invalid syntax

- `bench-laguna` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-laguna` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-laguna` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-laguna` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-laguna` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-laguna` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-laguna` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-laguna` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-laguna` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-laguna` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-laguna` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-laguna` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-laguna` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-laguna` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 24, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-lfm25-8b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-lfm25-8b` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-lfm25-8b` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-lfm25-8b` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-lfm25-8b` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-lfm25-8b` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-lfm25-8b` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-lfm25-8b` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-lfm25-8b` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-lfm25-8b` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-lfm25-8b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-omnicoder2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 43, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-omnicoder2` D10 sec2-splunk-search: **FAIL** — exit 1:   File "/code", line 5
    f'| fields {fields_str}${', ']
                                ^
SyntaxError: unterminated st
- `bench-omnicoder2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 42, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-omnicoder2` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 55, in <module>
    q = build_ssrs_dataset_query("[dbo].[Securit
- `bench-omnicoder2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mConvertFrom-Json: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  29 | [0m …           -Headers $headers -U
- `bench-omnicoder2` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m 117 | [0m         $queryBuild = [[36;1m{[0m

- `bench-omnicoder2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-omnicoder2` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  10 | [0m         .AppendNull([36;1m)[0m; Set
- `bench-omnicoder2` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   9 | [0m         return [[36;1m][0m, PSCusto
- `bench-omnicoder2` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  22 | [0m … name":"memory","value":75,"warn":85
- `bench-omnicoder2` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-omnicoder2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] <COMMAND> ...
code: error: unrecognized arguments: --verbose

- `bench-omnicoder2` D9 py2-subprocess-safe: **FAIL** — exit 1:   File "/code", line 34
    if cmd and (error_str.startswith('No such file') or error_str.startswith('[Errno ') and 'fil
- `bench-omnicoder2` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 35, in <module>
    assert with_retry(flaky) == "ok"
           
- `bench-omnicoder2` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec1-nessus-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  27 | [0m                 cs[36;1m-[0mmethod 
- `bench-qwen3-coder-30b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mException: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  19 | [0m                 [36;1mthrow "Max retri
- `bench-qwen3-coder-30b` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwen3-coder-30b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-qwen3-coder-next` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 74, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-qwen3-coder-next` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 37, in <module>
    assert "[dbo].[SecurityEvents]" in q, f"tabl
- `bench-qwen3-coder-next` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  30 | [0m                     cs[36;1m-[0mmet
- `bench-qwen3-coder-next` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwen3-coder-next` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 57, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-qwen36-27b` D10 sec1-nessus-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec2-splunk-search: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec3-solarwinds-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec4-tripwire-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec5-mssql-query: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec6-ssrs-deploy: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec7-changegear-api: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec8-ssrs-powershell: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D10 sec9-changegear-powershell: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D8 ps1-pipeline-filter: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D8 ps2-error-handling: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D8 ps3-log-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D8 ps4-json-transform: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D8 ps5-retry-block: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D9 py1-argparse-cli: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D9 py2-subprocess-safe: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D9 py3-retry-fn: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwen36-27b` D9 py4-deep-merge: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-qwopus-coder-mtp` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D8 ps1-pipeline-filter: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D8 ps2-error-handling: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D8 ps3-log-parse: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D8 ps4-json-transform: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D9 py2-subprocess-safe: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec1-nessus-parse: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec2-splunk-search: **FAIL** — exit 1:   File "/code", line 3
    "content": {"rows": 9}, "messages: null,
                            ^
SyntaxError: untermina
- `bench-starcoder2` D10 sec3-solarwinds-parse: **FAIL** — harness error: Server disconnected without sending a response.
- `bench-starcoder2` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-starcoder2` D8 ps1-pipeline-filter: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps2-error-handling: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps3-log-parse: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps4-json-transform: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps5-retry-block: **FAIL** — no code block in response
- `bench-starcoder2` D9 py1-argparse-cli: **FAIL** — no code block in response
- `bench-starcoder2` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    r2 = run_command(['sh', '-c', 'exit 1'])
   
- `bench-starcoder2` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 29, in <module>
    assert False, "Should raise"
           ^^^^
- `bench-starcoder2` D9 py4-deep-merge: **FAIL** — exit 1:   File "/code", line 1
    @memoize def foo(x: Any) -> None:
             ^^^
SyntaxError: invalid syntax


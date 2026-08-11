# Coding Capability Probe — Matrix

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-15T19:29:27Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D8 PowerShell | D9 PyProd | D10 SecAPI |
|---|---|---|---|
| bench-deepseek-coder-v2 | 3/5 | 2/4 | 5/9 |
| bench-devstral-small-2 | 3/5 | 3/4 | 8/9 |
| bench-gemma4-12b-coder | 0/5 | 0/4 | 0/9 |
| bench-glm | 4/5 | 4/4 | 7/9 |
| bench-granite41-30b | 0/5 | 0/4 | 0/9 |
| bench-granite41-8b | 0/5 | 0/4 | 0/9 |
| bench-harness1 | 0/5 | 0/4 | 0/9 |
| bench-laguna | 5/5 | 3/4 | 7/9 |
| bench-lfm25-8b | 0/5 | 0/4 | 0/9 |
| bench-omnicoder2 | 2/5 | 2/4 | 4/9 |
| bench-qwen3-coder-30b | 3/5 | 2/4 | 9/9 |
| bench-qwen3-coder-next | 4/5 | 3/4 | 7/9 |
| bench-qwen36-27b | 5/5 | 3/4 | 7/9 |
| bench-qwopus-coder-mtp | 4/5 | 2/4 | 0/9 |
| bench-r1-0528-abliterated | 0/5 | 0/4 | 0/9 |
| bench-r1-0528-qwen3-8b | 0/5 | 0/4 | 0/9 |
| bench-starcoder2 | 0/5 | 0/4 | 0/9 |

## Per-cell detail

- `bench-deepseek-coder-v2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 1, in <module>
    import stdlib
ModuleNotFoundError: No module 
- `bench-deepseek-coder-v2` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 44, in <module>
    assert len(results) == 2, f"Expected 2 rows,
- `bench-deepseek-coder-v2` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 34, in <module>
    reports = parse_ssrs_catalog(catalog)
      
- `bench-deepseek-coder-v2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mNew-ChangeGearTicket: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  74 | [0m $r = [36;1mNew-ChangeGearTi
- `bench-deepseek-coder-v2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 3 rows, got 0[0m

- `bench-deepseek-coder-v2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps5-retry-block: **FAIL** — expected 'PS5_RETRY_OK' not in stdout: Attempt 1 failed: HTTP 429 Too Many Requests

- `bench-deepseek-coder-v2` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    with_retry(always_fail, max_attempts=2)
  Fi
- `bench-deepseek-coder-v2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 28, in <module>
    assert r2["k"] == "keep", f"None should not 
- `bench-devstral-small-2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 27, in <module>
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
[31;1m[36;1m[36;1m  21 | [0m                     cs[36;1m-[0mmet
- `bench-devstral-small-2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mException: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  32 | [0m     if ($script:n -lt 3) { [36;1mthrow
- `bench-devstral-small-2` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 21, in <module>
    assert r["d"] is None  # None is set if key 
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
  File "/code", line 68, in <module>
    assert r["summary"]["total"] == 5
          
- `bench-glm` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-glm` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 51, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-glm` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-glm` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-glm` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-glm` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-glm` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-glm` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-glm` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-glm` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mWriteError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   8 | [0m     $result = foreach ([36;1m$host[0
- `bench-glm` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-glm` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-glm` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-glm` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-glm` D9 py4-deep-merge: **PASS** — expected stdout matched
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
  File "/code", line 62, in <module>
    tc = r["top_critical"]
         ~^^^^^^^^^^^
- `bench-laguna` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-laguna` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec5-mssql-query: **FAIL** — exit 1:   File "/code", line 8
    return [{'username': row[0], 'ip_address': row[1], 'event_time': row[2]} for row in cursor.fe
- `bench-laguna` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-laguna` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-laguna` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-laguna` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-laguna` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-laguna` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-laguna` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-laguna` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-laguna` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-laguna` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-laguna` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-laguna` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-laguna` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
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
  File "/code", line 22, in <module>
    r = parse_nessus_vulns(data)
        ^^^^^^^
- `bench-omnicoder2` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 28, in <module>
    assert "sourcetype=wineventlog" in spl
     
- `bench-omnicoder2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 31, in <module>
    assert "[dbo].[SecurityEvents]" in q, f"tabl
- `bench-omnicoder2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mException: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  18 | [0m         Invoke-RestMethod -Uri "$([36;
- `bench-omnicoder2` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m 149 | [0m [36;1m}[0m
[31;1m[36;1m[36;1m[0
- `bench-omnicoder2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-omnicoder2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-omnicoder2` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mMethod wrong: [0m

- `bench-omnicoder2` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mcpu@srv1 should be WARN, got [0m

- `bench-omnicoder2` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  13 | [0m …        for ($attempt = 1; $attempt 
- `bench-omnicoder2` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-omnicoder2` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 46, in <module>
    assert r3['returncode'] == -2, f"rc={r3['ret
- `bench-omnicoder2` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-omnicoder2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 31, in <module>
    assert r["d"] is None  # None is set if key 
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
- `bench-qwen3-coder-30b` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mNon-retryable should not retry, got 5 attempts[0m

- `bench-qwen3-coder-30b` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 2, in <module>
    import requests
ModuleNotFoundError: No modul
- `bench-qwen3-coder-30b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 33, in <module>
    assert r2["k"] == "keep", f"None should not 
- `bench-qwen3-coder-next` D10 sec1-nessus-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 40, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-qwen3-coder-next` D10 sec6-ssrs-deploy: **FAIL** — exit 1:   File "/code", line 9
    date_field_name = f"[{date_field.replace(']", "]]")}]"
                                      
- `bench-qwen3-coder-next` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  14 | [0m                 Status = if ($checkPS
- `bench-qwen3-coder-next` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 35, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-qwen36-27b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-qwen36-27b` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 28, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-qwen36-27b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-qwen36-27b` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-qwen36-27b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen36-27b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen36-27b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec2-splunk-search: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec3-solarwinds-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec4-tripwire-parse: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec6-ssrs-deploy: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec7-changegear-api: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec8-ssrs-powershell: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec9-changegear-powershell: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  30 | [0m     [36;1m}[0m
[31;1m[36;1m[36;1
- `bench-qwopus-coder-mtp` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D9 py3-retry-fn: **FAIL** — harness error: Server disconnected without sending a response.
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
- `bench-starcoder2` D10 sec2-splunk-search: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec3-solarwinds-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-starcoder2` D10 sec4-tripwire-parse: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec5-mssql-query: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec6-ssrs-deploy: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 14, in <module>
    assert my_add(0, (), [2]) == [2]
           
- `bench-starcoder2` D10 sec8-ssrs-powershell: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec9-changegear-powershell: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps1-pipeline-filter: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mNew-Item: [31;1mCannot find drive. A drive with the name 'd' does not exist.[0m
[31;1mInvoke-SafeBlock: [0m

- `bench-starcoder2` D8 ps3-log-parse: **FAIL** — harness error: Server error '500 Internal Server Error' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500
- `bench-starcoder2` D8 ps4-json-transform: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps5-retry-block: **FAIL** — no code block in response
- `bench-starcoder2` D9 py1-argparse-cli: **FAIL** — no code block in response
- `bench-starcoder2` D9 py2-subprocess-safe: **FAIL** — no code block in response
- `bench-starcoder2` D9 py3-retry-fn: **FAIL** — no code block in response
- `bench-starcoder2` D9 py4-deep-merge: **FAIL** — exit 1:   File "/code", line 2
    cfg2 = {'x': dict(b=(10,), a="overriden", x=['five']), y='y'}
                               

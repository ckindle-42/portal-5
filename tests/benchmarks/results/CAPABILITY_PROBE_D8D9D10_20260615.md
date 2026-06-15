# Coding Capability Probe — Matrix

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-15T09:50:28Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D8 PowerShell | D9 PyProd | D10 SecAPI |
|---|---|---|---|
| bench-deepseek-coder-v2 | 3/5 | 2/4 | 6/9 |
| bench-devstral-small-2 | 2/5 | 3/4 | 7/9 |
| bench-gemma4-12b-coder | 1/5 | 2/4 | 4/9 |
| bench-glm | 5/5 | 2/4 | 7/9 |
| bench-granite41-30b | 2/5 | 2/4 | 7/9 |
| bench-granite41-8b | 2/5 | 1/4 | 6/9 |
| bench-harness1 | 2/5 | 1/4 | 4/9 |
| bench-laguna | 3/5 | 3/4 | 7/9 |
| bench-lfm25-8b | 0/5 | 1/4 | 4/9 |
| bench-omnicoder2 | 2/5 | 1/4 | 4/9 |
| bench-qwen3-coder-30b | 3/5 | 2/4 | 9/9 |
| bench-qwen3-coder-next | 4/5 | 2/4 | 7/9 |
| bench-qwen36-27b | 3/5 | 1/4 | 6/9 |
| bench-qwopus-coder-mtp | 4/5 | 1/4 | 7/9 |
| bench-r1-0528-abliterated | 1/5 | 0/4 | 0/9 |
| bench-r1-0528-qwen3-8b | 3/5 | 1/4 | 5/9 |
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
- `bench-deepseek-coder-v2` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-deepseek-coder-v2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-deepseek-coder-v2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-deepseek-coder-v2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: the following arguments are required: command

- `bench-deepseek-coder-v2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-deepseek-coder-v2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 28, in <module>
    assert r2["k"] == "keep", f"None should not 
- `bench-devstral-small-2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 47, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-devstral-small-2` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 31, in <module>
    assert len(results) == 2, f"Expected 2 rows,
- `bench-devstral-small-2` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-devstral-small-2` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps2-error-handling: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-devstral-small-2` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-devstral-small-2` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-devstral-small-2` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-devstral-small-2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: the following arguments are required: command

- `bench-devstral-small-2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-devstral-small-2` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec1-nessus-parse: **FAIL** — exit 1:   File "/code", line 18
    svid = str(vulnerability['severity']['id'] if isinstance(vulnerability['severity']['id'], (s
- `bench-gemma4-12b-coder` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec6-ssrs-deploy: **FAIL** — exit 1:   File "/code", line 5
    )
    ^
SyntaxError: f-string: single '}' is not allowed

- `bench-gemma4-12b-coder` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 57, in <module>
    assert s["high"] == 1, f"high={s['high']}"
 
- `bench-gemma4-12b-coder` D10 sec8-ssrs-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D8 ps1-pipeline-filter: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D8 ps2-error-handling: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-gemma4-12b-coder` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 31, in <module>
    ns = build_parser().parse_args(['list', '--f
- `bench-gemma4-12b-coder` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 22, in <module>
    r = merge_configs(base, override)
        ^^
- `bench-glm` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 53, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-glm` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-glm` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-glm` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 56, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-glm` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-glm` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-glm` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-glm` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-glm` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-glm` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-glm` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-glm` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-glm` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-glm` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-glm` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-glm` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 38, in <module>
    with_retry(always_fail, max_attempts=2)
  Fi
- `bench-glm` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 52, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-granite41-30b` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 54, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-granite41-30b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps1-pipeline-filter: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-30b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-30b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-30b` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: the following arguments are required: command

- `bench-granite41-30b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-granite41-8b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 44, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-granite41-8b` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 23, in <module>
    assert "index=security" in spl, f"spl={spl}"
- `bench-granite41-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-8b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-granite41-8b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-granite41-8b` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-8b` D8 ps4-json-transform: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-8b` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-granite41-8b` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-granite41-8b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-granite41-8b` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 22, in <module>
    assert with_retry(lambda: 99) == 99
        
- `bench-granite41-8b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 20, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-harness1` D10 sec1-nessus-parse: **FAIL** — no code block in response
- `bench-harness1` D10 sec2-splunk-search: **FAIL** — no code block in response
- `bench-harness1` D10 sec3-solarwinds-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 13, in <module>
    q = build_swql("Orion.Nodes", ["NodeID", "Ca
- `bench-harness1` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-harness1` D10 sec5-mssql-query: **FAIL** — exit 1:   File "/code", line 4
    \"\"\"Return failed login events from the last `days` days.\n\n    Parameters\n    ----------
- `bench-harness1` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-harness1` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-harness1` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-harness1` D10 sec9-changegear-powershell: **FAIL** — no code block in response
- `bench-harness1` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-harness1` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-harness1` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-harness1` D8 ps4-json-transform: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-harness1` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-harness1` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: the following arguments are required: subcommand

- `bench-harness1` D9 py2-subprocess-safe: **FAIL** — no code block in response
- `bench-harness1` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-harness1` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 44, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-laguna` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 39, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-laguna` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-laguna` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-laguna` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 34, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-laguna` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-laguna` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-laguna` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-laguna` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-laguna` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-laguna` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-laguna` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-laguna` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-laguna` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-laguna` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-laguna` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-laguna` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-laguna` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 51, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-lfm25-8b` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 57, in <module>
    assert "earliest=-24h" in spl
           ^^^
- `bench-lfm25-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec5-mssql-query: **FAIL** — exit 1:   File "/code", line 9
    return [
           ^
SyntaxError: '[' was never closed

- `bench-lfm25-8b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 93, in <module>
    assert s["high"] == 1, f"high={s['high']}"
 
- `bench-lfm25-8b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-lfm25-8b` D8 ps1-pipeline-filter: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-lfm25-8b` D8 ps2-error-handling: **FAIL** — no code block in response
- `bench-lfm25-8b` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-lfm25-8b` D8 ps4-json-transform: **FAIL** — no code block in response
- `bench-lfm25-8b` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-lfm25-8b` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 46, in <module>
    main()
  File "/code", line 42, in main
    
- `bench-lfm25-8b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-lfm25-8b` D9 py3-retry-fn: **FAIL** — no code block in response
- `bench-lfm25-8b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 24, in <module>
    assert r["a"] == 1, f"a={r['a']}"
          
- `bench-omnicoder2` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 52, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-omnicoder2` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 37, in <module>
    assert "earliest=-24h" in spl
           ^^^
- `bench-omnicoder2` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-omnicoder2` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 92, in <module>
    assert tickets[0]["status"] == "open", f"sta
- `bench-omnicoder2` D10 sec8-ssrs-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-omnicoder2` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-omnicoder2` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-omnicoder2` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-omnicoder2` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-omnicoder2` D8 ps4-json-transform: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-omnicoder2` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-omnicoder2` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: the following arguments are required: command

- `bench-omnicoder2` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-omnicoder2` D9 py3-retry-fn: **FAIL** — exit 1:   File "/code", line 1
    def with_retry(fn, max_attempts=3, backoff_base=0.0, retryable=('429', '503', 'timeout')):
In
- `bench-omnicoder2` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 44, in <module>
    assert r["b"] == {"x": 10, "y": 99, "z": 30}
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
- `bench-qwen3-coder-30b` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-qwen3-coder-30b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-qwen3-coder-30b` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwen3-coder-30b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen3-coder-30b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 41, in <module>
    assert r2["k"] == "keep", f"None should not 
- `bench-qwen3-coder-next` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 72, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-qwen3-coder-next` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 47, in <module>
    assert "[dbo].[SecurityEvents]" in q, f"tabl
- `bench-qwen3-coder-next` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-qwen3-coder-next` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwen3-coder-next` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 42, in <module>
    assert 'not found' in r3['stderr'], f"stderr
- `bench-qwen3-coder-next` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwen3-coder-next` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec1-nessus-parse: **FAIL** — harness error: 
- `bench-qwen36-27b` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec5-mssql-query: **FAIL** — harness error: 
- `bench-qwen36-27b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwen36-27b` D10 sec9-changegear-powershell: **FAIL** — no code block in response
- `bench-qwen36-27b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps3-log-parse: **FAIL** — no code block in response
- `bench-qwen36-27b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwen36-27b` D8 ps5-retry-block: **FAIL** — harness error: 
- `bench-qwen36-27b` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwen36-27b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwen36-27b` D9 py3-retry-fn: **FAIL** — exit 1:   File "/code", line 11
    assert with_retry(lambda: 99) == 99
IndentationError: expected an indented block after 'exce
- `bench-qwen36-27b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-qwopus-coder-mtp` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-qwopus-coder-mtp` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec9-changegear-powershell: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-qwopus-coder-mtp` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps5-retry-block: **FAIL** — no code block in response
- `bench-qwopus-coder-mtp` D9 py1-argparse-cli: **FAIL** — exit 2: usage: code [-h] [--verbose] {list,get} ...
code: error: unrecognized arguments: --verbose

- `bench-qwopus-coder-mtp` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D9 py3-retry-fn: **FAIL** — exit 1:   File "/code", line 5
    while attempt <= max Attempts:
                         ^^^^^^^^
SyntaxError: invalid syntax

- `bench-qwopus-coder-mtp` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D10 sec1-nessus-parse: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec2-splunk-search: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec3-solarwinds-parse: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec4-tripwire-parse: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec5-mssql-query: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec6-ssrs-deploy: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec7-changegear-api: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec8-ssrs-powershell: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D10 sec9-changegear-powershell: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-r1-0528-abliterated` D8 ps2-error-handling: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-abliterated` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-abliterated` D8 ps4-json-transform: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-abliterated` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-abliterated` D9 py1-argparse-cli: **FAIL** — harness error: 
- `bench-r1-0528-abliterated` D9 py2-subprocess-safe: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D9 py3-retry-fn: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-abliterated` D9 py4-deep-merge: **FAIL** — harness error: Client error '429 Too Many Requests' for url 'http://localhost:9099/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `bench-r1-0528-qwen3-8b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 74, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-r1-0528-qwen3-8b` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
    rows = parse_splunk_results(resp)
          
- `bench-r1-0528-qwen3-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 39, in <module>
    assert all(r["id"] for r in reports)
       
- `bench-r1-0528-qwen3-8b` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 33, in <module>
    assert "assignee" not in f, f"empty assignee
- `bench-r1-0528-qwen3-8b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps3-log-parse: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-qwen3-8b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps5-retry-block: **FAIL** — exit 1: WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no 
- `bench-r1-0528-qwen3-8b` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 57, in <module>
    main()
  File "/code", line 50, in main
    
- `bench-r1-0528-qwen3-8b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D9 py3-retry-fn: **FAIL** — harness error: 
- `bench-r1-0528-qwen3-8b` D9 py4-deep-merge: **FAIL** — harness error: 
- `bench-starcoder2` D10 sec1-nessus-parse: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec2-splunk-search: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec3-solarwinds-parse: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec4-tripwire-parse: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec5-mssql-query: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec6-ssrs-deploy: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec7-changegear-api: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec8-ssrs-powershell: **FAIL** — no code block in response
- `bench-starcoder2` D10 sec9-changegear-powershell: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps1-pipeline-filter: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps2-error-handling: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps3-log-parse: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps4-json-transform: **FAIL** — no code block in response
- `bench-starcoder2` D8 ps5-retry-block: **FAIL** — no code block in response
- `bench-starcoder2` D9 py1-argparse-cli: **FAIL** — exit 1:   File "/code", line 2
    ▃▄▅▆▇█⣿
    ^
SyntaxError: invalid character '▃' (U+2583)

- `bench-starcoder2` D9 py2-subprocess-safe: **FAIL** — no code block in response
- `bench-starcoder2` D9 py3-retry-fn: **FAIL** — exit 1:   File "/code", line 1
    >>> sort_key = lambda x: (-x[1], x[0])  # last name first, then name
    ^^
SyntaxError: inva
- `bench-starcoder2` D9 py4-deep-merge: **FAIL** — no code block in response

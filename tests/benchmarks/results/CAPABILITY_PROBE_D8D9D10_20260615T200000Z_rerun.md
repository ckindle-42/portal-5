# Coding Capability Probe — Matrix

**Source**: `/Users/chris/projects/portal-5/tests/fixtures/capability_scenarios.yaml` · generated 2026-06-15T22:33:22Z

Execution-validated where applicable: PASS = the model's code ran in the sandbox and produced correct output. D6 is manual-review (refusal disposition). No verdict — promotions operator-only.

| Model | D8 PowerShell | D9 PyProd | D10 SecAPI |
|---|---|---|---|
| bench-gemma4-12b-coder | 0/5 | 1/4 | 4/9 |
| bench-granite41-30b | 3/5 | 3/4 | 7/9 |
| bench-granite41-8b | 2/5 | 4/4 | 5/9 |
| bench-harness1 | 1/5 | 3/4 | 6/9 |
| bench-lfm25-8b | 1/5 | 1/4 | 1/9 |
| bench-qwopus-coder-mtp | 4/5 | 2/4 | 5/9 |
| bench-r1-0528-abliterated | 1/5 | 0/4 | 1/9 |
| bench-r1-0528-qwen3-8b | 2/5 | 0/4 | 7/9 |

## Per-cell detail

- `bench-gemma4-12b-coder` D10 sec1-nessus-parse: **FAIL** — exit 1:   File "/code", line 31
    }), count may need a cast to int if it comes as str in the sample)
                         
- `bench-gemma4-12b-coder` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec4-tripwire-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 26, in <module>
    assert len(results) == 3, f"Expected 3, got 
- `bench-gemma4-12b-coder` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 40, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-gemma4-12b-coder` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   1 | [0m function Get-SsrsReports([36;1m-[0m
- `bench-gemma4-12b-coder` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   3 | [0m         [Parameter(Mandatory)][36;1m
- `bench-gemma4-12b-coder` D8 ps1-pipeline-filter: **FAIL** — exit 1: [31;1mInvalidArgument: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  21 | [0m [36;1m[System.IO.File]::WriteAll
- `bench-gemma4-12b-coder` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  28 | [0m }[36;1m#[0m This structure isn't th
- `bench-gemma4-12b-coder` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   3 | [0m … $results = foreach ($line in ($logC
- `bench-gemma4-12b-coder` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   7 | [0m             $status = if ($check.valu
- `bench-gemma4-12b-coder` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   9 | [0m …            if ($retryPatterns | Whe
- `bench-gemma4-12b-coder` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    ns = build_parser().parse_args(['list', '--f
- `bench-gemma4-12b-coder` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
    r3 = run_command(['/no/such/binary/exists'])
- `bench-gemma4-12b-coder` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-gemma4-12b-coder` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 19, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-granite41-30b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 50, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-granite41-30b` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 43, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-granite41-30b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-granite41-30b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps2-error-handling: **FAIL** — no code block in response
- `bench-granite41-30b` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  19 | [0m                 cs[36;1m-[0mmethod 
- `bench-granite41-30b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-granite41-30b` D8 ps5-retry-block: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-granite41-30b` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 27, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-granite41-8b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 48, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-granite41-8b` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 19, in <module>
    assert "index=security" in spl, f"spl={spl}"
- `bench-granite41-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-granite41-8b` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 2 reports, got 0[0m

- `bench-granite41-8b` D10 sec9-changegear-powershell: **FAIL** — exit 1: 
- `bench-granite41-8b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-granite41-8b` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-granite41-8b` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  25 | [0m                 cs[36;1m-[0mmethod 
- `bench-granite41-8b` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mWriteError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  11 | [0m     foreach ([36;1m$host[0m in $data
- `bench-granite41-8b` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  18 | [0m … ryPatterns | Where-Object { $except
- `bench-granite41-8b` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-granite41-8b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-granite41-8b` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-granite41-8b` D9 py4-deep-merge: **PASS** — expected stdout matched
- `bench-harness1` D10 sec1-nessus-parse: **PASS** — expected stdout matched
- `bench-harness1` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-harness1` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-harness1` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-harness1` D10 sec5-mssql-query: **FAIL** — exit 1:   File "/code", line 33
    }
    ^
SyntaxError: unmatched '}'

- `bench-harness1` D10 sec6-ssrs-deploy: **FAIL** — exit 1:   File "/code", line 71
    }
    ^
SyntaxError: unmatched '}'

- `bench-harness1` D10 sec7-changegear-api: **PASS** — expected stdout matched
- `bench-harness1` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-harness1` D10 sec9-changegear-powershell: **FAIL** — no code block in response
- `bench-harness1` D8 ps1-pipeline-filter: **FAIL** — exit 1: [31;1mInvalidArgument: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  23 | [0m [36;1m[System.IO.File]::WriteAll
- `bench-harness1` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-harness1` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 3 rows, got 0[0m

- `bench-harness1` D8 ps4-json-transform: **FAIL** — exit 1: [31;1mException: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  11 | [0m         [36;1mthrow "Unable to parse i
- `bench-harness1` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  17 | [0m         } catch [Exception][36;1m [
- `bench-harness1` D9 py1-argparse-cli: **PASS** — expected stdout matched
- `bench-harness1` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-harness1` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-harness1` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 43, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-lfm25-8b` D10 sec1-nessus-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 37, in <module>
    assert r["summary"]["critical"] == 2, f"crit
- `bench-lfm25-8b` D10 sec2-splunk-search: **FAIL** — exit 1:   File "/code", line 14
    "Returns a Splunk SPL search string:
    ^
SyntaxError: unterminated string literal (detecte
- `bench-lfm25-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-lfm25-8b` D10 sec4-tripwire-parse: **FAIL** — exit 1:   File "/code", line 2
    return sorted(
                 ^
SyntaxError: '(' was never closed

- `bench-lfm25-8b` D10 sec5-mssql-query: **FAIL** — exit 1:   File "/code", line 10
    return [dict(zip(['username', 'ip_address', 'event_time'], row))
           ^
SyntaxError: '
- `bench-lfm25-8b` D10 sec6-ssrs-deploy: **FAIL** — exit 1:   File "/code", line 1
    public static string BuildSsrsDatasetQuery(string table, string dateField, string paramStart 
- `bench-lfm25-8b` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 54, in <module>
    assert "assignee" not in f, f"empty assignee
- `bench-lfm25-8b` D10 sec8-ssrs-powershell: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 2 reports, got 1[0m

- `bench-lfm25-8b` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  14 | [0m         Content[36;1m-[0mType  = 'a
- `bench-lfm25-8b` D8 ps1-pipeline-filter: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   5 | [0m         [double][36;1m [0m-MinSizeM
- `bench-lfm25-8b` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mInvoke-SafeBlock: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  30 | [0m $ok = Invoke-SafeBlock [36;1m-A
- `bench-lfm25-8b` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  10 | [0m         $line = $rawLine [36;1m-trim
- `bench-lfm25-8b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-lfm25-8b` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mWrite-Error: [31;1mExpected 'hello', got [0m

- `bench-lfm25-8b` D9 py1-argparse-cli: **FAIL** — exit 1:   File "/code", line 32
    help='Specify the record ID**
         ^
SyntaxError: unterminated string literal (detected 
- `bench-lfm25-8b` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-lfm25-8b` D9 py3-retry-fn: **FAIL** — no code block in response
- `bench-lfm25-8b` D9 py4-deep-merge: **FAIL** — no code block in response
- `bench-qwopus-coder-mtp` D10 sec1-nessus-parse: **FAIL** — exit 1:   File "/code", line 27
    "summary": {*summary, "total": len(vuln_list)},
                                 ^
SyntaxErr
- `bench-qwopus-coder-mtp` D10 sec2-splunk-search: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 30, in <module>
    assert "[dbo].[SecurityEvents]" in q, f"tabl
- `bench-qwopus-coder-mtp` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 1, in <module>
    import requests
ModuleNotFoundError: No modul
- `bench-qwopus-coder-mtp` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  60 | [0m }[36;1m[0m
[31;1m[36;1m[36;1m[0
- `bench-qwopus-coder-mtp` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps2-error-handling: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps3-log-parse: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  34 | [0m Wait[36;1m,[0m let me reconsider. T
- `bench-qwopus-coder-mtp` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 32, in <module>
    ns = build_parser().parse_args(['list', '--f
- `bench-qwopus-coder-mtp` D9 py2-subprocess-safe: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D9 py3-retry-fn: **PASS** — expected stdout matched
- `bench-qwopus-coder-mtp` D9 py4-deep-merge: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 36, in <module>
    assert r["d"] is None  # None is set if key 
- `bench-r1-0528-abliterated` D10 sec1-nessus-parse: **FAIL** — exit 1:   File "/code", line 108
    top_critical_list = sorted(top_critical_final, key=lambda d: float(d['cvssV3BaseScore']), r
- `bench-r1-0528-abliterated` D10 sec2-splunk-search: **FAIL** — exit 1:   File "/code", line 35
    result_array = (response["results"]  # Note: This directly uses the provided response struct
- `bench-r1-0528-abliterated` D10 sec3-solarwinds-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 71, in <module>
    assert "SELECT" in q and "NodeID" in q and "
- `bench-r1-0528-abliterated` D10 sec4-tripwire-parse: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 27, in <module>
    results = parse_tripwire_results(data, min_s
- `bench-r1-0528-abliterated` D10 sec5-mssql-query: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 70, in <module>
    results = get_failed_logins(cur, days=7)
   
- `bench-r1-0528-abliterated` D10 sec6-ssrs-deploy: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 7, in <module>
    q = build_ssrs_dataset_query("[dbo].[Security
- `bench-r1-0528-abliterated` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 8, in <module>
    f = build_ticket_filter("changes", status="Op
- `bench-r1-0528-abliterated` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-r1-0528-abliterated` D10 sec9-changegear-powershell: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  51 | [0m …          if ([System.Version]::new(
- `bench-r1-0528-abliterated` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-r1-0528-abliterated` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   4 | [0m         [Parameter(Mandatory=$true, P
- `bench-r1-0528-abliterated` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   7 | [0m     if ([string]::IsNullOrW[36;1m`it
- `bench-r1-0528-abliterated` D8 ps4-json-transform: **FAIL** — exit 1: 
- `bench-r1-0528-abliterated` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  39 | [0m             (Get-Command Invoke-WithR
- `bench-r1-0528-abliterated` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 47, in <module>
    ns = build_parser().parse_args(['list', '--f
- `bench-r1-0528-abliterated` D9 py2-subprocess-safe: **FAIL** — exit 1:   File "/code", line 31
    hasattr(subprocess, '_DevNull') and isinstance(process.stdout, subprocess._DevNull) else \
 
- `bench-r1-0528-abliterated` D9 py3-retry-fn: **FAIL** — exit 1:   File "/code", line 14
    sleep_duration(wait_duration))
                                 ^
SyntaxError: unmatched ')'
- `bench-r1-0528-abliterated` D9 py4-deep-merge: **FAIL** — exit 1:   File "/code", line 10
    if any(v is None and k.startswith('ignore') else False for v in (new_base.get(k), config.get
- `bench-r1-0528-qwen3-8b` D10 sec1-nessus-parse: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec2-splunk-search: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 23, in <module>
    assert "index=security" in spl, f"spl={spl}"
- `bench-r1-0528-qwen3-8b` D10 sec3-solarwinds-parse: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec4-tripwire-parse: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec5-mssql-query: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec6-ssrs-deploy: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec7-changegear-api: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 71, in <module>
    assert tickets[0]["status"] == "open", f"sta
- `bench-r1-0528-qwen3-8b` D10 sec8-ssrs-powershell: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D10 sec9-changegear-powershell: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps1-pipeline-filter: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps2-error-handling: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m   4 | [0m         [Parameter(Mandatory=$true)]
- `bench-r1-0528-qwen3-8b` D8 ps3-log-parse: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m  19 | [0m                     cs[36;1m-[0mmet
- `bench-r1-0528-qwen3-8b` D8 ps4-json-transform: **PASS** — expected stdout matched
- `bench-r1-0528-qwen3-8b` D8 ps5-retry-block: **FAIL** — exit 1: [31;1mParserError: [0m
[31;1m[36;1mLine |[0m
[31;1m[36;1m[36;1m 100 | [0m …                $isRetriable = $fals
- `bench-r1-0528-qwen3-8b` D9 py1-argparse-cli: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 49, in <module>
    ns = build_parser().parse_args(['list', '--f
- `bench-r1-0528-qwen3-8b` D9 py2-subprocess-safe: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 42, in <module>
    r = run_command(['echo', 'hello world'])
   
- `bench-r1-0528-qwen3-8b` D9 py3-retry-fn: **FAIL** — exit 1: Traceback (most recent call last):
  File "/code", line 23, in <module>
    assert with_retry(lambda: 99) == 99
        
- `bench-r1-0528-qwen3-8b` D9 py4-deep-merge: **FAIL** — no code block in response

---
id: unit-readme-acceptance-testing
kind: what
title: "README \u2014 Acceptance Testing"
sources:
- type: code
  path: tests/portal5_acceptance_v6.py
- type: code
  path: tests/acceptance/cli.py
- type: code
  path: tests/acceptance/runner.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.691529
updated_at: 1784946220.691529
---

The acceptance suite is a live-stack gate, deliberately separate from the mocked
pytest unit suite. The entrypoint `tests/portal5_acceptance_v6.py` is a thin shim:
it re-exports the signal dictionaries from `tests/acceptance/_common.py` and calls
`acceptance.cli.main()`. `cli.py` parses `--section` and delegates each section to
one file under `tests/acceptance/` — for example `s02_services.py`, `s03_routing.py`,
`s10_personas_ollama.py`, `s16_security_mcp.py`, `s60_tool_calling.py` and
`s70_information_access.py`. Each section records named checks via `record(...)`,
and `cli.py` tallies PASS/FAIL/BLOCKED/WARN counts and writes the summary to
`ACCEPTANCE_RESULTS.md`.

Run the whole suite, or a single section:

```bash
python3 tests/portal5_acceptance_v6.py          # all sections
python3 tests/portal5_acceptance_v6.py --section S70
```

`--skip-passing` skips sections that passed in a prior run, and `--append` merges a
targeted re-run into the saved results. `tests/acceptance/runner.py` maps section
names such as S0, S2, S3a and S70 to their `async` section functions, so the suite
fails the run whenever any recorded check FAILs or BLOCKs.

## Why

The acceptance gate exists because unit tests deliberately mock Ollama and the HTTP
surface, so a mocked suite can pass while the deployed stack rejects requests,
tools are missing, or container ports are wrong. Running against the live stack
catches those contract breaks before a push. The section-per-file layout keeps each
area (services, routing, personas, security MCP) independently re-runnable during
debugging instead of forcing one monolithic run.

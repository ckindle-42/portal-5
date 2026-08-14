---
id: unit-portal5-acceptance-execute-v9-autonomous-monitoring-loop-required-default
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Autonomous Monitoring Loop \u2014 required\
  \ default"
sources:
- type: code
  path: tests/acceptance/cli.py
- type: code
  path: tests/lib/results.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: portal/platform/inference/router/app.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.694719
updated_at: 1784946220.694719
---

The acceptance suite runs many Ollama-routed sections back to back against a
live stack, so a full run is long and the machine is unattended for extended
windows. The S10c compliance section is the most expensive phase: it drives
every compliance persona through every applicable scenario expanded from the
compliance fixture, issuing one pipeline chat request per scenario. Because a
run can stall silently on cold model loads, ComfyUI memory pressure, or an
Ollama crash, the operator must monitor rather than fire-and-forget.

After launching the suite, establish a scheduled wakeup loop that periodically:

- probes pipeline liveness via the unauthenticated `/health` endpoint on
  `localhost:9099` (registered in `portal/platform/inference/router/app.py`);
- tails the live progress log written by the runner at
  `/tmp/portal5_progress.log` — `_emit` in `tests/lib/results.py` appends one
  line per check carrying the section, id, name, detail, and running
  PASS/WARN/FAIL counts, so progress is observable without polling the stack;
- diagnoses a stall from the last recorded section and its detail before
  acting, then halts with evidence if the run is genuinely hung rather than
  merely slow.

## Why

An unattended acceptance run that hangs wastes hours and produces a useless
results file. The runner writes a live progress log and the pipeline exposes a
health endpoint precisely so an operator can distinguish a slow-but-alive run
from a wedged one, and can point at recorded evidence when stopping. Nothing in
the code stops a hung section for you, so the monitoring cadence is an operator
discipline the preflight and the progress log exist to support.

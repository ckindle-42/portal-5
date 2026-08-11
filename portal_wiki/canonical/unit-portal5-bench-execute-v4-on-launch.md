---
id: unit-portal5-bench-execute-v4-on-launch
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 On launch"
sources:
- type: code
  path: tests/benchmarks/bench/config.py
- type: code
  path: tests/benchmarks/bench/cli.py
last_generated_commit: 3771ef49a112fde1d667c67af5bf1bc003ce75b4
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7016032
updated_at: 1784946220.7016032
---

1. Start the run detached, logging to a timestamped file under
   `tests/benchmarks/results/`.
2. Record the PID and the expected test count (from `--dry-run`).
3. Set the first wakeup ~20 min out.

## Why

The bench writes results to a timestamped JSON under
`tests/benchmarks/results/` by default: `RESULTS_DIR` and the UTC-stamped
`RESULTS_FILE` are set in `tests/benchmarks/bench/config.py`. Because a full
run spans hours and the CLI appends as it goes, the output file doubles as the
run's log of progress, so recording where it lives and the planned count on
launch is what lets a later wakeup compare completed tests against the
`--dry-run` plan and decide between reschedule, filter, or halt.

---
id: unit-portal5-bench-execute-v4-3-backends-up
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 3. Backends up?"
sources:
- type: code
  path: tests/benchmarks/bench/config.py
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/config.py
last_generated_commit: 9ec2fd4984c047ba49d9056db6a9666a1a4f0caf
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7008882
updated_at: 1784946220.7008882
---

```bash
curl -s localhost:11434/api/tags  >/dev/null && echo "ollama ok"
curl -s localhost:9099/health     >/dev/null && echo "pipeline ok"
```

The bench hits Ollama at `http://localhost:11434` and the pipeline at
`http://localhost:9099` (constants `OLLAMA_URL` / `PIPELINE_URL` in
`tests/benchmarks/bench/config.py`). The pipeline registers a `/health`
handler in `portal/platform/inference/router/app.py`; Ollama serves
`/api/tags`. The bench itself probes the same backends via
`_check_backend` on startup and refuses to run if neither responds.

## Why

`PORTAL_ENABLE_EVAL=1` must be set before `portal.platform.inference` is
imported: `_eval_enabled` in `portal/platform/inference/config.py` gates the
eval-module workspaces at pipeline load, and a bench plan that lists eval
workspaces is incomplete if the pipeline cannot route them. The retired-alias
check is the other gate — a leak there means the surface is not canonical, so
bench a broken surface is pointless and the run must stop.

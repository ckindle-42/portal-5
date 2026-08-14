---
id: unit-readme-test-everything-is-working
kind: what
title: "README \u2014 Test everything is working"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/smoke.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.68112
updated_at: 1784946220.68112
---

```bash
./launch.sh test            # Run live smoke tests against running stack
```

The `test` subcommand in `launch.sh` executes `portal.platform.inference.cli test`,
implemented in `portal/platform/inference/cli/smoke.py`. `cmd_test` runs
end-to-end checks against the live stack: it probes the pipeline health endpoint
(`PIPELINE_URL`, default `http://localhost:9099`) with the configured
`PIPELINE_API_KEY`, the Open WebUI URL (`OPENWEBUI_URL`, default
`http://localhost:8080`), and prints a per-check pass/fail summary with a nonzero
exit on any failure. This is the quick post-`up` verification path, distinct from
the heavier acceptance suite.

## Why

A mock-only unit suite cannot prove the real services accept requests, so a
short live smoke test is the first thing an operator runs after `up`. Keeping it
inside the CLI (rather than a compose one-shot) means it uses the same environment
the operator has, and a nonzero exit makes it usable in a scripted health check
without parsing output.

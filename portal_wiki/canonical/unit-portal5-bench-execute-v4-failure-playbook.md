---
id: unit-portal5-bench-execute-v4-failure-playbook
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Failure playbook"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Failure playbook
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.703467
updated_at: 1784946220.703467
---

- **A model won't load / OOMs** — the M4 Pro has 64GB; a 70B q4 + context can
  exceed it. Skip and note; don't force.
- **Persona benches at pool-default TPS not its pin** — served-model regression;
  report, don't patch.
- **Pipeline mode much slower than direct for the same model** — expected
  (routing overhead), but a large gap on a simple prompt may indicate a
  mis-route; cross-check with `routing_regression.py --assert-baseline`.
- **Preflight retired-alias leak** — surface regression; halt.

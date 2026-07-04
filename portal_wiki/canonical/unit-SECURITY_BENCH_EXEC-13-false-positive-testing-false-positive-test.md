---
id: unit-SECURITY_BENCH_EXEC-13-false-positive-testing-false-positive-test
kind: why
title: "SECURITY_BENCH_EXEC \u2014 13. False Positive Testing (`--false-positive-test`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 13. False Positive Testing (`--false-positive-test`)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.904553
updated_at: 1783195000.904553
---

Sends benign traffic (normal nmap scans, HTTP requests, DNS lookups, SMB share listings, LDAP queries) to the blue defender and measures false positive rate. Reports `false_positive_rate` per blue model and per-traffic verdicts.

```bash
python3 -m tests.benchmarks.bench_security \
  --blue-models "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --false-positive-test --lab-exec
```

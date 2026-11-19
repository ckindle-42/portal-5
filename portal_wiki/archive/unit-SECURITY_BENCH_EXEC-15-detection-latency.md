---
id: unit-SECURITY_BENCH_EXEC-15-detection-latency
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 15. Detection Latency"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 15. Detection Latency
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

Blue turn results now include `detection_latency_s` — the wall-clock time between red's tool execution and blue's detection response. Lower is better. Enables measuring whether blue detects in real-time or with significant delay.

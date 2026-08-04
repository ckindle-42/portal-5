---
id: unit-SECURITY_BENCH_EXEC-19-full-output-capture
kind: why
title: "SECURITY_BENCH_EXEC \u2014 19. Full Output Capture"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 19. Full Output Capture
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.906741
updated_at: 1783195000.906741
---

All raw data is preserved in the result JSON for post-hoc analysis:
- `tool_calls` — full tool calls with complete arguments (not truncated)
- `lab_outputs` — full lab command output (not truncated)
- `lab_observations` — accumulated observations (open_ports, confirmed_cve, etc.)
- `exec_scores` — full scoring breakdown including proven/attempted/skipped
- `blue_turns` — blue detection responses with detection_latency_s

The result JSON is self-contained: all data needed to rescore, replay, or analyze is in the file.

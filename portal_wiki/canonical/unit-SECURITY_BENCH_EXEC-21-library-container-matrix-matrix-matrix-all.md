---
id: unit-SECURITY_BENCH_EXEC-21-library-container-matrix-matrix-matrix-all
kind: why
title: "SECURITY_BENCH_EXEC \u2014 21. Library \xD7 Container Matrix (`--matrix` /\
  \ `--matrix-all`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "21. Library \xD7 Container Matrix (`--matrix` / `--matrix-all`)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.907288
updated_at: 1783195000.907288
---


The matrix mode crosses every scenario (56 in `PROMPTS`) and every challenge class (12 in `challenge_classes.yaml`) with every resolvable vulhub container on disk. Each class's vulhub globs (e.g., `fastjson/*`) expand into individual CVE environments — a dozen classes become hundreds of real test units.

Each unit is scored by a **named oracle** (`verify_finding` N/N), not text-match `success_indicators`. A unit PASSES only when its oracle VERIFIES against real output on the spun container.

```bash

---
id: unit-SECURITY_BENCH_EXEC-4-step-dependency-dag
kind: why
title: "SECURITY_BENCH_EXEC \u2014 4. Step Dependency DAG"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 4. Step Dependency DAG
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.902315
updated_at: 1783195000.902315
---

Steps with `depends_on` fields are topologically sorted into parallel groups via `_build_step_dag()` / `_dag_parallel_groups()`. When `--chain-dag` is used, independent steps are distributed across models.

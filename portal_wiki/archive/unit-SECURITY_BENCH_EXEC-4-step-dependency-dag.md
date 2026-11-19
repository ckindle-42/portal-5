---
id: unit-SECURITY_BENCH_EXEC-4-step-dependency-dag
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 4. Step Dependency DAG"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 4. Step Dependency DAG
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

Steps with `depends_on` fields are topologically sorted into parallel groups via `_build_step_dag()` / `_dag_parallel_groups()`. When `--chain-dag` is used, independent steps are distributed across models.

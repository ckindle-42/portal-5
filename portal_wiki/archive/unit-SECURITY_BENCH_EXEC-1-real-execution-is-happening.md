---
id: unit-SECURITY_BENCH_EXEC-1-real-execution-is-happening
kind: why
title: "SECURITY_BENCH_EXEC \u2014 1. Real execution is happening"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 1. Real execution is happening
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.909889
updated_at: 1783195000.909889
---


Look for `[EXEC OK]` / `[EXEC ERR]` lines in the log.

If you only see `[RED R1 ... ] execute_bash(...)` with no `[EXEC]` lines, verify lab exec availability:
```python
python3 -c "
from bench_security._data import _LAB_EXEC_AVAILABLE
print(_LAB_EXEC_AVAILABLE)
"
```
Must print `True`. False means `bench_lab_exec` import failed.

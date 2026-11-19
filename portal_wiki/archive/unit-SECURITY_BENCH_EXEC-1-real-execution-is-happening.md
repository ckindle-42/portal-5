---
id: unit-SECURITY_BENCH_EXEC-1-real-execution-is-happening
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 1. Real execution is happening"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 1. Real execution is happening
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

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

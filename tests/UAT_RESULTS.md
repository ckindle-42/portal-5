# Portal 5 — UAT Results

**Run:** 2026-07-26 11:58:40
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

**Run status:** Interrupted by operator request after A-01 completed; 1/314 cases executed.

## Summary

- **PASS**: 0
- **WARN**: 0
- **FAIL**: 1
- **SKIP**: 0
- **BLOCKED**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | FAIL | [A-01 Document RAG — Upload, Query, Follow-Up](http://localhost:8080/c/decad0a0-0ce8-49a2-be3b-166bd2e1c7da) | `auto` | 5/6(83%) [routed: auto] Turn 1 summary substantive=✓(len=368479, min=80); Not generic=✓(ok); Turn 2 retrieval substantive=✓(len=3176, min=100); Quotes content actually in fixture=✗(none of: ['access control', 'rbac', 'authentication', 'authorization', 'least privilege', 'principle of']); Recovery: passed on attempt 2/3=✓(1 retries needed (backend instability signal)); Routed model: auto=✓(matches Ollama:qwen3.5-abliterated) | 2113.1s |

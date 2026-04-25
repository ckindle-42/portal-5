# Portal 5 Acceptance Test Results — V6

**Date:** 2026-04-25 09:06:32
**Git SHA:** f282b71
**Sections:** S70
**Runtime:** 3s (0m 3s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 3 |
| ❌ FAIL | 1 |
| ⚠️  WARN | 3 |
| **Total** | **7** |

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S70 | S70-01 | SearXNG web search | ✅ PASS | 19 results returned | 0.9s |
| S70 | S70-02 | Research MCP health | ⚠️  WARN | not running: All connection attempts failed | 0.0s |
| S70 | S70-03 | Memory MCP health | ⚠️  WARN | not running: All connection attempts failed | 0.0s |
| S70 | S70-04 | RAG MCP health | ⚠️  WARN | not running: All connection attempts failed | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_65656.db | 0.1s |
# Portal 5 Acceptance Test Results — V6

**Date:** 2026-04-24 21:26:37
**Git SHA:** d2cb4b9
**Sections:** S50
**Runtime:** 60s (1m 0s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 5 |
| ⚠️  WARN | 1 |
| **Total** | **6** |

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S50 | S50-01 | Empty prompt handled gracefully | ⚠️  WARN | unexpected HTTP 408 | 30.0s |
| S50 | S50-02 | Oversized prompt rejected or truncated | ✅ PASS | HTTP 200 | 27.0s |
| S50 | S50-03 | Invalid model slug handled | ✅ PASS | HTTP 200 \| model=dolphin-llama3:8b | 0.8s |
| S50 | S50-04 | Pipeline /health surfaces backend count | ✅ PASS | healthy: 6 | 0.0s |
| S50 | S50-05 | Malformed JSON rejected | ✅ PASS | HTTP 400 | 0.0s |
| S50 | S50-06 | Missing auth rejected with 401 | ✅ PASS | HTTP 401 | 0.0s |
# UAT Run Log — 20260506T0421Z

| Phase | Status | Tests | P/W/F/S/M | Notes |
|---|---|---|---|---|
| 1. smoke (auto) | DONE | 4 | 2P/0W/2F | routing + persona smoke |
| 2. mlx_large heavy | DONE | 16 | 12P/1W/3F | compliance/agentic/vision/research |
| 3. auto-coding | DONE | 26 | mixed | proxy instability on rerun, fixed post-hoc |
| 4. mlx_small bulk | DONE | 25 | mixed | data/reasoning/creative/mistral/spl/math/auto |
| 5. ollama tier | DONE | 17 | 15P/0W/2F | security/redteam/blueteam/docs |
| 6. media_heavy | DONE | 5 | 2P/0W/0F/3S | music/video (3 memory-skips, 2 resolved) |
| 7. benchmark | DONE | 10 | 7P/0W/3F | CC-01 across 13 models |
| 8. advanced | DONE | 6 | 1P/0W/3F/1S/1M | --skip-bots |
| Re-test: P-DA03 | PASS | 1 | 100% | was infra FAIL, fixed by state=down→restart |
| Re-test: P-DA06 | PASS | 1 | 100% | was memory SKIP, fixed by free_gb reclaim |
| Re-test: P-D03 | PASS | 1 | 100% | was memory SKIP |
| Re-test: A-04 | PASS | 1 | 100% | was memory SKIP |
| Re-test: P-V10 | FAIL | 1 | 60% | was memory-empty, now behavioral keyword |
| Re-test: P-V11 | FAIL | 1 | 40% | was memory-empty, now behavioral keyword |

## Final Results

| Metric | Count |
|---|---|
| Total | 76 |
| PASS | 56 |
| WARN | 2 |
| FAIL | 16 |
| SKIP | 1 |
| MANUAL | 1 |
| Pass rate | 73% |

## Failure Breakdown

| Category | Count | Detail |
|---|---|---|
| Infrastructure | 0 | 0 backend_unavailable |
| Benchmark (expected) | 3 | CC-01 per P5-BENCH-001 |
| Behavioral (keyword mismatch) | 13 | Needs OWUI review per protocol |

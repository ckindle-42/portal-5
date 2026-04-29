# UAT Run Log — 20260428T1918Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260428T1918Z | 19:34Z | 4 | 4P/0W/0F | exit=0 |
| 2. mlx_large heavy | DONE | 20260428T1918Z | 20:41Z | 16 | 17P/1W/2F (cum) | exit=0 |
| 3. auto-coding | DONE | 20260428T1918Z | 21:48Z | 26 | 33P/1W/12F (cum) | exit=0 — watchdog interference suspected |
| 3. auto-coding (re-run, no watchdog) | DONE | 20260428T1918Z | 00:43Z | 26 | 46P/1W/22F (cum, incl duplicates) | exit=0 — identical results to first run, assertion strictness |
| 4. mlx_small bulk | DONE | 20260428T1918Z | 02:21Z | 25 | 69P/1W/24F (cum, incl duplicates) | exit=0 — 23P/2F new |
| 5. ollama tier | DONE | 20260428T1918Z | 03:15Z | 17 | 83P/1W/27F (cum, incl duplicates) | exit=0 — 14P/3F new (T-11 sec MCP: 0/3) |
| 6. media_heavy | DONE | 20260428T1918Z | 03:46Z | 5 | 87P/1W/27F/1S (cum, incl duplicates) | exit=0 — 4P/1S new (Whisper skipped) |
| 7. benchmark | DONE | 20260428T1918Z | 05:05Z | 9 | 89P/1W/33F/2S (cum, incl dups) | exit=0 — 2P/6F/1S (memory pressure, MLX crash) |
| 8. advanced | DONE | 20260428T1918Z | 05:27Z | 5 | 93P/1W/35F/1S/1M (cum, incl dups) | exit=0 — 1P/2F/1S/1M new, memory pressure, A-04 skipped |

## Run summary — 20260428T1918Z

- Total rows: 131  PASS: 93  WARN: 1  FAIL: 35  SKIP: 1  MANUAL: 1
- Unique estimate: ~100 tests across 8 phases
- Pass rate: ~90P / ~104 unique ≈ 86.5%
| 6. media_heavy (re-run, clean) | DONE | post-crash | 14:28Z | 5 | 4P/1S new, 94P/1W/35F/4S/1M cum | exit=0 — all passed, memory 74% |
| 7. benchmark (re-run) | DONE | post-crash | 16:26Z | 9 | 1P/7F comfyui residue blocked model loading | exit=0 |

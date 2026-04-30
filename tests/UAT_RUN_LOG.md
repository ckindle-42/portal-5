# UAT Run Log — 20260430T0444Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260430T0444Z | 05:33Z | 4 | 4P/0W/0F | exit=0 |
| 2. mlx_large heavy | DONE | 06:46Z | 06:46Z | 16 | 20P/0W/0F (cum) | exit=0 |
| 3. auto-coding | DONE | 08:58Z | 08:58Z | 26 | 43P/1W/2F (cum) | exit=0 |
| 4. mlx_small bulk | DONE | 11:05Z | 11:05Z | 25 | 65P/1W/5F (cum) | exit=0 |
| 5. ollama tier | DONE | 12:01Z | 12:01Z | 17 | 78P/1W/9F (cum) | exit=0 |
| 6. media_heavy | DONE | 12:27Z | 12:27Z | 4 | 79P/1W/9F (cum) | WS-12 driver crash |
| 7. benchmark | PAUSED | 12:35Z | — | 0/9 | — | Docker stack down, OWUI unreachable |
| 7. benchmark | DONE | 13:23Z | 13:23Z | 9 | 83P/1W/14F (cum) | exit=0 |
| 8. advanced | DONE | 13:49Z | 13:49Z | 6 | 87P/1W/15F (cum) | exit=0 |

## Run summary — 20260430T0444Z

- Total: 105  PASS: 87  WARN: 1  FAIL: 15  SKIP: 1  MANUAL: 1
- Pass rate: 82% (excluding manual)

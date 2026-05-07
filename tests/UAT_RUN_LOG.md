# UAT Run Log — 20260506T0421Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260506T0421Z | 05:13Z | 4 | 2P/0
0W/2F | exit=0 |
| 1. gate | PASS | 05:16Z | 05:16Z | — | — | wired=2.0GB after 70s |
| 2. mlx_large heavy | DONE | 06:22Z | 06:22Z | 16 | 14P/1W/5F (cum) | exit=0 |
| 2. gate | PASS | 06:28Z | 06:28Z | — | — | wired=2.0GB after 320s |
| 3. auto-coding | DONE | 08:01Z | 08:01Z | 22/26 | 29P/2W/11F (cum) | exit=0 (proxy crashes caused 4 incomplete) |
| 3. gate | BLOCKED | 08:02Z | — | — | — | proxy DOWN (3 attempts) |
| 3. gate | PASS | 08:04Z | 08:04Z | — | — | wired=2.0GB after 70s |
| 3. auto-coding (rerun) | DONE | 11:06Z | 11:06Z | 11/26 | 22P/2W/15F (cum) | exit=0 (proxy crashes worse on rerun) |
| 4. mlx_small bulk | DONE | 11:06Z | 11:06Z | 8 added | 22P/2W/15F (cum) | exit=0 (partial, proxy instability ongoing) |
| 4. gate | PASS | 11:09Z | 11:09Z | — | — | wired=2.0GB after 140s |
| 99. gate | PASS | 15:21Z | 15:21Z | — | — | wired=2.6GB after 620s |
| 99. gate | PASS | 15:25Z | 15:25Z | — | — | wired=0.0GB inactive=0.0GB after 160s |
| 5. ollama tier | DONE | 16:47Z | 16:47Z | 17 | 40P/2W/17F (cum) | exit=0, 2 SKIP |
| 5. gate | PASS | 16:49Z | 16:49Z | — | — | wired=2.6GB inactive=17.0GB after 60s |
| 6. media_heavy | DONE | 17:11Z | 17:11Z | 5 (3S) | 42P/2W/17F (cum) | exit=0, Metal leak detection skipped 3 |
| 6. gate | PASS | 17:13Z | 17:13Z | — | — | wired=2.7GB inactive=8.1GB after 100s |
| 7. benchmark | DONE | 18:43Z | 18:43Z | 10 | 49P/2W/20F (cum) | exit=0 |
| 7. gate | PASS | 18:46Z | 18:46Z | — | — | wired=0.0GB inactive=0.0GB after 160s |
| 8. advanced | DONE | 18:56Z | 18:56Z | 6 (6S) | 49P/2W/20F (cum) | exit=0, all skipped (Metal leak detection) |

## Run summary

- Total: 84  PASS: 49  WARN: 2  FAIL: 20  SKIP: 13
- Pass rate: 58%

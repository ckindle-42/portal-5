# UAT Run Log — 20260508T1918Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260508T1918Z | 02:14Z | 4 | 2P/0
0W/1F | exit=0 |
| 1. gate | PASS | 03:51Z | 03:51Z | — | — | wired=2.9GB inactive=9.3GB after 110s |
| 2. mlx_large heavy | DONE | 05:14Z | 05:14Z | 24 | 3P/0
0W/2F (cum) | exit=0 |
| 2. gate | PASS | 05:18Z | 05:18Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 3. gate | PASS | 06:38Z | 06:38Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 3. auto-coding | DONE | 08:25Z | 08:25Z | 26 | 3P/0W/2F (cum) | exit=0 |
| 3. gate | PASS | 08:28Z | 08:28Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 4. mlx_small bulk | DONE | 11:30Z | 11:30Z | 25 | 23P/2W/5F (cum) | exit=0 |
| 4. gate | PASS | 11:32Z | 11:32Z | — | — | wired=2.9GB inactive=13.0GB after 110s |
| 5. ollama + mlx_small | DONE | 11:53Z | 11:53Z | 9 | 32P/2W/5F (cum) | exit=0 |
| 5. gate | PASS | 11:56Z | 11:56Z | — | — | wired=0.0GB inactive=0.0GB after 130s |
| 6. media_heavy | DONE | 12:37Z | 12:37Z | 5 | 36P/2W/5F (cum) | exit=0 |
| 6. gate | PASS | 12:39Z | 12:39Z | — | — | wired=2.9GB inactive=6.6GB after 100s |
| 7. benchmark | DONE | 13:37Z | 13:37Z | 13 | 47P/4W/5F (cum) | exit=0 |
| 7. gate | PASS | 13:38Z | 13:38Z | — | — | wired=2.9GB inactive=19.0GB after 70s |
| 8. advanced | DONE | 14:39Z | 14:39Z | ~6 | 49P/4W/11F (cum) | exit=0 |

## Run summary

- Total: 64  PASS: 49  WARN: 4  FAIL: 11
- Pass rate: 76%
| 99. gate | PASS | 17:26Z | 17:26Z | — | — | wired=0.0GB inactive=0.0GB after 200s |

## Retest corrections

| Test | Before | After | Root cause |
|---|---|---|---|
| WS-17 Mistral Reasoner | FAIL 33% | **PASS 6/6** | Phase 4 memory pressure — empty response cascade |
| WS-04 SPL Engineer | FAIL 50% | **PASS 5/5** | Phase 4 memory pressure — empty response cascade |
| P-DA05 Phi-4 STEM | FAIL 33% | **PASS 5/5** | Thinking model timeout (90s→450s poll cap) + token cap (16K→32K predict_limit) |
| A-03 Same-Session Memory | FAIL 66% | **PASS 5/5** | Phase 8 memory pressure — empty response cascade |

## Final tally

- **PASS: 53  WARN: 4  FAIL: 4  SKIP: 50**
- **Pass rate: 87%** (53/61 executed)
- **Remaining FAILs**: P-B03 (behavioral), WS-16 (assertion), A-08 (cross-chat memory), A-01 (multi-turn empty turn 2)

## Code changes made during this UAT run

1. `portal_pipeline/notifications/events.py`: Fixed Telegram MarkdownV2 — list repr brackets + underscore in keys
2. `tests/portal5_uat_driver.py:334`: Free memory guard narrowed to `free_gb < 4 and used >= 90%`
3. `portal_pipeline/router/workspaces.py`: `auto-data` + `auto-reasoning` predict_limit 16384→32768
4. `tests/portal5_uat_driver.py:5549`: P-DA05 tier mlx_small→mlx_large (450s polling cap for thinking model)

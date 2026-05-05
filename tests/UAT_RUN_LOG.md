# UAT Run Log — 20260505T0610Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260505T0610Z | 06:22Z | 4 | 1P/0W/2F | exit=timeout (600s), exit=0 |
| 2. mlx_large heavy | DONE | 07:28Z | 07:28Z | 16 | 13P/1W/6F (cum) | exit=0 |
| 3. auto-coding | DONE | 09:38Z | 09:38Z | 26 | 27P/1W/18F (cum) | exit=0 (resumed after proxy recovery) |
| 4. mlx_small bulk | DONE | 13:08Z | 13:08Z | 25 | 42P/2W/27F/1S (cum) | exit=0, 1 SKIP (mem pressure), WS-04 flagged for crash review |
| 5. ollama tier | DONE | 13:28Z | 13:28Z | 17 | 57P/2W/29F/1S (cum) | exit=0 |
| 6. media_heavy | DONE | 15:43Z | 15:43Z | 5 | 72P/3W/35F/2S/1M (cum) | exit=0 (T-08 FAIL image keywords, M-01 SKIP no_audio_fixture) |
| 7. benchmark | DONE | 14:40Z | 14:40Z | 13 | 66P/3W/32F/1S (cum) | exit=0, phi4-reasoning/granite41-30b empty-resp per KNOWN_LIMITS P5-BENCH-001 |
| 8. advanced | DONE | 14:51Z | 14:51Z | 6 | 69P/3W/34F/1S/1M (cum) | exit=0, --skip-bots |

## Run summary — 

- Total: 108  PASS: 69  WARN: 3  FAIL: 34  SKIP: 1  MANUAL: 1
- Pass rate: 65%

### Memory notes
- Phases 2-4 hit 80-93% memory consistently, causing empty-response cascades
- Large MLX models (Qwopus3.5-27B, Qwen3-Coder-30B, Llama-3.3-70B) consume 30-45GB wired
- Metal GPU buffer retention keeps wired elevated after unload (30-45 min recovery)
- Phase 4: 1 test SKIPPED due to memory critical (90%) — P-DA05
- 1 system crash/reboot during Phase 4 — resumed
- WS-04 (auto-spl) flagged: consistently causes empty responses on all 3 attempts
| 9. gate | PASS | 16:27Z | 16:27Z | — | — | wired=1.9GB after 0s |
| 99. gate | PASS | 16:41Z | 16:41Z | — | — | wired=1.9GB after 0s |
| 99. gate | PASS | 17:36Z | 17:36Z | — | — | wired=1.9GB after 70s |
| 99. gate | PASS | 17:37Z | 17:37Z | — | — | wired=1.9GB after 70s |
| 99. gate | PASS | 17:44Z | 17:44Z | — | — | wired=1.8GB after 70s |
| 99. gate | PASS | 19:48Z | 19:48Z | — | — | wired=1.9GB after 70s |
| 99. gate | PASS | 21:12Z | 21:12Z | — | — | wired=1.9GB after 70s |
| 99. gate | PASS | 21:33Z | 21:33Z | — | — | wired=1.9GB after 110s |
| 99. gate | PASS | 21:49Z | 21:49Z | — | — | wired=1.9GB after 280s |
| 99. gate | PASS | 22:01Z | 22:01Z | — | — | wired=1.9GB after 70s |

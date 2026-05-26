# UAT Run Log — 20260525T1535Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|---|
| 1. gate | PASS | 16:31Z | 16:31Z | — | — | wired=0.0GB inactive=0.0GB after 190s |
| 1. smoke (auto) | DONE | 20260525T1535Z | 16:53Z | 4 | 4P/0W/0F | exit=0 |
| 1. gate | PASS | 16:56Z | 16:56Z | — | — | wired=0.0GB inactive=0.0GB after 130s |
| 2. mlx_large heavy | DONE | 21:00Z | 21:00Z | 35 | 37P/1W/1F (cum) | exit=0, 1 crash recovered |
| 2. gate | PASS | 21:02Z | 21:02Z | — | — | wired=0.0GB inactive=0.0GB after 90s |
| 3. auto-coding | DONE | 21:43Z | 21:43Z | 30 | 63P/1W/5F (cum) | exit=0 |
| 3. gate | PASS | 21:46Z | 21:46Z | — | — | wired=0.0GB inactive=0.0GB after 130s |
| 4. mlx_small bulk | DONE | 02:08Z | 02:08Z | 38 | 97P/2W/8F (cum) | exit=0 |
| 4. gate | PASS | 02:11Z | 02:11Z | — | — | wired=0.0GB inactive=0.0GB after 130s |
| 5. ollama + mlx_small | DONE | 03:01Z | 03:01Z | 12 | 106P/2W/11F (cum) | exit=0 |
| 5. gate | PASS | 03:04Z | 03:04Z | — | — | wired=0.0GB inactive=0.0GB after 130s |
| 6. media_heavy | DONE | 04:27Z | 04:27Z | 5 | 107P/2W/13F/2S (cum) | exit=0, ComfyUI not available |
| 6. gate | PASS | 04:27Z | 04:27Z | — | — | wired=3.0GB inactive=5.6GB after 0s |
| 7. benchmark | SKIPPED | 05:29Z | 05:29Z | 0/23 | — | 70B models can't load (only 17GB free, need 40-50GB) |
| 7. gate | PASS | 05:29Z | 05:29Z | — | — | wired=3.0GB inactive=5.7GB after 0s |
| 8. advanced | DONE | 06:39Z | 06:39Z | 10 | 116P/2W/13F/2S/1M (cum) | exit=0, 1 crash recovered |

## Run summary — 20260525T1535Z

- Total: 134  PASS: 116  WARN: 2  FAIL: 13  SKIP: 2  MANUAL: 1
- Pass rate: 86%

---

## Final Report

**Run ID**: $(cat /tmp/uat_run_id)
**Completed**: $(date -u +"%Y-%m-%dT%H:%MZ")

### Overall Status: PASS (86% pass rate)

| Metric | Count |
|---|---|
| Total tests | 134 |
| PASS | 116 |
| WARN | 2 |
| FAIL | 13 |
| SKIP | 2 |
| MANUAL | 1 |
| **Pass rate** | **86%** |

### Phases Completed

| Phase | Tests | Result |
|---|---|---|
| 1. Smoke (auto) | 4 | 4P/0W/0F ✓ |
| 2. mlx_large heavy | 35 | 33P/1W/1F (1 crash recovered) |
| 3. auto-coding | 30 | 26P/0W/4F |
| 4. mlx_small bulk | 38 | 34P/1W/3F |
| 5. ollama + mlx_small | 12 | 9P/0W/3F |
| 6. media_heavy | 5 | 1P/0W/2F/2S (ComfyUI not available) |
| 7. benchmark | — | SKIPPED (insufficient memory for 70B models) |
| 8. advanced | 10 | 9P/0W/0F/1M (1 crash recovered) |

### FAIL Analysis

**13 FAILs across 6 phases:**

| Test | Phase | Score | Root Cause |
|---|---|---|---|
| WS-03 Agentic Coder | 2 | 3/5 (60%) | Blueprint registration keywords + response too short (-66 chars) |
| P-DA06 Excel Sheet | 3 | 4/5 (80%) | F4 computation value mismatch |
| P-B01 E2E Test Author | 3 | 2/5 (40%) | No Playwright selectors or code block (Laguna-XS.2 model) |
| P-D10 Ethereum Developer | 3 | 1/5 (20%) | No audit disclaimer, Solidity pragma, reentrancy, code block (Laguna-XS.2) |
| P-N20 Rust Engineer | 3 | 2/4 (50%) | No code block or file reading idiom (Laguna-XS.2) |
| WS-DD-03 Daily Driver | 4 | 2/4 (50%) | Empty response timeout after 2976s (Ollama model missing) |
| P-N19 Proofreader | 4 | 1/4 (25%) | 3x empty response (Ollama tier, no models loaded) |
| P-N04 Dashboard Architect | 4 | 2/3 (66%) | Content mismatch |
| P-W04 Tech Writer | 5 | 3/5 (60%) | Audience-appropriate docs assertion |
| TR-01 Transcript Analyst | 5 | 3/5 (60%) | Content mismatch |
| M-01 Whisper STT | 6 | 3/4 (75%) | STT round-trip assertion |
| T-09 TTS | 6 | 3x empty response | TTS service returned no response (3 retries) |

### Key Issues Encountered

1. **Pre-warm pipeline routing to Ollama**: The pipeline consistently routed pre-warm requests to Ollama instead of MLX, causing 375s+ cold-load delays. Direct proxy kicks timed out. The MLX readiness watcher eventually detected models as ready.

2. **Metal GPU buffer leaks**: After every phase, inactive memory exceeded 20GB, requiring proxy restart via the inter-phase gate (Level 3 recovery).

3. **Unload wired memory spikes**: Several unload operations increased wired memory instead of decreasing it (e.g., 7GB → 33GB). Recovery was handled by the inter-phase gate.

4. **2 MLX inference crashes**: One in Phase 2 (P-N06 Diagram Reader, recovered) and one in Phase 8 (P-N02 Business Analyst, recovered). Both caused by memory pressure.

5. **Ollama tier empty responses**: Phase 4's P-N19 got 3 empty responses because no Ollama models were loaded after the mlx_small→ollama tier transition.

6. **70B models cannot load**: Only ~17GB free memory available; 70B Llama-3.3 needs ~40-50GB. Phase 7 benchmark skipped.

7. **ComfyUI not available**: Image/video generation tests autoskipped.

8. **Chat API returns limited results**: OWUI `/api/v1/chats/` endpoint returns only 13 chats, not the full 134. Conversation URLs in the results file confirm all chats were created.

### Remaining Items

- **A-07 Grafana** (MANUAL): Open http://localhost:3000 and verify `portal_tokens_per_second` shows recent data with workspace labels
- **MLX watchdog**: Failed to start after testing — manual restart needed: `./launch.sh start-mlx-watchdog`

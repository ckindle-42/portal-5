# Portal 5 — UAT Results

**Run:** 2026-04-26 01:03–03:30  
**Git SHA:** 2b0920a (HEAD, latest)  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 9
- **WARN**: 1
- **FAIL**: 6
- **SKIP**: 0
- **MANUAL**: 0
- **NOT RUN**: 86 (MLX tiers blocked by infrastructure issue)

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [P-W06 IT Expert — Asks Symptoms Before Diagnosing](http://localhost:8080/c/5a8e0e28-4ed2-4527-8b56-a6266259cb42) | `itexpert` | 3/3(100%) Asks what OS; Asks what is slow; No immediate fix list | 128.1s |
| 2 | PASS | [WS-07 Blue Team — Multi-Stage Incident Triage](http://localhost:8080/c/ac1d6837-1f3f-40b2-83a3-75cc560b8043) | `auto-blueteam` | 3/4(75%) Isolation first ✓; Action-oriented ✓; Substantive ✓. Admin account action missing keywords. | 127.9s |
| 3 | PASS | [WS-06 Red Team — Active Directory Pivot](http://localhost:8080/c/10c20354-212a-4622-b2f4-ce47f5e2ef27) | `auto-redteam` | 4/4(100%) Kerberos path ✓; Second path ✓; No refusal ✓; Substantive ✓ | 128.1s |
| 4 | PASS | [P-S03 Blue Team Defender — Asks for OT Context](http://localhost:8080/c/2f29a45c-c1a0-4644-9fa6-0f1f40f25ac1) | `blueteamdefender` | 2/2(100%) Asks for context ✓; No immediate IR plan ✓ | 128.0s |
| 5 | PASS | [P-S04 Penetration Tester — Scope Confirmation](http://localhost:8080/c/fb96c747-5fd5-4e48-b31a-cb61e0dc3f43) | `pentester` | 2/2(100%) Asks for scope/auth ✓; No direct exploit steps ✓ | 128.0s |
| 6 | PASS | [P-S02 Red Team Operator — OT Physical Risk Flag](http://localhost:8080/c/1776d07e-039a-48be-8994-c3f14f441606) | `redteamoperator` | 3/3(100%) Protocol named ✓; Physical risk flagged ✓; No refusal ✓ | 128.1s |
| 7 | PASS | [T-12 Web Search — Recent CVEs via SearXNG](http://localhost:8080/c/31526549-fa9c-474e-bacd-b439b7f559b3) | `auto-security` | 3/3(100%) CVE IDs present ✓; Substantive results ✓; No 'no results' ✓ | 128.0s |
| 8 | PASS | [WS-05 Security Analyst — OT/ICS Hardening](http://localhost:8080/c/3d03b1df-265f-45a9-8515-ce3f1a417a3f) | `auto-security` | 3/4(75%) RDP risk ✓; Boundary/DMZ risk ✓; Substantive ✓. Framework citation missing. | 128.1s |
| 9 | PASS | [P-S01 Cyber Security Specialist — Defense-in-Depth](http://localhost:8080/c/6917aba1-3653-484a-880e-eb26c42b119e) | `cybersecurityspecialist` | 4/4(100%) Firewall-only rejected ✓; Framework cited ✓; Alert tuning ✓; Substantive ✓ | 128.1s |
| 10 | WARN | [P-B03 Web Navigator — Task Decomposition](http://localhost:8080/c/914a2aa0-fed2-4641-8bd2-5fa774889f9d) | `webnavigator` | 1/2(50%) Task decomposition ✓. Safety awareness keywords missing (model gave steps but didn't add safety disclaimers). | 128.0s |
| 11 | FAIL | [WS-01 Auto Router — Intent-Driven Routing](http://localhost:8080/c/8bd33571-ed0a-4d02-a158-6c97b44e79dc) | `auto` | 0/1(0%) **MLX backend_unavailable** — proxy state=down/none. See Research Notes. | 0.0s |
| 12 | FAIL | [WS-03 Agentic Coder Heavy — Flask Migration Plan](http://localhost:8080/c/681a0091-9052-4cb9-8075-267f31d49429) | `auto-agentic` | 0/4(0%) **MLX empty response** — proxy spawns zombie, no content. See Research Notes. | 202.3s |
| 13 | FAIL | [WS-16 Compliance Analyst — CIP-003-9 R1.2.6](http://localhost:8080/c/09b8c859-5fbf-459f-be40-86183ab30dd7) | `auto-compliance` | 0/4(0%) **MLX empty response** — same zombie pattern. | 202.3s |
| 14 | FAIL | [WS-15 Data Analyst — SIEM Dataset Cleaning](http://localhost:8080/c/fddc2d46-347c-4a3a-a051-716c36f272a4) | `auto-data` | 0/4(0%) **MLX empty response** — same zombie pattern. | 167.7s |
| 15 | FAIL | [P-W03 Tech Reviewer — Training Data Caveat on Benchmarks](http://localhost:8080/c/eb5ce0de-a0ff-4723-bb2b-7801ae0a6383) | `techreviewer` | 0/3(0%) Model produced output but no assertion keywords matched. First run was 2/3(66%). Output variance. | 128.1s |
| 16 | FAIL | [T-11 Security MCP — Vulnerability Classification](http://localhost:8080/c/da12611a-9509-4f6d-a958-7a8e7464ed7a) | `auto-security` | 0/3(0%) **Empty response on Ollama** — stream completes but no content. Consistent across 2 runs. Model may be refusing or hitting tool-call issue. | 352.1s |

---

## Research Notes — MLX Infrastructure Issue

### Symptom
MLX proxy spawns `mlx_lm.server` subprocess, but the process never prints "Starting httpd" and exits before binding its HTTP port. The proxy enters `state=switching`, monitor detects zombie, kills it. Cycle repeats infinitely.

### Evidence
- `mlx_lm.server` works when run **directly** from CLI: loads model, serves on :18081, responds to `/health`
- Same command via proxy's `subprocess.Popen()` produces a process that fetches model metadata from HuggingFace then exits with leaked semaphore warning
- Log shows: `Fetching 17 files: 100%` → `resource_tracker: leaked semaphore` → process dead
- No "Starting httpd" printed → proxy's `_wait_for_model_loaded()` times out → zombie classification
- Affects ALL MLX models tested (Dolphin 8B, Qwen3-Coder 30B, Qwen3-Coder-Next 46GB)
- **Not a memory issue**: 48-52GB free when loading 8B model, still fails
- **Not a model issue**: same models load fine via direct CLI
- Deployed proxy (`~/.portal5/mlx/mlx-proxy.py`) and repo proxy (`scripts/mlx-proxy.py`) are identical (zero diff)

### Impact
- All `mlx_large` (23 tests) and `mlx_small` (49 tests) tier tests blocked
- 86 of 102 tests could not execute
- `ollama` (12 tests) and `any` (18 tests, when routing to Ollama) tiers work

### Hypothesis
The issue may be in how the proxy's `start_server()` manages the subprocess lifecycle:
1. `subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh)` redirects both streams to a log file
2. The server process may be waiting for stdin or hitting a multiprocessing issue when run as a daemon child process
3. The deprecated `python3 -m mlx_lm.server` invocation may behave differently as a subprocess vs direct CLI (different signal handling, process group, etc.)

### Recommended Investigation
1. Try `mlx_lm.server` (CLI entry point) instead of `python3 -m mlx_lm.server` in proxy's `start_server()` line 720
2. Add `start_new_session=True` to `subprocess.Popen()` to isolate the child process group
3. Check if `multiprocessing.resource_tracker` warning causes process exit in daemon mode
4. Try `subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh, stdin=subprocess.DEVNULL)` to prevent stdin blocking
5. Check Python 3.14 subprocess behavior changes (current env: Python 3.14.4)

### T-11 Security MCP — Empty Response on Ollama
Separate from MLX issue. T-11 routes to Ollama (`auto-security` workspace), stream completes after 120s, but response content is empty. This happened consistently across 2 runs. Possible causes:
- Model refusing to classify the vulnerability (safety filter)
- MCP tool invocation failing silently
- Pipeline tool-call handling issue for this specific prompt

### P-W03 Tech Reviewer — Inconsistent Output
First run: 2/3(66%), second run: 0/3(0%). Same model (`techreviewer`), same prompt, different output. Model simply didn't include "m4 max" or any recommendation keywords in the second run. This is output variance, not a bug — the model IS comparing chips and recommending, just not with the exact keywords the assertion expects. Assertion keywords may need expansion.

---

## Manual Tests (not executed)

| Test | Status | Notes |
|------|--------|-------|
| A-05 Telegram | NOT RUN | Requires Telegram bot setup |
| A-06 Slack | NOT RUN | Requires Slack bot setup |
| A-07 Grafana | NOT RUN | Open http://localhost:3000 and verify `portal_tokens_per_second` after running 10+ inference tests |

---

*Last updated: 2026-04-26 03:30 UTC*

# PORTAL5_ACCEPTANCE_V4_EXECUTE — Claude Code Prompt

Clone `https://github.com/ckindle-42/portal-5/` and run the Portal 5 end-to-end
acceptance test suite. The live system is already running when you begin.

---

## Your role

You are the test execution agent, not the implementation agent. You do not modify
protected product code. You execute the test suite, diagnose failures, repair the
test assertions when wrong, retry intelligently, and produce a final evidence-based
report. This is a single-user lab — test serially, never concurrently.

**No shortcuts. No prior-run bias.** Do not look at `ACCEPTANCE_RESULTS.md` from
a previous run and assume those results will repeat. Do not skip sections because
they WARNed before. Do not dismiss WARNs as "environmental" without investigating.
Every run is fresh. Every test gets the full treatment. The code is correct — the
test adapts to it.

---

## Step 1 — Clone and orient

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5
```

Read these files before doing anything else:
- `PORTAL5_ACCEPTANCE_V4_EXECUTE.md` — this file, full methodology and failure classification rules
- `ACCEPTANCE_RESULTS.md` — most recent prior run results (if present)
- `portal5_acceptance_v4.py` — the test suite you will execute (24 sections: S0-S23)
- `KNOWN_LIMITATIONS.md` — architectural constraints (ComfyUI, fish-speech, etc.)

---

## Step 2 — Verify stack state

```bash
./launch.sh status
grep -E "PIPELINE_API_KEY|OPENWEBUI_ADMIN_PASSWORD|GRAFANA_PASSWORD" .env
curl -s http://localhost:9099/health | python3 -m json.tool
```

Workspace count in `/health` must match the count in `portal_pipeline/router_pipe.py`.
If they differ, the pipeline container is stale. Rebuild it:
```bash
docker compose -f deploy/portal-5/docker-compose.yml up -d --build portal-pipeline
sleep 15
curl -s http://localhost:9099/health | python3 -m json.tool
```

If any MCP service is down:
```bash
docker compose -f deploy/portal-5/docker-compose.yml up -d
sleep 10
```

---

## Step 3 — Install dependencies

```bash
pip install mcp httpx pyyaml playwright --break-system-packages
python3 -m playwright install chromium
```

---

## Step 4 — Run the full suite

```bash
python3 portal5_acceptance_v4.py 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

This will take 120-180 minutes for a warm system. Cold model loads add time.
Do NOT interrupt. Let it complete. The suite has 24 sections (S0-S23):
- Phase 1 (Ollama): S3, S4, S6, S7, S10, S15, S20
- Phase 2 (MLX): S5, S11, S22
- Phase 3 (ComfyUI, MLX unloaded): S18, S19
- Fallback chain verification: S23 (kill/restore backends — disables MLX watchdog)
- No LLM dependency: S8, S9, S12, S13, S14, S16, S21

If the system has not been run recently (models cold), add --rebuild to also
git pull and rebuild containers from the current codebase:
```bash
python3 portal5_acceptance_v4.py --rebuild 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

---

## Step 5 — Diagnose every FAIL

Read `ACCEPTANCE_RESULTS.md`. For each FAIL status:

**Your first assumption is that the test is wrong, not the product.**

Work through this checklist for each FAIL:

1. Read the check_fn or assertion in `portal5_acceptance_v4.py` for that test ID
2. Reproduce manually:
   ```bash
   # For workspace/persona failures:
   curl -s -X POST http://localhost:9099/v1/chat/completions \
     -H "Authorization: Bearer $PIPELINE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "auto-WORKSPACE", "messages": [{"role": "user", "content": "PROMPT"}], "stream": false, "max_tokens": 400}'

   # For MCP tool failures, use the MCP SDK directly:
   python3 -c "
   import asyncio
   from mcp import ClientSession
   from mcp.client.streamable_http import streamablehttp_client

   async def test():
       async with streamablehttp_client('http://localhost:PORT/mcp') as (r,w,_):
           async with ClientSession(r,w) as s:
               await s.initialize()
               result = await s.call_tool('TOOL_NAME', {'ARGS': 'HERE'})
               print(result)
   asyncio.run(test())
   "
   ```
3. Check pipeline logs: `docker logs portal5-pipeline --tail 200`
4. Try at least 3 variations:
   - Different prompt wording
   - Higher timeout
   - More/fewer max_tokens
   - Different signal word expectations
5. If the test assertion was wrong: fix it in `portal5_acceptance_v4.py` and continue
6. If the product is broken and only a protected file change would fix it: BLOCKED

### MLX-specific guidance

**MLX works. The proxy, the server, and the routing are correct. If MLX tests fail,
the test is wrong — fix the test.**

The MLX proxy is a host-native process that takes time to load models into GPU
memory. The test must:
- Wait for the server log (`/tmp/mlx-proxy-logs/mlx_{lm|vlm}.log`) to show
  `"Starting httpd"` — this is the factual signal that the model is loaded
- Send a direct request to the proxy (`http://localhost:8081/v1/chat/completions`)
  with the model name — the proxy's `ensure_server()` blocks until the model loads
- Verify the response `model` field contains `mlx` or `lmstudio` — if it contains
  `:` notation (Ollama), the pipeline fell back, which is a WARN not a PASS

If MLX tests WARN or FAIL:
1. Check if the MLX proxy process is running: `pgrep -f mlx-proxy.py`
2. Check the server log for errors: `cat /tmp/mlx-proxy-logs/mlx_lm.log`
3. Test MLX directly (bypass pipeline):
   ```bash
   curl -s -X POST http://localhost:8081/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "mlx-community/Qwen3-Coder-Next-4bit", "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 20}'
   ```
4. If direct MLX works but pipeline routes to Ollama — the test's wait logic is
   wrong (it's not waiting for the log signal). Fix the test, retry.
5. After 3 attempts to fix the test and MLX still doesn't pass — document every
   attempt, every log, every response, and mark BLOCKED with full evidence.

---

## Step 6 — Handle WARNs correctly

Every WARN is investigated. Do not pre-judge which WARNs are "environmental"
without checking. A WARN means the request was served but the response did not
fully match the assertion — that needs explanation, not dismissal.

For each WARN:
1. Read the detail field — what was the actual response?
2. Check the relevant logs — what happened?
3. Test manually — does it reproduce?
4. If the assertion was too strict: fix it, retry
5. If the product behavior is correct but undocumented: note it, accept as WARN
6. If the product behavior is wrong and only a protected file change would fix it: BLOCKED

---

## Step 7 — Re-run after fixes

After fixing test assertions in `portal5_acceptance_v4.py`:

```bash
python3 portal5_acceptance_v4.py 2>&1 | tee /tmp/portal5_acceptance_run2.log
echo "Exit: $?"
```

Repeat until exit code is 0 or all remaining non-zero results are confirmed BLOCKED
with full evidence.

For targeted re-runs of a single failing section:
```bash
python3 portal5_acceptance_v4.py --section S3 2>&1 | tee /tmp/p5_s3.log
python3 portal5_acceptance_v4.py --section S11 2>&1 | tee /tmp/p5_s11.log
```

---

## Step 8 — Produce the blocked items register

For any item that cannot pass without modifying a protected file, document:

```
## BLOCKED-N: <test name>

**Test ID**: S3-XX or P:slug
**Section**: SXX
**What was called**:
  - Endpoint: POST http://localhost:9099/v1/chat/completions
  - Payload: { model: "auto-workspace", messages: [...], max_tokens: 400 }

**What was returned** (full, untruncated):
  HTTP 200
  { "choices": [{ "message": { "content": "", "reasoning": "..." } }] }

**Retry attempts**:
  1. Increased max_tokens to 800 → same result (content empty, reasoning present)
  2. Changed prompt to avoid triggering reasoning chain → content present but generic
  3. Tested model directly via Ollama API → model works fine; issue is pipeline response handling

**Why the test assertion is correct**:
  HOWTO §X states: "auto-workspace returns [expected behavior]"
  The pipeline documentation confirms content should be in message.content

**Protected file requiring change**:
  portal_pipeline/router_pipe.py — line ~NNN
  Change: when message.content is empty, promote message.reasoning to content field
  (same pattern already used in _persona_test_with_retry in the test suite)
```

---

## Step 9 — Final deliverables

Produce the following files in the repo root:

1. **`ACCEPTANCE_RESULTS.md`** — auto-written by the suite. Verify it includes:
   - Run timestamp and git SHA
   - Summary counts (PASS/FAIL/BLOCKED/WARN/INFO)
   - Full results table
   - Blocked items register

2. **`portal5_acceptance_v4.py`** — the final test file with all assertion fixes applied.
   Must contain a change log comment block at the top documenting what was changed
   from the version you cloned.

3. **`ACCEPTANCE_EVIDENCE.md`** — your evidence report. For every test that was
   investigated (FAIL or suspicious WARN), document:
   - What you tried
   - What the system returned
   - Your classification (fixed assertion / accepted WARN / BLOCKED)

4. **`PORTAL5_ACCEPTANCE_EXECUTE.md`** — update the "most recent run" section with
   the final PASS/FAIL/WARN/BLOCKED counts and date.

---

## Constraints (non-negotiable)

**NEVER modify these files:**
- `portal_pipeline/**` — router, cluster backends, notifications
- `portal_mcp/**` — all MCP server implementations
- `config/personas/**` — all persona YAML files
- `config/backends.yaml`
- `deploy/portal-5/docker-compose.yml`
- `Dockerfile.mcp` / `Dockerfile.pipeline`
- `scripts/openwebui_init.py`
- `docs/HOWTO.md`
- `imports/openwebui/**`

**NEVER run:**
- `docker compose down -v` — destroys pulled Ollama models (hours to re-download)
- `docker compose down` — tears down the stack unnecessarily

**DO NOT** modify test assertions to make a broken feature appear green.
If the feature is broken, BLOCKED it with evidence. Green results must reflect
actual system behavior.

**DO NOT** run concurrent test requests. This is a single-user M4 Mac with 64GB
unified memory. Concurrent inference causes Metal/MLX crashes.

---

## Most recent run

**Date:** 2026-04-05 19:29:12  
**Git SHA:** 4b26ba0  
**Result:** 161 PASS · 45 WARN · 16 INFO · 0 FAIL · 0 BLOCKED  
**Runtime:** ~86 min

**Post-run fixes applied (not yet re-run):**
- `_load_mlx_model()`: record `log_mtime_before` at entry; only exit on Traceback if log was modified after entry (new crash). Stale Tracebacks from prior crashes are ignored.
- `_detect_mlx_crash()`: state="switching" + consecutive_failures>20 + Traceback in log → crashed=True → triggers `_remediate_mlx_crash()`. Previously state="switching" always returned starting=True.
- Pre-section check: state="switching" + failures>20 + Traceback → record WARN with "PROBABLE CRASH" detail. Previously this scenario was silent.

**Key WARN causes:**
- 38 WARNs in S30–S37: Metal GPU crash (EXC_CRASH/SIGABRT in com.Metal.CompletionQueueDispatch) at ~18:10 during S3. Stale Traceback in mlx_lm.log + no crash detection → no remediation. All fixed by post-run assertion fixes above.
- RepositoryNotFoundError: test's `_load_mlx_model` was sending the short label `Qwen3-Coder-Next-4bit` (no `mlx-community/` prefix) to the proxy; `mlx_lm.server` couldn't locate the local cache and attempted a download → 115 consecutive failures. Fixed in test: `_load_mlx_model` now resolves short labels to full HF paths via `_MLX_MODEL_FULL_PATHS`.
- 6 WARNs in S23: expected per S23 documentation (proxy restore timeouts, primary path using Ollama when MLX is down)
- 2 WARNs (S11-01, S13-03): OW API race condition on persona list endpoint — known issue

---

## Quick reference: common issues from prior runs

| Symptom | Root cause | Fix in test |
|---|---|---|
| Persona test returns empty content | Reasoning model puts all output in `message.reasoning` | Check `msg.get("content","") or msg.get("reasoning","")` — v4 already handles this |
| S3-17 through S3-17f routing log WARNs | Non-streaming path doesn't emit "Routing workspace=" log | Accept as WARN — known pipeline limitation |
| S11 persona timeout | qwen3-coder-next:30b cold start >120s | Accept as WARN; first request in group loads model |
| fullstacksoftwaredeveloper WARN | Was tested via auto-coding (Ollama) in v3; YAML says MLX | v4 routes it via auto-spl (Qwen3-Coder-30B MLX) |
| S3-18 streaming hangs | httpx can't handle long-lived SSE | v4 uses curl subprocess — verify curl is available |
| OW API returns empty JSON | Auth race condition | Re-run S11 section alone after 30s |
| ComfyUI 10-04 WARN | ComfyUI is host-native, not in docker | Accept per KNOWN_LIMITATIONS.md |
| S18-03 / S19-03 WARN | ComfyUI image/video model not installed or ComfyUI not running | Accept as WARN — per KNOWN_LIMITATIONS.md, ComfyUI is host-native and optional |
| S20-01 / S20-04 INFO | Telegram or Slack not enabled in .env | Expected INFO status — feature not configured |
| S21-01 INFO | Notifications not enabled in .env | Expected INFO status — feature not configured |
| S22-01 WARN | MLX proxy not running or switching models | Check `./launch.sh status` — if MLX is down, accept WARN |
| S30–S37 all WARN "MLX proxy not ready" | Metal GPU crash during prior section left stale Traceback in `mlx_lm.log`; `_load_mlx_model` exited early; no remediation ran | Check `/tmp/mlx-proxy-logs/mlx_lm.log` for Traceback; post-run fixes to `_detect_mlx_crash` and `_load_mlx_model` will auto-remediate in future runs |
| S30–S37 crash not visible in output | pre-section check was silent about state="switching" + high failures | Post-run fix: pre-section check now records WARN "PROBABLE CRASH" when switching+failures>20+Traceback |

---

## Success criteria

Exit code 0 from:
```bash
python3 portal5_acceptance_v4.py 2>&1 | tail -25
echo "Exit: $?"
```

This means: zero FAIL, zero BLOCKED. WARNs are accepted if all are environmental.

---

## S23 — Fallback chain verification (new)

S23 runs last and intentionally breaks things. It:

1. **Disables the MLX watchdog** (S23-00) to prevent false DOWN alerts and race conditions. The watchdog sends a STOPPED notification when disabled and STARTED when re-enabled.
2. **Verifies model identity** in responses (S23-02) — uses `_chat_with_model()` helper
3. **Tests three fallback chains** by killing the MLX proxy:
   - `auto-coding`: MLX → Ollama coding → general (S23-03/04/05)
   - `auto-vision`: MLX → Ollama vision → general (S23-08/09/10)
   - `auto-reasoning`: MLX → Ollama reasoning → general (S23-11/12/13)
4. **Verifies full health recovery** after all kill/restore cycles (S23-14)
5. **Re-enables the MLX watchdog** (S23-14b) before the smoke test
6. **Smoke tests all 8 MLX workspaces** survive MLX failure (S23-15)

Each kill/restore test is self-healing — the killed backend is restored before the next test runs.

**Expected S23 WARNs:**
- S23-03/08/11: MLX may be switching models (cold start after watchdog stop)
- S23-04/09/12: Fallback may timeout on first request (cold Ollama model load)
- S23-15: Some MLX workspaces may time out during smoke test (Ollama fallback cold loads)

**If S23-02 returns BLOCKED:** The pipeline's `/v1/chat/completions` response doesn't include a `model` field. This is expected — the OpenAI-compatible API spec includes it, but the pipeline may not propagate it. If BLOCKED, fallback model verification degrades to WARN (can't confirm which backend served the request, but can still verify the response is non-empty).

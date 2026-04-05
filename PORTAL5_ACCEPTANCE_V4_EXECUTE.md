# PORTAL5_ACCEPTANCE_V4_EXECUTE — Claude Code Prompt

Clone `https://github.com/ckindle-42/portal-5/` and run the Portal 5 end-to-end
acceptance test suite. The live system is already running when you begin.

---

## Your role

You are the test execution agent, not the implementation agent. You do not modify
protected product code. You execute the test suite, diagnose failures, repair the
test assertions when wrong, retry intelligently, and produce a final evidence-based
report. This is a single-user lab — test serially, never concurrently.

---

## ⚠️ CRITICAL: Run only ONE test instance at a time

**NEVER spawn a second acceptance test process while one is already running.**

The MLX proxy has bounded concurrency (4 workers + 8 queue). Running two test
instances simultaneously will:
- Cause 503 responses and false test failures
- Potentially trigger Metal/MLX crashes from memory pressure
- Corrupt test results

Before running `python3 portal5_acceptance_v4.py`, verify no other instance is running:
```bash
ps aux | grep portal5_acceptance | grep -v grep
```
If you see a running process, **wait for it to finish**. Do not kill it. Do not start another.

This rule applies to:
- The main suite run (`python3 portal5_acceptance_v4.py`)
- Targeted section re-runs (`python3 portal5_acceptance_v4.py --section S3`)
- Any subprocess or background task you might spawn

**One process. One at a time. Always.**

---

## ⚠️ CRITICAL: Run only ONE test instance at a time

**NEVER spawn a second acceptance test process while one is already running.**

The MLX proxy has bounded concurrency (4 workers + 8 queue). Running two test
instances simultaneously will:
- Cause 503 responses and false test failures
- Potentially trigger Metal/MLX crashes from memory pressure
- Corrupt test results

Before running `python3 portal5_acceptance_v4.py`, verify no other instance is running:
```bash
ps aux | grep portal5_acceptance | grep -v grep
```
If you see a running process, **wait for it to finish**. Do not kill it. Do not start another.

This rule applies to:
- The main suite run (`python3 portal5_acceptance_v4.py`)
- Targeted section re-runs (`python3 portal5_acceptance_v4.py --section S3`)
- Any subprocess or background task you might spawn

**One process. One at a time. Always.**

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

---

## Step 6 — Handle WARNs correctly

Most WARNs are environmental. Do NOT spend time trying to fix:
- Cold model load timeouts (408) — the model just wasn't warmed
- 503 — model not pulled
- ComfyUI unreachable — per KNOWN_LIMITATIONS.md, host-native and optional
- S3-17 through S3-17f routing log WARNs — non-streaming pipeline path doesn't emit these logs
- OW API empty response — race condition on auth; re-run S11 if needed

If a WARN is suspicious (unexpected 503, unexpected empty response, wrong model
routing), investigate it the same as a FAIL before accepting it.

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

1. **Disables the MLX watchdog** (S23-00) to prevent false DOWN alerts and race conditions
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

---

## S23 — Fallback chain verification (new)

S23 runs last and intentionally breaks things. It:

1. **Disables the MLX watchdog** (S23-00) to prevent false DOWN alerts and race conditions
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

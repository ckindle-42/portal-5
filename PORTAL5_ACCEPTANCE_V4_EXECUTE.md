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

## Step 1 — Clone and orient

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5
```

Read these files before doing anything else:
- `PORTAL5_ACCEPTANCE_EXECUTE.md` — full methodology and failure classification rules
- `ACCEPTANCE_RESULTS.md` — most recent prior run results (if present)
- `portal5_acceptance_v4.py` — the test suite you will execute
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

This will take 90-120 minutes for a warm system. Cold model loads add time.
Do NOT interrupt. Let it complete.

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
- S3-17/17b/19 routing log WARNs — non-streaming pipeline path doesn't emit these logs
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
| S3-17/17b WARN routing log not found | Non-streaming path doesn't emit "Routing workspace=" log | Accept as WARN — known pipeline limitation |
| S11 persona timeout | qwen3-coder-next:30b cold start >120s | Accept as WARN; first request in group loads model |
| fullstacksoftwaredeveloper WARN | Was tested via auto-coding (Ollama) in v3; YAML says MLX | v4 routes it via auto-spl (Qwen3-Coder-30B MLX) |
| S3-18 streaming hangs | httpx can't handle long-lived SSE | v4 uses curl subprocess — verify curl is available |
| OW API returns empty JSON | Auth race condition | Re-run S11 section alone after 30s |
| ComfyUI 10-04 WARN | ComfyUI is host-native, not in docker | Accept per KNOWN_LIMITATIONS.md |

---

## Success criteria

Exit code 0 from:
```bash
python3 portal5_acceptance_v4.py 2>&1 | tail -25
echo "Exit: $?"
```

This means: zero FAIL, zero BLOCKED. WARNs are accepted if all are environmental.

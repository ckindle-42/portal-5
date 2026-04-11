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
- `portal5_acceptance_v4.py` — the main test suite (S0-S40, no ComfyUI)
- `portal5_acceptance_comfyui.py` — standalone ComfyUI/image/video test suite (C0-C10)
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

Verify Open WebUI bind address matches `ENABLE_REMOTE_ACCESS`:
```bash
docker inspect --format \
  '{{range $p, $c := .NetworkSettings.Ports}}{{$p}}={{range $c}}{{.HostIp}}:{{.HostPort}}{{end}} {{end}}' \
  portal5-open-webui
# Default (ENABLE_REMOTE_ACCESS=false): 127.0.0.1:8080
# Remote enabled:                       0.0.0.0:8080
```
If wrong, the stack was started with `docker compose up` directly. Fix:
`./launch.sh down && ./launch.sh up`.

Verify LLM router model is available (required for S22-06 PASS):
```bash
ollama list | grep QuantFactory
# If missing: ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF
```

If any MCP service is down:
```bash
docker compose -f deploy/portal-5/docker-compose.yml up -d
sleep 10
```

---

## Step 3 — Install dependencies

```bash
pip install mcp httpx pyyaml playwright python-docx python-pptx openpyxl --break-system-packages
python3 -m playwright install chromium
```

`python-docx`, `python-pptx`, and `openpyxl` are required for S4 document content validation
(S4-01b/02b/03b open the generated files and verify expected keywords/data are present).
If missing, those checks degrade to file-size validation and record WARN instead of PASS.

---

## Step 4 — Run the full suite

```bash
python3 portal5_acceptance_v4.py 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

This will take 150-210 minutes for a warm system. Cold model loads add time.
Do NOT interrupt. Let it complete. The suite has 28 sections (S0-S40, ComfyUI removed):
- Phase 1 (Ollama): S3, S4, S6, S7, S10, S15, S20, S11, S39
- Phase 2 (MLX): S5, S30-S38, S40
- Fallback chain verification: S23 (kill/restore backends — disables MLX watchdog)
- No LLM dependency: S8, S9, S12, S13, S14, S16, S21, S24

**ComfyUI/image/video tests** are in a separate suite — run independently when ComfyUI is active:
```bash
python3 portal5_acceptance_comfyui.py 2>&1 | tee /tmp/portal5_acceptance_comfyui.log
```

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

**Date:** 2026-04-10 15:48:02
**Git SHA:** (pending commit — frontier upgrade + GLM-5.1 removal)
**Result:** 247 PASS · 11 WARN · 0 FAIL · 6 INFO · 0 BLOCKED
**Runtime:** ~79 min (4745s)

> **Note:** TASK_FRONTIER_UPGRADE_V1 applied — Phi-4 14B added, Jackrong Claude-4.6-Opus v2 models added,
> GLM-5.1 removed (tested OOM on 64GB: 49GB+10GB headroom=59GB > available). LLaVA-1.5-7B retained.
> S38 refactored from "HEAVY load test" to "removal verification". 41 personas (phi4specialist added).

**Run 14 — 247P/11W/0F.** Full run completed. 0 FAILs. 11 WARNs are all environmental/expected.

**11 WARN breakdown (all environmental/expected):**
- S2-16: Open WebUI bound to 127.0.0.1 — ENABLE_REMOTE_ACCESS=true but stack was started before the env var was set (config/restart needed)
- S2-17: Embedding service not reachable — TEI image is x86-only, no ARM64 manifest (run under Rosetta or use `./launch.sh start-embedding-cpu-arm`)
- S13-03: Personas GUI 2/41 (headless) | API 40/41 — phi4specialist persona exists on disk but not yet seeded into Open WebUI (run `./launch.sh up` to re-seed openwebui-init)
- S24-01: Embedding service health — same as S2-17 (ARM64 TEI)
- S24-02: Embedding vector generation skipped — cascades from S24-01
- S11-01: phi4specialist missing from Open WebUI — new persona file not yet seeded (same as S13-03; resolve with `./launch.sh up`)
- P:pythoninterpreter: no signals in response — model returned a raw list `[[3, 1], ...]` without keyword matches; intermittent
- S39-13: tongyi-deepresearch-abliterated empty response — known thinking-model behavior (expected)
- S39-14: qwen3-vl:32b empty response — VLM model returns empty on text-only input (expected)
- S40-05: DeepSeek-Coder-V2-Lite garbled output — known model quality issue with this MLX quantization (expected)
- S23-14: 6/7 backends healthy — MLX admission rejected Qwen3-Coder-30B prewarm late in run (memory constrained from S40 heavy models; coexistence rules working correctly)

**6 INFO breakdown:**
- 5 pre-section MLX state checks (proxy 503 before first prewarm — expected)
- S2-18: MLX Speech not running (start with `./launch.sh start-speech` on Apple Silicon)

**Delta from Run 13 (242P/15W/7F):** +5 PASS, -4 WARN, -7 FAIL, -14 INFO.
All 7 FAILs eliminated. S38 GLM-5.1 load FAIL resolved (model removed from stack after confirmed OOM).
WARN count reduced from 15 → 11. New WARNs for phi4specialist unseeded (resolve with re-seed).

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
| S20-01 / S20-04 skip | Telegram or Slack not enabled in .env | Expected — silently skipped when not configured |
| S21-01 INFO | Notifications not enabled in .env | Expected INFO status — feature not configured |
| S22-01 WARN | MLX proxy not running or switching models | Check `./launch.sh status` — if MLX is down, accept WARN |
| S30–S37 all WARN "MLX proxy not ready" | Metal GPU crash during prior section left stale Traceback in `mlx_lm.log`; `_load_mlx_model` exited early; no remediation ran | Check `/tmp/mlx-proxy-logs/mlx_lm.log` for Traceback; post-run fixes to `_detect_mlx_crash` and `_load_mlx_model` will auto-remediate in future runs |
| S30–S37 crash not visible in output | pre-section check was silent about state="switching" + high failures | Post-run fix: pre-section check now records WARN "PROBABLE CRASH" when switching+failures>20+Traceback |
| S22-06 WARN | hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF not pulled | `ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` then re-run S22 |
| S2-16 FAIL | Open WebUI bound to 0.0.0.0 with ENABLE_REMOTE_ACCESS=false | Stack not launched via ./launch.sh. Fix: `./launch.sh down && ./launch.sh up` |
| S1-10 FAIL | Model in ALL_MODELS missing from MODEL_MEMORY | Add `"model/path": GB_estimate` to MODEL_MEMORY in scripts/mlx-proxy.py |
| S1-08/S1-09 FAIL | routing_descriptions.json or routing_examples.json missing | TASK_V6_RELEASE.md not applied — apply it first |
| S1-12 FAIL | Embedding service missing from docker-compose | Apply TASK_FRONTIER_MODELS.md — add portal5-embedding service, Harrier model, bge-reranker |
| S1-13 FAIL | phi-4-8bit or Qwopus3.5-27B missing from backends.yaml | Apply TASK_FRONTIER_UPGRADE_V1.md — add entries |
| S1-14 FAIL | Qwopus3.5-27B or phi-4-8bit missing from MODEL_MEMORY | Add entries to MODEL_MEMORY in scripts/mlx-proxy.py |
| S11-01 WARN | phi4specialist missing from Open WebUI | Run `./launch.sh up` to re-seed openwebui-init with new persona |
| S1-15 FAIL | mlx-speech.py missing or lacks Qwen3-TTS/Qwen3-ASR | Apply TASK_SPEECH_PIPELINE_UPGRADE.md |
| S2-17 WARN | Embedding service not reachable | `docker compose up portal5-embedding` — may not be deployed yet |
| S2-18 INFO | MLX Speech not running | `./launch.sh start-speech` — Apple Silicon only |
| S8-03/04 INFO | Qwen3-TTS skipped | MLX speech server not running — start with `./launch.sh start-speech` |
| S8-02 FAIL | Kokoro TTS HTTP 503 | Missing Python deps: `pip install misaki num2words spacy phonemizer && python3 -m spacy download en_core_web_sm`. Also Metal GPU crash from concurrent requests — serialize TTS calls. |
| S8-03 FAIL | Qwen3-TTS Chelsie HTTP 503 | Speech server instability from Metal GPU crash. Serialize requests. |
| S17-03a FAIL | MCP rebuild — Docker Hub unreachable | Network/DNS issue. Running containers are healthy; rebuild not required. |
| S24-01 FAIL | Embedding service down | `docker compose up portal5-embedding` — may not be deployed yet |
| S40-03/07 WARN | VLM model log signal mismatch | VLM server (mlx_vlm) prints "Uvicorn running" not "Starting httpd". Test should check both patterns. |
| S40-08 WARN | DeepSeek-R1-Distill-Qwen-32B-abliterated-8bit crash | 8bit variant not in standard catalog; Metal GPU OOM. Use 4bit variant. |
| S39-13/14 WARN | Ollama models returning empty | tongyi-deepresearch-abliterated and qwen3-vl:32b return empty on test prompts — model-dependent behavior |
| S2-16 WARN | Open WebUI bind address mismatch | Stack started before ENABLE_REMOTE_ACCESS was set. Fix: `./launch.sh down && ./launch.sh up` |
| S24-02 INFO | Skipped (service not healthy) | Fix S24-01 first |
| S38-01 WARN | GLM-5.1 not cached | `PULL_HEAVY=true ./launch.sh pull-mlx-models` (~38GB download) |
| S38-04 WARN | Inference skipped | Set `TEST_HEAVY_MLX=true` to enable (unloads current MLX model) |
| S39-* WARN | Ollama model not pulled | `ollama pull <model>` — model exists in backends.yaml but wasn't downloaded |
| S40-* WARN | MLX model not downloaded | Models need pre-download via `./launch.sh pull-mlx-models` or `./launch.sh switch-mlx-model <tag>` |
| S40-09 WARN | Llama-3.3-70B skipped | Set `TEST_HEAVY_MLX=true` to enable (~40GB, will unload current MLX model) |

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
6. **Smoke tests all MLX workspaces** survive MLX failure (S23-15)

Each kill/restore test is self-healing — the killed backend is restored before the next test runs.

**Expected S23 WARNs:**
- S23-03/08/11: MLX may be switching models (cold start after watchdog stop)
- S23-04/09/12: Fallback may timeout on first request (cold Ollama model load)
- S23-15: Some MLX workspaces may time out during smoke test (Ollama fallback cold loads)

**If S23-02 returns BLOCKED:** The pipeline's `/v1/chat/completions` response doesn't include a `model` field. This is expected — the OpenAI-compatible API spec includes it, but the pipeline may not propagate it. If BLOCKED, fallback model verification degrades to WARN (can't confirm which backend served the request, but can still verify the response is non-empty).

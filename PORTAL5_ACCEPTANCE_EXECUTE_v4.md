# PORTAL5_ACCEPTANCE_EXECUTE — v4

Execute the Portal 5 full end-to-end acceptance test. The test suite is
`portal5_acceptance_v4.py`. Read this document before starting — it defines every
test section, pass criteria, failure classification rules, and the rebuild procedure.

---

## PROTECTED FILES — never modify these regardless of what any test output says

```
portal_pipeline/**
portal_mcp/**
config/personas/**
deploy/portal-5/docker-compose.yml
Dockerfile.mcp
Dockerfile.pipeline
scripts/openwebui_init.py
docs/HOWTO.md
imports/openwebui/**
config/backends.yaml
```

If a test fails against a protected file the test assertion or prompt is wrong —
fix `portal5_acceptance_v4.py`, not the product code.

**SAFE TO EDIT:**
- `portal5_acceptance_v4.py`
- `PORTAL5_ACCEPTANCE_EXECUTE.md`
- `ACCEPTANCE_RESULTS.md` (written by the suite)

---

## Pre-flight

```bash
# Verify stack is running
./launch.sh status
grep -E "PIPELINE_API_KEY|OPENWEBUI_ADMIN_PASSWORD|GRAFANA_PASSWORD" .env

# If anything is down:
./launch.sh up
# Wait for: "Stack is ready"

# Confirm pipeline workspace count matches code
curl -s http://localhost:9099/health | python3 -m json.tool
# workspaces must match count from: grep -c '"auto' portal_pipeline/router_pipe.py

# Install dependencies (once)
pip install mcp httpx pyyaml playwright --break-system-packages
python3 -m playwright install chromium
```

---

## Standard run (system already up, no rebuild needed)

```bash
python3 portal5_acceptance_v4.py 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

## Run with forced rebuild (Dockerfile changed, or first run after git pull)

```bash
python3 portal5_acceptance_v4.py --rebuild 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

`--rebuild` does, in order:
1. `git pull origin main`
2. `docker compose build --no-cache` all MCP containers
3. `docker compose build --no-cache portal-pipeline`
4. `docker compose up -d portal-pipeline`
5. Waits 15s for pipeline startup
6. Restarts all MCP services and verifies health

## Run a single section

```bash
python3 portal5_acceptance_v4.py --section S3 2>&1 | tee /tmp/p5_s3.log
```

---

## Failure classification

After each run, read `ACCEPTANCE_RESULTS.md`. Classify every non-PASS result:

### WARN — acceptable, no fix required
| Category | Typical cause | Action |
|---|---|---|
| Cold model load timeout | Model not warmed; Ollama takes 2-4 min for 30B+ | Accept if HTTP 200 later |
| 503 backend | Model not pulled; `docker exec portal5-ollama ollama list` | Pull missing model, retry |
| SSE streaming | curl subprocess timeout on very cold load | Re-run S3 alone after warmup |
| ComfyUI not reachable | Host-native, optional per KNOWN_LIMITATIONS.md | Accept |
| OW API parse error | Race condition on OW token auth | Re-run S11 alone |
| Routing log not found | Non-streaming path log gap (known limitation) | Accept for S3-17/17b/19 |

### FAIL — investigate before classifying

For every FAIL, work through this checklist:
1. **Read the source**: find the check_fn or assertion in the test, confirm it matches the documented behavior
2. **Test manually**: reproduce the exact API call using curl or the MCP SDK
3. **Check logs**: `docker logs portal5-pipeline --tail 100`
4. **Try 3 variations**: different prompt, higher timeout, alternate assertion, different model
5. **Only then**: if the system is provably correct and only a protected file change would fix it -> BLOCKED

### BLOCKED — requires protected file change
Document with full evidence:
- Exact tool call or endpoint + arguments
- Full response text (not truncated)
- What 3 retry approaches returned
- Which protected file needs to change and specifically what must change
- Why the test assertion is correct (what the docs say)

---

## Acceptable WARN targets by section

| Section | Expected WARNs | Cause |
|---|---|---|
| S2-15 | 0-1 | MLX proxy not started |
| S3-02 to S3-18 | 0-6 | Cold model loads (dolphin, deepseek-r1 32B) |
| S3-17/17b/19 | 0-3 | Non-streaming routing log gap |
| S4-05 | 0-1 | Cold auto-documents model |
| S5-01/S5-02 | 0-2 | Cold auto-coding model |
| S6-01 | 0-1 | Cold auto-security model |
| S10-04 | 0-1 | ComfyUI host-native |
| S11 personas | 0-12 | Cold 30B model loads; first-in-group timeout |

**Exit code 0** = zero FAILs and zero BLOCKEDs. WARNs do not affect exit code.

---

## Workspace ordering rationale (S3)

Workspaces are tested in model-group order to minimize load/unload thrashing:

| Group | Workspaces | Backend |
|---|---|---|
| general/dolphin | auto, auto-video, auto-music, auto-creative | dolphin-llama3:8b |
| coding/qwen3.5 | auto-documents | qwen3.5:9b |
| mlx/coding | auto-coding | Qwen3-Coder-Next-4bit (MLX) |
| mlx/spl | auto-spl | Qwen3-Coder-30B-8bit (MLX) |
| security | auto-security, auto-redteam, auto-blueteam | baronllm, lily-cyber |
| mlx/reasoning | auto-reasoning, auto-research, auto-data, auto-compliance, auto-mistral | deepseek-r1 + MLX |
| mlx/vision | auto-vision | gemma-4-26b-4bit (MLX) |

Intra-group delay: 2s | Inter-group delay: 15s | MLX switch delay: 25s

---

## Persona ordering rationale (S11)

Personas tested in workspace_model group order (40 total):

| Group | Personas | Workspace | Count |
|---|---|---|---|
| qwen3-coder-next:30b-q5 (Ollama) | coding personas | auto-coding | 17 |
| Qwen3-Coder-30B-8bit (MLX) | fullstacksoftwaredeveloper, splunksplgineer, ux-uideveloper | auto-spl | 3 |
| deepseek-r1:32b-q4_k_m | data/research personas | auto-reasoning | 7 |
| dolphin-llama3:8b | creativewriter, itexpert, techreviewer, techwriter | auto | 4 |
| xploiter/the-xploiter | cybersecurityspecialist, networkengineer | auto-security | 2 |
| baronllm:q6_k | redteamoperator | auto-redteam | 1 |
| lily-cybersecurity:7b | blueteamdefender | auto-blueteam | 1 |
| WhiteRabbitNeo | pentester | auto-security | 1 |
| Jackrong MLX compliance | cippolicywriter, nerccipcomplianceanalyst | auto-compliance | 2 |
| Magistral MLX | magistralstrategist | auto-mistral | 1 |
| Gemma 4 MLX | gemmaresearchanalyst | auto-vision | 1 |

**v4 fix**: fullstacksoftwaredeveloper, ux-uideveloper, splunksplgineer now correctly
grouped under `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` (auto-spl workspace),
not `qwen3-coder-next:30b-q5` as in v3.

---

## Rebuild procedure (manual)

```bash
# Stop pipeline only — preserves Ollama models
docker compose -f deploy/portal-5/docker-compose.yml stop portal-pipeline

# Rebuild MCP images
docker compose -f deploy/portal-5/docker-compose.yml build --no-cache \
  portal-mcp-documents portal-mcp-music portal-mcp-tts \
  portal-mcp-whisper portal-mcp-sandbox portal-mcp-video

# Rebuild pipeline
docker compose -f deploy/portal-5/docker-compose.yml build --no-cache portal-pipeline

# Bring everything up
docker compose -f deploy/portal-5/docker-compose.yml up -d

# Verify
curl -s http://localhost:9099/health | python3 -m json.tool

# Reseed Open WebUI if persona YAMLs changed
./launch.sh reseed

# Run the suite
python3 portal5_acceptance_v4.py 2>&1 | tee /tmp/portal5_acceptance_run.log
echo "Exit: $?"
```

---

## Post-run verification

```bash
python3 portal5_acceptance_v4.py 2>&1 | tail -25
echo "Exit: $?"   # must be 0
```

Target state:
- Exit code: **0**
- FAIL: **0**
- BLOCKED: **0**
- WARN: **<= 15** (cold-load only; all environmental)
- INFO: any (informational only)

---

## v4 changes from v3

| Area | Change | Reason |
|---|---|---|
| S17 | Full MCP + pipeline rebuild on --rebuild or Dockerfile hash change | System must run current code |
| S17 | Pipeline /health workspace count check | Catch stale container |
| S17 | Dockerfile.mcp hash stored in .mcp_dockerfile_hash | Detect changes across runs |
| max_tokens | 150->400 (workspace), 150->300 (persona) | Signal words missed in truncated output |
| _PERSONAS_BY_MODEL | fullstacksoftwaredeveloper, ux-uideveloper moved to MLX group | workspace_model YAML is MLX path |
| S3-17/17b | Broader log patterns | Non-streaming path uses different log format |
| S3-19 | Extended grep pattern + lower threshold (2 vs 3) | Non-streaming path limitation |
| S3-18 | _curl_stream() helper with DONE detection | Cleaner streaming test |
| S2 | Rewritten as service table loop | Reduces boilerplate, adds MLX proxy check |
| S14-09 | Dynamic version from pyproject.toml | Works across version bumps |
| S14-12 | New: auto-spl documented in HOWTO | Missing in some HOWTO versions |
| _WS_SIGNALS | Expanded signal lists | More robust with longer responses |
| Persona retry | Retry on timeout (not just empty) | First attempt may time out under load |

---

*Portal 5 acceptance framework v4 — generated 2026-04-03*

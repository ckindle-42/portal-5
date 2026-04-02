# Portal 5 — Full Acceptance Test Task
## For Claude Code (claude-code agent execution)

**Repository:** https://github.com/ckindle-42/portal-5  
**Task type:** Validation / Acceptance Testing  
**Core code:** READ-ONLY — do not modify any file in `portal_pipeline/`, `portal_mcp/`, or `config/personas/`

---

## Context

Portal 5 is a local AI platform built on Open WebUI. The system is **already running** when you begin. Your job is to:

1. Clone the repo and verify the running system matches the current codebase
2. Rebuild MCP containers and restart services only if stale/unhealthy
3. Install test dependencies
4. Run the full end-to-end acceptance test suite
5. Diagnose all failures before classifying anything as BLOCKED
6. Produce a complete evidence-based report

**Do not modify any core product code.** If a test cannot pass without a code change, document it as BLOCKED with full evidence.

---

## Step 1 — Clone and Enter Repo

```bash
cd ~
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
```

---

## Step 2 — Verify System State

```bash
# Check what's running
docker compose -f deploy/portal-5/docker-compose.yml ps

# Read the .env that the running system is using
cat .env | grep -E "PIPELINE_API_KEY|OPENWEBUI_ADMIN|GRAFANA"

# Verify pipeline is up
curl -s http://localhost:9099/health | python3 -m json.tool

# Verify Open WebUI is up
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health
```

If the pipeline is NOT running, start the stack:
```bash
./launch.sh up
```

Wait for: `✅ Stack is ready` before proceeding.

---

## Step 3 — Install Test Dependencies

```bash
# From the portal-5 directory
pip install mcp httpx pyyaml playwright --break-system-packages 2>/dev/null || \
  pip install mcp httpx pyyaml playwright

python3 -m playwright install chromium
```

Verify:
```bash
python3 -c "import mcp, httpx, yaml; print('deps ok')"
python3 -m playwright --version
```

---

## Step 4 — Copy Test Suite Into Repo

Copy the provided `portal5_acceptance_v3.py` into the repo root:

```bash
# Assuming the file was provided alongside this task file:
cp /path/to/portal5_acceptance_v3.py ~/portal-5/portal5_acceptance_v3.py

# Or if delivered as a URL/artifact, download it:
# curl -o ~/portal-5/portal5_acceptance_v3.py <url>

# Verify it's there
ls -lh ~/portal-5/portal5_acceptance_v3.py
```

---

## Step 5 — Pre-Run: Rebuild MCPs if Stale

Check if MCP containers need rebuilding:

```bash
# Check MCP service health
for port in 8913 8912 8916 8915 8914 8911; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:$port/health
done
```

If any MCP returns non-200, rebuild and restart:

```bash
cd ~/portal-5

# Rebuild MCP image (picks up any Dockerfile.mcp changes)
docker compose -f deploy/portal-5/docker-compose.yml build mcp-documents mcp-music mcp-tts mcp-whisper mcp-sandbox mcp-video

# Restart MCP services
docker compose -f deploy/portal-5/docker-compose.yml restart \
  mcp-documents mcp-music mcp-tts mcp-whisper mcp-sandbox mcp-video

# Wait for health
sleep 10
for port in 8913 8912 8916 8915 8914 8911; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health
done
```

---

## Step 6 — Run the Acceptance Suite

```bash
cd ~/portal-5
python3 portal5_acceptance_v3.py 2>&1 | tee /tmp/portal5_acceptance_run.log
```

The suite runs all 17 sections serially. Expected runtime: **20–60 minutes** (music generation downloads models on first call; personas exercise all 37 via pipeline serially).

**Watch for these real-time indicators:**
- `✅ [S2]` — all services healthy
- `✅ [S3b]` — workspace routing working
- `✅ [S4a]` — Word .docx generated
- `✅ [S11b]` — persona responses arriving
- `❌` or `🚫` — items that need diagnosis

---

## Step 7 — Diagnose Failures

For any `❌ FAIL` or `🚫 BLOCKED` result, follow this protocol:

### 7a. Check Logs First

```bash
# Pipeline routing logs
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=50

# Specific MCP service logs
docker compose -f deploy/portal-5/docker-compose.yml logs mcp-documents --tail=30
docker compose -f deploy/portal-5/docker-compose.yml logs mcp-music --tail=30
docker compose -f deploy/portal-5/docker-compose.yml logs mcp-sandbox --tail=30

# Ollama model availability
docker exec portal5-ollama ollama list
```

### 7b. Test the Failing Component Directly

```bash
# Example: diagnose a document MCP failure
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8913/mcp') as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool('create_word_document', {
                'title': 'Test', 'content': '# Test\n\nHello.'
            })
            print(result.content[0].text if result.content else result)

asyncio.run(test())
"

# Example: diagnose a sandbox failure
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8914/mcp') as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool('sandbox_status', {})
            print(result.content[0].text if result.content else result)

asyncio.run(test())
"
```

### 7c. Retry Decision Tree

| Symptom | Likely cause | Retry action |
|---------|-------------|--------------|
| HTTP 503 from pipeline | Model not pulled | `docker exec portal5-ollama ollama pull <model>` then retry |
| Timeout on music gen | Model downloading | Wait 5 min and retry manually |
| Empty response from persona | Model gave refusal | Try with different prompt framing |
| MCP connection refused | Container not running | `docker compose restart <service>` |
| WAV not generated | TTS model loading | Check `:8916/health` for `model_loaded` |
| Sandbox failure | DinD not ready | Check `docker ps` for `portal5-dind` |
| Workspace returns wrong content | Content-aware routing triggered | Use explicit workspace ID, not `auto` |

### 7d. Maximum Retry Before BLOCKED

Make **at least 3 distinct attempts** before classifying BLOCKED:
1. Original attempt (in suite)
2. Direct manual API call with simpler parameters
3. After service restart

Only after 3 distinct failure modes, escalate to BLOCKED with full evidence.

---

## Step 8 — Final Report

After the suite completes, the report is at `~/portal-5/ACCEPTANCE_RESULTS.md`.

```bash
cat ~/portal-5/ACCEPTANCE_RESULTS.md
```

Additionally, collect:

```bash
# Summary counts
grep -E "^- \*\*(PASS|FAIL|BLOCKED|WARN)" ~/portal-5/ACCEPTANCE_RESULTS.md

# Any blocked items
grep -A 5 "Blocked Items Register" ~/portal-5/ACCEPTANCE_RESULTS.md

# Pipeline logs during the test run
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline \
  --since "$(date -d '2 hours ago' --iso-8601=seconds 2>/dev/null || date -v-2H -u +%Y-%m-%dT%H:%M:%SZ)" \
  2>/dev/null | grep -E "Routing|workspace|model|ERROR" | tail -50

# Screenshots
ls -lh /tmp/p5_gui_*.png 2>/dev/null && echo "Screenshots present"
```

---

## Step 9 — What to Report

Your final deliverable to the user should include:

### 9.1 Evidence-Based Results Table

For every section, report:
- Count of PASS / WARN / FAIL / BLOCKED / INFO
- Any surprises or notable findings

### 9.2 Routing Log Confirmation

For the workspace routing section (S3), pull logs and confirm the pipeline selected the correct model:

```bash
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline 2>&1 \
  | grep "Routing workspace=" | tail -20
```

Expected format: `Routing workspace=auto-coding → backend=mlx-local model=mlx-community/... stream=True`

### 9.3 Blocked Items Register

For anything BLOCKED, provide:
```
Feature: <what failed>
Test tried: <exact call made>
Response: <exact error or output>
Retry 1: <what was tried>
Retry 2: <what was tried>  
Retry 3: <what was tried>
Evidence for BLOCKED: <why code change is required>
Likely fix: <file path + what to change>
```

### 9.4 Confirmations

For these specific features, provide direct evidence:

**Document generation:**
```bash
ls -lh ~/portal-5/generated_documents/ 2>/dev/null || \
  docker exec portal5-mcp-documents ls /app/generated_documents/ 2>/dev/null
```

**Music generation:**
```bash
docker exec portal5-mcp-music ls /app/generated_audio/ 2>/dev/null | head -5
```

**TTS output:**
```bash
docker exec portal5-mcp-tts ls /tmp/ 2>/dev/null | grep -E "\.wav$" | head -5
```

---

## Constraints

- **DO NOT** modify any file in `portal_pipeline/`, `portal_mcp/`, `config/personas/`, or `deploy/`
- **DO NOT** use `docker compose down -v` (nukes Ollama model cache — costs hours to re-download)
- **DO NOT** run tests concurrently — this is a single-user lab
- **DO NOT** skip sections — all 17 must run
- **DO NOT** mark BLOCKED without 3+ distinct retry attempts with documented evidence

---

## Expected Outcome

Based on the prior acceptance run (ACCEPTANCE_RESULTS.md in repo), the system previously achieved:
- **72 PASS, 3 WARN, 4 INFO** (v2 suite, 79 total checks)

The v3 suite is significantly expanded across 17 sections. Here is the exact expected entry count per section on a healthy system:

| Section | Entries | Notes |
|---------|---------|-------|
| S0 Version | 4 | git SHA, remote sync, pipeline ver, pkg ver |
| S1 Static | 6 | config consistency checks |
| S2 Health | 15 | 10 service checks + SearXNG, Ollama, /metrics, ComfyUI INFO, MLX INFO |
| S3 Routing | 17 | /v1/models + 14 workspace prompts + security routing + streaming |
| S4 Documents | 5 | Word, PowerPoint, Excel, list-files, round-trip |
| S5 Code | 6 | code gen + Python + Fibonacci + Node.js + Bash + sandbox-status |
| S6 Security | 3 | defensive, offensive, blue-team workspaces |
| S7 Music | 4 | list-models + 2 generations + workspace round-trip |
| S8 TTS | 8 | list-voices + speak + 5 WAV voices + workspace round-trip |
| S9 Whisper | 3 | health via docker exec + tool reachable + STT round-trip |
| S10 Video | 3 | health + workspace round-trip + ComfyUI INFO |
| S11 Personas | 39 | registration check + 37 persona prompts + summary |
| S12 Metrics | 5 | counter, workspaces_total, TPS histogram, Prometheus, Grafana |
| S13 GUI | 7 | login, workspace dropdown, persona listing, textarea, admin, tools |
| S14 HOWTO | 15 | all documented claims cross-referenced against live system |
| S15 Search | 2 | SearXNG JSON + research workspace |
| S16 CLI | 2 | status + list-users |
| S17 Rebuild | 3 | containers running + Dockerfile hash + MCP health |
| **Total** | **147** | |

Expected outcome on a healthy system with all models pulled:
- **~129 PASS**, **~9 WARN** (cold loads, headless GUI limit, unpulled models), **~9 INFO** (version strings, optional services), **0 FAIL**

Acceptable outcome: PASS + WARN ≥ 90% of total, FAIL = 0, BLOCKED with documented evidence for any genuine product issues.

---
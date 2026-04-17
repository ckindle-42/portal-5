# PORTAL5_ACCEPTANCE_EXECUTE_V6 — Claude Code Prompt

Clone `https://github.com/ckindle-42/portal-5/` and run the Portal 5 end-to-end
acceptance test suite v6. The live system is already running when you begin.

---

## Your Role

You are the **test execution agent**, not the implementation agent. You do not modify
protected product code. You execute the test suite, diagnose failures, repair the
test assertions when wrong, retry intelligently, and produce a final evidence-based
report. This is a **single-user lab** — test serially, never concurrently.

**No shortcuts. No prior-run bias.** Do not look at `ACCEPTANCE_RESULTS.md` from
a previous run and assume those results will repeat. Do not skip sections because
they WARNed before. Do not dismiss WARNs as "environmental" without investigating.
Every run is fresh. Every test gets the full treatment. **The code is correct — the
test adapts to it.**

---

## What V6 Tests

The v6 acceptance test framework validates **every documented feature** in Portal 5:

### Core Infrastructure (Sections S0-S2)
- Stack health (Docker, Ollama, MLX, Open WebUI, Pipeline)
- Service connectivity (all ports)
- Configuration consistency (backends.yaml ↔ router_pipe.py)

### Workspaces (Section S3)
All 17 workspaces with content-aware routing validation:
- `auto`, `auto-coding`, `auto-agentic`, `auto-spl`, `auto-security`
- `auto-redteam`, `auto-blueteam`, `auto-creative`, `auto-reasoning`
- `auto-documents`, `auto-video`, `auto-music`, `auto-research`
- `auto-vision`, `auto-data`, `auto-compliance`, `auto-mistral`

### Document Generation (Section S4)
- Word (.docx) generation via MCP
- Excel (.xlsx) generation with formulas
- PowerPoint (.pptx) generation with slides
- Content validation (not just file existence)

### Code Execution (Section S5)
- Sandbox health check (DinD)
- Python code execution
- Output capture and validation
- Timeout enforcement

### Security Workspaces (Section S6)
- BaronLLM routing for security/redteam
- Lily-Cybersecurity for blueteam
- Content-aware routing keywords

### Music Generation (Section S7)
- MusicGen health check
- Audio generation (WAV output)
- Duration and format validation

### Text-to-Speech (Section S8)
- MLX Speech server (Kokoro, Qwen3-TTS)
- Voice selection
- WAV output validation

### Speech-to-Text (Section S9)
- Qwen3-ASR transcription
- Round-trip TTS→ASR validation

### Personas (Sections S10-S11)
All 46 personas across 8 categories:
- Development (17): bugdiscoverycodeassistant, codereviewassistant, codereviewer,
  devopsautomator, devopsengineer, ethereumdeveloper, fullstacksoftwaredeveloper,
  githubexpert, javascriptconsole, kubernetesdockerrpglearningengine, 
  pythoncodegeneratorcleanoptimizedproduction-ready, pythoninterpreter, 
  seniorfrontenddeveloper, seniorsoftwareengineersoftwarearchitectrules, 
  softwarequalityassurancetester, ux-uideveloper, codebasewikidocumentationskill
- Security (6): cybersecurityspecialist, networkengineer, redteamoperator,
  blueteamdefender, pentester, splunksplgineer
- Data (7): dataanalyst, datascientist, machinelearningengineer, statistician,
  itarchitect, researchanalyst, excelsheet
- Compliance (2): nerccipcomplianceanalyst, cippolicywriter
- Systems (2): linuxterminal, sqlterminal
- General (2): itexpert, techreviewer
- Writing (2): creativewriter, techwriter
- Reasoning (6): magistralstrategist, gemmaresearchanalyst, phi4stemanalyst,
  phi4specialist, gptossanalyst, gemma4e4bvision

### Web Search (Section S12)
- SearXNG health
- Search query execution

### RAG/Embedding (Section S13)
- Embedding service health (TEI)
- Vector generation
- Reranker configuration

### MLX Acceleration (Section S20)
- Proxy health and model switching
- /v1/models endpoint
- Memory info endpoint

### LLM Intent Router (Section S21) — P5-FUT-006
- Router model availability (Llama-3.2-3B-abliterated)
- Content-aware routing for security, coding, compliance intents
- routing_descriptions.json and routing_examples.json validation
- JSON schema enforcement for routing decisions

### MLX Admission Control (Section S22) — P5-FUT-009
- Memory endpoint availability
- 503 rejection for oversized model requests
- Model memory estimates coverage
- Pre-flight memory checks before model load

### Model Diversity (Section S23)
- GPT-OSS:20B availability and reasoning test (OpenAI lineage)
- Gemma 4 E4B VLM (vision+audio multimodal)
- Phi-4 and Phi-4-reasoning-plus (Microsoft STEM reasoning)
- Magistral-Small (Mistral [THINK] mode)

### Image Generation (Section S30)
- ComfyUI connectivity
- FLUX schnell generation
- Output validation

### Video Generation (Section S31)
- Wan2.2 model availability
- Video generation via MCP

### Metrics & Monitoring (Section S40)
- Prometheus scrape targets
- Pipeline /metrics endpoint
- Grafana dashboard accessibility

---

## Step 1 — Clone and Orient

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5
```

Read these files before doing anything else:
- `PORTAL5_ACCEPTANCE_EXECUTE_V6.md` — this file, full methodology
- `CLAUDE.md` — architectural guidelines and constraints
- `docs/HOWTO.md` — feature documentation (what tests validate)
- `KNOWN_LIMITATIONS.md` — architectural constraints
- `ACCEPTANCE_RESULTS.md` — most recent prior run results (if present)

---

## Step 2 — Verify Stack State

```bash
./launch.sh status
grep -E "PIPELINE_API_KEY|OPENWEBUI_ADMIN_PASSWORD|GRAFANA_PASSWORD" .env
curl -s http://localhost:9099/health | python3 -m json.tool
```

Workspace count in `/health` must match the count in `portal_pipeline/router_pipe.py`:
```bash
python3 -c "
import re
src = open('portal_pipeline/router_pipe.py').read()
ids = set(re.findall(r'\"(auto[^\"]*)\": *\{', src))
print(f'WORKSPACES in router_pipe.py: {len(ids)}')
"
```

If they differ, the pipeline container is stale. Rebuild:
```bash
docker compose -f deploy/portal-5/docker-compose.yml up -d --build portal-pipeline
sleep 15
curl -s http://localhost:9099/health | python3 -m json.tool
```

Verify MCP services are running:
```bash
for port in 8910 8911 8912 8913 8914 8915 8916 8917 8918; do
  curl -s --max-time 3 http://localhost:$port/health && echo " :$port OK" || echo " :$port DOWN"
done
```

---

## Step 3 — Install Dependencies

```bash
pip install mcp httpx pyyaml playwright python-docx python-pptx openpyxl --break-system-packages
python3 -m playwright install chromium
```

Required for:
- `mcp` — MCP SDK for tool calls (same path as Open WebUI)
- `python-docx`, `python-pptx`, `openpyxl` — Document content validation
- `playwright` — GUI tests (optional, most tests use API)

---

## Step 4 — Run the Full Suite

```bash
python3 portal5_acceptance_v6.py 2>&1 | tee /tmp/portal5_acceptance_v6_run.log
echo "Exit: $?"
```

Expected runtime: **90-180 minutes** depending on model load states.

### CLI Options

```bash
# Single section
python3 portal5_acceptance_v6.py --section S3

# Multiple sections (comma-separated)
python3 portal5_acceptance_v6.py --section S3,S10,S11

# Section range
python3 portal5_acceptance_v6.py --section S3-S11

# Force rebuild before tests
python3 portal5_acceptance_v6.py --rebuild

# Verbose output (show evidence)
python3 portal5_acceptance_v6.py --verbose

# Skip sections that passed in prior run
python3 portal5_acceptance_v6.py --skip-passing
```

### Live Progress Monitoring

```bash
# In a separate terminal:
tail -f /tmp/portal5_progress.log
```

---

## Step 5 — Diagnose Every FAIL

Read `ACCEPTANCE_RESULTS.md`. For each FAIL status:

**Your first assumption is that the test is wrong, not the product.**

Work through this checklist for each FAIL:

### 1. Read the assertion
Find the test in `portal5_acceptance_v6.py`:
```bash
grep -n "tid=" portal5_acceptance_v6.py | grep "S3-05"
```

### 2. Reproduce manually
```bash
# For workspace/persona failures:
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto-WORKSPACE", "messages": [{"role": "user", "content": "PROMPT"}], "stream": false, "max_tokens": 400}'
```

### 3. Check logs
```bash
# Pipeline logs (routing decisions)
docker logs portal5-pipeline --tail 200 | grep -i "routing\|workspace="

# MCP logs
docker logs portal5-mcp-documents --tail 100

# Ollama logs (model loading)
curl -s http://localhost:11434/api/ps | python3 -m json.tool
```

### 4. Try variations
- Different prompt wording
- Higher timeout
- More/fewer max_tokens
- Different signal word expectations

### 5. Fix or classify
- If the test assertion was wrong: fix it, continue
- If the product behavior is correct but undocumented: accept as WARN
- If the product is broken and only a protected file change would fix it: **BLOCKED**

---

## Step 6 — MLX-Specific Guidance

**MLX works. The proxy, the server, and the routing are correct. If MLX tests fail,
the test is wrong — fix the test.**

### MLX Model Loading Signals

The MLX proxy loads models on-demand. Wait for these signals:

1. **Server log** — `/tmp/mlx-proxy-logs/mlx_lm.log` or `mlx_vlm.log`:
   - `"Starting httpd"` — mlx_lm server ready
   - `"Uvicorn running on"` — mlx_vlm server ready

2. **Health endpoint** — `http://localhost:8081/health`:
   - `state: "ready"` + `loaded_model` set — ready
   - `state: "switching"` — model loading in progress
   - `state: "none"` — proxy up, no model loaded yet

3. **Process check**:
   ```bash
   pgrep -f mlx-proxy.py      # proxy process
   pgrep -f mlx_lm.server     # text model server
   pgrep -f mlx_vlm.server    # VLM server
   ```

### Direct MLX Test (bypass pipeline)

```bash
curl -s -X POST http://localhost:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "mlx-community/Qwen3-Coder-Next-4bit", "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 20}'
```

### MLX Admission Control

The proxy rejects models that won't fit in memory:
```bash
curl -s http://localhost:8081/health/memory | python3 -m json.tool
```

If `admission_rejected: true`, the model is too large for current memory state.
This is a known hardware constraint, not a bug — record as **INFO**, not FAIL.

---

## Step 7 — Handle WARNs Correctly

Every WARN is investigated. A WARN means the request was served but the response
did not fully match the assertion.

For each WARN:
1. Read the detail field — what was the actual response?
2. Check the relevant logs — what happened?
3. Test manually — does it reproduce?
4. If the assertion was too strict: fix it, retry
5. If the product behavior is correct but undocumented: note it, accept as WARN
6. If the product behavior is wrong and only a protected file change would fix it: **BLOCKED**

---

## Step 8 — Re-run After Fixes

```bash
python3 portal5_acceptance_v6.py 2>&1 | tee /tmp/portal5_acceptance_v6_run2.log
echo "Exit: $?"
```

For targeted re-runs:
```bash
python3 portal5_acceptance_v6.py --section S3 2>&1 | tee /tmp/p5_s3.log
python3 portal5_acceptance_v6.py --section S10,S11 2>&1 | tee /tmp/p5_personas.log
```

---

## Step 9 — Produce the Blocked Items Register

For any item that cannot pass without modifying a protected file:

```markdown
## BLOCKED-N: <test name>

**Test ID**: SXX-YY
**Section**: SXX
**What was called**:
  - Endpoint: POST http://localhost:9099/v1/chat/completions
  - Payload: { model: "auto-workspace", messages: [...], max_tokens: 400 }

**What was returned** (full, untruncated):
  HTTP 200
  { "choices": [{ "message": { "content": "", "reasoning": "..." } }] }

**Retry attempts**:
  1. Increased max_tokens to 800 → same result
  2. Changed prompt wording → same result
  3. Tested model directly via Ollama API → model works fine

**Why the test assertion is correct**:
  HOWTO §X states: "auto-workspace returns [expected behavior]"
  
**Protected file requiring change**:
  portal_pipeline/router_pipe.py — line ~NNN
  Change: [specific fix needed]
```

---

## Step 10 — Final Deliverables

Produce these files in the repo root:

1. **`ACCEPTANCE_RESULTS.md`** — auto-written by the suite:
   - Run timestamp and git SHA
   - Summary counts (PASS/FAIL/BLOCKED/WARN/INFO)
   - Full results table
   - Blocked items register

2. **`portal5_acceptance_v6.py`** — final test file with assertion fixes

3. **`ACCEPTANCE_EVIDENCE.md`** — evidence report for investigated tests

4. **Update this file** with the "most recent run" section

---

## Constraints (Non-Negotiable)

### NEVER modify these files:
- `portal_pipeline/**` — router, cluster backends, notifications
- `portal_mcp/**` — all MCP server implementations
- `config/personas/**` — all persona YAML files
- `config/backends.yaml`
- `deploy/portal-5/docker-compose.yml`
- `Dockerfile.mcp` / `Dockerfile.pipeline`
- `scripts/openwebui_init.py`
- `docs/HOWTO.md`
- `imports/openwebui/**`

### NEVER run:
- `docker compose down -v` — destroys pulled Ollama models
- `docker compose down` — tears down the stack unnecessarily

### DO NOT:
- Modify test assertions to make a broken feature appear green
- Run concurrent test requests (single-user M4 Mac, 64GB unified memory)
- Classify tests as BLOCKED without 3+ genuine retry attempts

---

## Most Recent Run

**Date:** 2026-04-17  
**Git SHA:** b62806b  
**Result:** PASS — 155 PASS / 1 INFO / 0 FAIL / 0 BLOCKED / 0 WARN  
**Runtime:** 51m 28s (full suite, all 22 sections)

---

## Quick Reference: Common Issues

### 1. MLX proxy returns 503
**Cause:** Model still loading (30-300s depending on size)
**Fix:** Wait for `state: "ready"` in `/health`, or check server log for startup signal

### 2. Pipeline returns empty content
**Cause:** Model returned `reasoning` field instead of `content` (thinking models)
**Fix:** Test should check both `message.content` and `message.reasoning`

### 3. Persona not found in Open WebUI
**Cause:** New persona YAML not seeded
**Fix:** Run `./launch.sh reseed` or `./launch.sh up`

### 4. MCP tool timeout
**Cause:** Model inference slow, or ComfyUI/MusicGen cold start
**Fix:** Increase timeout, or pre-warm models before test

### 5. Embedding service unreachable
**Cause:** TEI container is x86-only, no ARM64 manifest
**Fix:** On Apple Silicon, use `./launch.sh start-embedding-cpu-arm` or accept as known limitation

### 6. Document file not found
**Cause:** AI_OUTPUT_DIR env var mismatch between MCP container and test
**Fix:** Verify `AI_OUTPUT_DIR` in .env matches bind mount path

---

## Section Quick Reference

| Section | Description | Expected Tests |
|---------|-------------|----------------|
| S0 | Prerequisites | 5 |
| S1 | Config consistency | 7 |
| S2 | Service health | 16 |
| S3 | Workspace routing | 17 |
| S4 | Document generation | 4 |
| S5 | Code sandbox | 3 |
| S6 | Security workspaces | 4 |
| S7 | Music generation | 2 |
| S8 | Text-to-Speech | 2 |
| S9 | Speech-to-Text | 2 |
| S10 | Personas (Ollama) | 7+ |
| S11 | Personas (MLX) | 4+ |
| S12 | Web search | 1 |
| S13 | RAG/Embedding | 2 |
| S20 | MLX acceleration | 3 |
| S21 | LLM Intent Router (P5-FUT-006) | 7 |
| S22 | MLX Admission Control (P5-FUT-009) | 4 |
| S23 | Model Diversity | 6 |
| S30 | Image generation | 2 |
| S31 | Video generation | 1 |
| S40 | Metrics/Monitoring | 3 |

**Total expected:** ~100+ core tests (persona tests scale with persona count)

---

*Last updated: 2026-04-10*

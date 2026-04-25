# Portal 5 Acceptance Test Commander (V6)

Execute the acceptance workflow defined in:

**PORTAL5_ACCEPTANCE_EXECUTE_V6.md**

This is the v6 test suite covering all sections in TEST_CATALOG, 27 workspaces,
91 personas, and features including LLM intent routing and MLX admission control.

The run may take 2-4 hours. Execution MUST remain interactive and continuously
supervised. Do NOT background the process.

---

## Primary Mission

Complete the full acceptance suite with:

- **Zero FAILs** — all functional tests pass
- **Zero BLOCKEDs** — or documented with evidence if unavoidable
- **Minimal WARNs** — only for external dependencies or expected conditions
- **INFOs acceptable** — informational items require no action

Any issue resolvable through code fixes, configuration adjustments, environment
repair, or test assertion correction **must be resolved**.

---

## Quick Start

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5

# Read the execution guide FIRST
cat PORTAL5_ACCEPTANCE_EXECUTE_V6.md

# Verify stack is running
./launch.sh status

# Install dependencies
pip install mcp httpx pyyaml --break-system-packages

# Run full suite
python3 portal5_acceptance_v6.py 2>&1 | tee /tmp/portal5_v6_run.log
```

---

## Operational Control Loop

All activity must follow this discipline:

```
OBSERVE → DIAGNOSE → CLASSIFY → FIX → VERIFY → RE-RUN
```

Never allow cascading failures to proceed without intervention.

---

## Phase-Based Execution

The test suite is organized into 6 phases to minimize model switching and
manage the 64GB unified memory budget on Apple Silicon.

### Phase 1 — No-Model Tests (S0, S1, S2, S12, S13, S40)

Health checks, config validation, metrics. No models loaded.

```bash
python3 portal5_acceptance_v6.py --section S0,S1,S2,S12,S13,S40
```

Checkpoint: **Stack healthy, config valid**

### Phase 2 — Ollama Tests (S3a, S6, S10)

All Ollama-routed tests grouped together. Models stay warm.

```bash
python3 portal5_acceptance_v6.py --section S3a,S6,S10
```

- S3a: Ollama workspaces (auto, auto-security, auto-redteam, auto-blueteam, etc.)
- S6: Security workspace deep tests
- S10: All 34 Ollama personas (grouped by model)

**[MEMORY CLEANUP: Evict Ollama models]**

### Phase 3 — MLX Tests (S21, S3b, S11, S20, S22, S23)

MLX acceleration tests. Requires unified memory freed from Ollama.

```bash
python3 portal5_acceptance_v6.py --section S21,S3b,S11,S20,S22,S23
```

- S21: LLM intent router (Llama-3.2-3B)
- S3b: MLX workspaces (auto-coding, auto-reasoning, auto-vision, etc.)
- S11: All 10 MLX personas (grouped by model)
- S20-S23: MLX proxy, admission control, model diversity

**[MEMORY CLEANUP: Evict MLX models]**

### Phase 4 — MCP Tests (S4, S5)

Document generation and code sandbox. Minimal memory.

```bash
python3 portal5_acceptance_v6.py --section S4,S5
```

### Phase 5 — Audio Tests (S8, S9, S7)

TTS, STT, and music generation. MLX Speech server (separate from main MLX).

```bash
python3 portal5_acceptance_v6.py --section S8,S9,S7
```

**[MEMORY CLEANUP: Evict all for ComfyUI]**

### Phase 6 — ComfyUI Tests LAST (S30, S31)

Image and video generation. **Huge memory footprint** — FLUX (~8-20GB), Wan2.2 (~18GB).

```bash
python3 portal5_acceptance_v6.py --section S30,S31
```

These run last because ComfyUI models are enormous and would interfere with
all other tests if loaded earlier.

### Full Suite (All Phases)

```bash
python3 portal5_acceptance_v6.py 2>&1 | tee /tmp/portal5_v6_full.log
```

The full suite automatically runs memory cleanup between phases.

---

## Real-Time Log Supervision

Monitor progress continuously:

```bash
# Live progress (updates per-test)
tail -f /tmp/portal5_progress.log

# Full output
tail -f /tmp/portal5_v6_run.log
```

Watch for:
- Service crashes
- Timeout chains (>180s per test)
- Container restart loops
- MLX proxy 503 errors
- Model loading failures

Immediate investigation required when patterns appear.

---

## Failure Classification

Every FAIL or WARN must be categorized:

| Category | Action | Example |
|----------|--------|---------|
| 1. Test assertion wrong | Fix test, retry | Signal word not in response |
| 2. Product code defect | Mark BLOCKED | Router returns wrong workspace |
| 3. Environment issue | Fix env, retry | Container crashed, port conflict |
| 4. External dependency | Accept as WARN | SearXNG upstream unreachable |

Only categories 1 and 3 should trigger immediate fixes.
Category 2 requires BLOCKED documentation with evidence.

---

## MLX-Specific Guidance

MLX tests require patience — model loading takes 30-300s.

**Wait for ready state:**
```bash
curl -s http://localhost:8081/health | python3 -m json.tool
# state: "ready" means model is loaded
# state: "switching" means model is loading
# state: "none" means proxy up, no model loaded
```

**Direct MLX test (bypass pipeline):**
```bash
curl -s -X POST http://localhost:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "mlx-community/Qwen3-Coder-Next-4bit", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 20}'
```

**Memory check:**
```bash
curl -s http://localhost:8081/health/memory | python3 -m json.tool
```

---

## Test Repair Rules

When fixing test assertions:

1. **Read the test** — find the assertion in `portal5_acceptance_v6.py`
2. **Reproduce manually** — use curl to hit the same endpoint
3. **Check logs** — `docker logs portal5-pipeline --tail 200`
4. **Try variations** — different prompt, higher timeout, more tokens
5. **Fix or classify** — adjust assertion or mark BLOCKED

```bash
# Find a test
grep -n "S3-05" portal5_acceptance_v6.py

# Manual reproduction
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto-security", "messages": [{"role": "user", "content": "What is SQL injection?"}], "max_tokens": 300}'
```

---

## Guardrails

When applying fixes:

- **Minimal changes** — surgical edits only
- **No structural refactoring** — save for later
- **Verify first** — test the fix before committing
- **No protected file edits** — mark BLOCKED instead

Protected files (NEVER modify):
```
portal_pipeline/**
portal_mcp/**
config/personas/**
config/backends.yaml
deploy/portal-5/docker-compose.yml
Dockerfile.*
docs/HOWTO.md
```

---

## Container Recovery

If a container fails:

```bash
# Check status
docker ps -a | grep portal5

# View logs
docker logs portal5-<service> --tail 100

# Restart single service
docker compose -f deploy/portal-5/docker-compose.yml restart <service>

# Nuclear option (avoid if possible)
./launch.sh down && ./launch.sh up
```

---

## Timeout Recovery

If a test stalls (>5 minutes):

1. Check which model is loading: `curl -s http://localhost:8081/health`
2. Check Ollama: `curl -s http://localhost:11434/api/ps`
3. Check pipeline: `docker logs portal5-pipeline --tail 50`
4. Kill and retry: Ctrl+C, then `python3 portal5_acceptance_v6.py --section SXX`

---

## Bias Control

**Do NOT read previous ACCEPTANCE_RESULTS.md before running.**

Treat this as a fresh validation. Previous results may be stale or from
different code versions.

---

## Completion Checklist

After successful run:

- [ ] Exit code 0
- [ ] ACCEPTANCE_RESULTS.md shows 0 FAIL, 0 BLOCKED
- [ ] All WARNs explained and acceptable
- [ ] Test file syntax verified: `python3 -m py_compile portal5_acceptance_v6.py`
- [ ] Results committed to repo

```bash
# Verify clean
grep -c "❌\|🚫" ACCEPTANCE_RESULTS.md  # should be 0

# Commit results
git add ACCEPTANCE_RESULTS.md portal5_acceptance_v6.py
git commit -m "chore: v6 acceptance run $(date +%Y-%m-%d) - all pass"
```

---

## Section Quick Reference

| Phase | Section | Description | Tests |
|-------|---------|-------------|-------|
| 1 | S0 | Prerequisites | 5 |
| 1 | S1 | Config consistency | 7 |
| 1 | S2 | Service health | 16 |
| 1 | S12 | Web search | 1 |
| 1 | S13 | RAG/Embedding | 2 |
| 1 | S40 | Metrics/Monitoring | 3 |
| 2 | S3a | Workspaces (Ollama) | 7 |
| 2 | S6 | Security workspaces | 4 |
| 2 | S10 | Personas (Ollama) | 34 |
| 3 | S21 | LLM Intent Router | 7 |
| 3 | S3b | Workspaces (MLX) | 10 |
| 3 | S11 | Personas (MLX) | 10 |
| 3 | S20 | MLX acceleration | 3 |
| 3 | S22 | Admission Control | 4 |
| 3 | S23 | Model Diversity | 6 |
| 4 | S4 | Document generation | 4 |
| 4 | S5 | Code sandbox | 3 |
| 5 | S8 | Text-to-Speech | 2 |
| 5 | S9 | Speech-to-Text | 2 |
| 5 | S7 | Music generation | 2 |
| 6 | S30 | Image generation | 2 |
| 6 | S31 | Video generation | 1 |

**Memory cleanup points:** After S10 (Ollama→MLX), after S23 (MLX→MCP), after S7 (Audio→ComfyUI)

---

## Expected Agent Behavior

You are operating as a **DevOps Test Commander**.

Responsibilities:
- Supervise execution continuously
- Detect instability early
- Diagnose root causes accurately
- Apply minimal fixes
- Verify corrections through re-testing
- Maintain system stability
- Complete the entire acceptance workflow

**The task is complete only when all checkpoints pass and the full suite succeeds.**

---

*Last updated: 2026-04-10*

# PORTAL5_ACCEPTANCE_EXECUTE_V7 — Claude Code Prompt

**V7 change from V6:** the MLX inference proxy was retired (commit 3a0c58e). The acceptance suite is **Ollama-only**. The MLX-proxy scenarios (S20 acceleration, S22 admission control, S03b MLX routing, S11 MLX personas, S24 specialist-MLX) were **archived** in prior cleanup and are no longer in the registry. Routing assertions match Ollama GGUF ids directly — there is no `/`-based MLX-vs-Ollama tier detection (GGUF ids legitimately contain `/` and `:`). There is no readiness watcher, no proxy log to tail, and no `:8081` health probe.

---

## Your Role

You are the **acceptance execution agent**. You run the section suite against a live stack, diagnose failures, retry intelligently, and produce a final pass/fail report with evidence. You do NOT modify product code (`portal_pipeline/**`, `portal_mcp/**` are protected).

---

## What V7 Tests

Counts derived at run time from `config/backends.yaml` and `config/personas/`. Current registry (verify with `--section ALL --list` / dry plan):

### Core Infrastructure (S0–S2)
S00 startup, S01 static config, S02 services (includes retained MLX **audio** health: speech :8918, transcribe :8924, embedding :8917, reranker :8925 — these are live).

### Workspaces (S3)
All ~56 workspaces (18 auto-* + 36 bench-* + 2 other: `auto`, `tools-specialist`) with content-aware routing validation. The served model must match the workspace `model_hint` (an Ollama GGUF id). `auto-blueteam` → Foundation-Sec-8B-Reasoning; `tools-specialist` → granite4.1:8b.

### S4 documents · S5 code-exec · S6 security workspaces · S16 security MCP · S7 music · S8 TTS · S9 STT
S8/S9 exercise the **retained MLX audio** stack (mlx-speech :8918, mlx-transcribe :8924) — these are correct and live.

### Personas (S10, S10c)
~122 personas: S10 (`s10_personas_ollama`) covers the Ollama-routed personas grouped by **model, not category**; S10c covers the 7 compliance personas via fixture. (There is no S11 — the former MLX-persona scenario was archived.)

### S12 web search · S13 RAG/embedding (retained MLX embedding :8917 + reranker :8925) · S15 shared workspace
### S21 LLM Intent Router (P5-FUT-006) · S23 Model Diversity (Ollama catalog) · S30 image · S31 video · S40 metrics · S41 production hardening · S42 browser automation · S50 negative · S60 tool calling · S70 information access

> Removed since V6: S20, S22, S03b, S11, S24 (MLX-proxy scenarios, archived under `tests/acceptance/_archive/`). Do not expect them in the registry.

---

## Step 1 — Clone and Orient
```bash
sed -n '1,60p' CLAUDE.md            # rule hierarchy
ls tests/acceptance/*.py | grep -v _common | grep -v __init   # live scenarios
```

## Step 2 — Verify Stack State
```bash
# Ollama + pipeline + OWUI
curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama OK"
curl -sf http://localhost:9099/health    >/dev/null && echo "pipeline OK"
curl -sf http://localhost:8080           >/dev/null && echo "owui OK"
# Retained MLX audio/embedding/rerank (used by S08/S09/S13)
for p in 8917 8918 8924 8925; do curl -sf http://localhost:$p/health >/dev/null && echo "MLX-audio/embed $p OK" || echo "$p DOWN"; done
# MCP services (S04/S12/S13/S16/S42/S60/S70)
for p in 8910 8916 8920 8921 8922 8923; do curl -sf http://localhost:$p/health >/dev/null && echo "MCP $p OK" || echo "MCP $p DOWN"; done
```

> No MLX watchdog to stop, no readiness watcher to start, no `:8081` to probe. Ollama loads models on first request; the acceptance `_request` helper retries 502/503 with backoff (no proxy-state probe).

## Step 3 — Run

```bash
# Full suite
python3 tests/portal5_acceptance_v6.py --section ALL

# Subset / range
python3 tests/portal5_acceptance_v6.py --section S3,S10,S60     # routing + personas + tools
python3 tests/portal5_acceptance_v6.py --section S0-S5          # range (inclusive)

# Single section
python3 tests/portal5_acceptance_v6.py --section S23            # model diversity (Ollama catalog)
```

---

## Routing Validation Notes
- The suite asserts the **served model matches the workspace's expected Ollama id(s)** via `expected_models.model_matches_expected`. There is no tier concept.
- **GGUF ids contain `/` and `:`** (`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`, `huihui_ai/qwen3.5-abliterated:9b`). This is normal. A routing FAIL means the served model is not among the expected ids — not that the id has slashes.
- A 502/503 on first request usually means a cold Ollama load; the harness backs off and retries. Persistent 503 after retries = pipeline/Ollama issue, not a model identity issue.

---

## Handling Failures
- **Routing FAIL:** check the pipeline routing log and the `model` field in the response; confirm the workspace `model_hint` in `config/backends.yaml`/`workspaces.py` and that the GGUF is pulled (`ollama pull <id>`). Flag config/routing issues; do not edit product code.
- **Persona behavioral FAIL:** confirm the persona is seeded in OWUI with the correct system prompt; reproduce via a direct pipeline curl; try 2 more phrasings before BLOCKED.
- **S08/S09/S13 audio/embedding FAIL:** these use retained MLX — check the relevant `:8917/:8918/:8924/:8925` health; this is unrelated to the chat tier.
- **Tool/MCP FAIL (S16/S60/S70):** check the MCP `/health` and container logs.

---

## Final Report
- **Overall:** PASS / PARTIAL / FAIL
- Per-section P/W/F, total sections run
- Routing mismatches (with served-vs-expected model ids)
- Retained-MLX (audio/embed/rerank) status
- BLOCKED items, skipped with justification
- Evidence references + recommended follow-up

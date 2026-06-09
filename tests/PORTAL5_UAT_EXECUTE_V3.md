# PORTAL5_UAT_EXECUTE_V3 — Claude Code Execution Prompt

**V3 change from V2:** the MLX inference proxy was retired (commit 3a0c58e); the UAT driver and inter-phase gate are now **Ollama-only**. The tier taxonomy collapsed from `mlx_large → mlx_small → ollama → any → media_heavy` to **`ollama → any → media_heavy`**. There is no MLX proxy, no readiness watcher (`mlx-readiness.py` is gone), no proxy restart, and no `/health/wired` polling. Memory is reclaimed by evicting Ollama models (`/api/ps` + `keep_alive:0`) and read from `vm_stat`. Retained MLX **audio** (mlx-speech :8918) is a memory-pressure source only, never killed.

The phased structure is preserved: **phased execution, one section group per invocation, with `--append` and a resume tracker.** Phasing still gives a clean checkpoint between memory transitions, easy failure bisection, and resumable runs. What changed is *why* the phases are ordered as they are (below).

---

## Execution Standard

**Sequential only.** Single-user M4 Pro Mac lab. Never send concurrent inference requests. The driver enforces this via cascade ordering — tests within any invocation run by `(workspace_tier, model_slug, test_id)`, with full Ollama eviction at tier/model transitions. Two models are never resident at once.

**Phased.** You do NOT run everything in one shot. You run section groups in load-grouped order, one invocation per group, with `--append`. Between phases the inter-phase gate checks Ollama health + unified-memory pressure and the FAIL delta before continuing. Read the Phase Plan below.

**Phasing rationale (Ollama).** The single GPU means each distinct model loads once per phase. Group large GGUFs (30–70B: Llama-3.3-70B, Olmo-3-32B, Qwen3.6-35B-A3B) early while memory is freshest to catch OOM early; group the bulk of mid-size (8–18B) workspaces together so the cascade sort consolidates by `model_slug` and avoids redundant reloads at section boundaries; run media-heavy (ComfyUI image/video) last with its own GPU-reclaim handling.

---

## Your Role

You are the **UAT execution agent**. You run the driver phase by phase against a live stack, classify each result (PASS/WARN/FAIL/BLOCKED), diagnose failures using the taxonomy below, retry intelligently, and produce a final report. You do NOT modify product code (`portal_pipeline/**`, `portal_mcp/**` are protected).

---

## What the UAT Driver Tests

Per-test browser-driven validation through Open WebUI (:8080) → pipeline (:9099) → Ollama (:11434). Each test opens/clicks/reads a real OWUI conversation, asserts on the streamed response, and renames the conversation `[PASS]/[WARN]/[FAIL]`. Coverage spans the auto-* workspaces, persona workspaces, tool/MCP calls, document/media generation, and cross-session memory.

---

## Phase 0 — Pre-flight (run once, ~3 min)

```bash
# Read the architectural reference FIRST.
sed -n '1,60p' CLAUDE.md

# Driver present and parses
python3 -m py_compile tests/portal5_uat_driver.py && echo "driver OK"

# Docker Desktop — restart for a clean VM before any long run (avoids vz Internal
# Virtualization errors accumulating across sleep/wake).
# (do this manually, then:)
./launch.sh up && sleep 30

# Stack health — Ollama + pipeline + OWUI
curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama OK"
curl -sf http://localhost:9099/health >/dev/null && echo "pipeline OK"
curl -sf http://localhost:8080 >/dev/null && echo "owui OK"

# OWUI auth + chat API (the driver's critical path)
# (driver auto-loads PIPELINE_API_KEY from .env; confirm it is set)
grep -q PIPELINE_API_KEY .env && echo "api key present"

# Playwright Chromium
python3 -c "from playwright.sync_api import sync_playwright; print('playwright OK')"

# MCP services for tool tests (T-01..T-12) and memory test (A-08)
for p in 8910 8916 8920 8921 8922 8923; do
  curl -sf http://localhost:$p/health >/dev/null && echo "MCP $p OK" || echo "MCP $p DOWN"
done

# Inter-phase gate script present (Ollama-only; no readiness watcher needed)
test -f tests/inter_phase_gate.sh && echo "gate OK"
```

> There is no MLX watchdog to stop and no readiness watcher to start. The driver detects Ollama model-load completion directly via the streaming response (the first token IS the ready signal) and `/api/ps`.

### Initialize the run tracker
```bash
RUN_TS=$(date -u +%Y%m%dT%H%MZ)
cat > tests/UAT_RUN_LOG.md <<EOF
# UAT Run Log — $RUN_TS
| Phase | Status | Started | Completed | Tests | P/W/F (cum) | Notes |
|---|---|---|---|---|---|---|
EOF
```

---

## Phase Plan (execution order)

| # | Phase | Why here | Est |
|---|---|---|---|
| 1 | Smoke | Initializes results; quick end-to-end confidence | 5–10 min |
| 2 | Large-GGUF-heavy sections (compliance, agentic, vision, research, security, redteam) | Big models loaded while memory is freshest; catches OOM early | 75–110 min |
| 3 | Bulk coding (auto-coding alone) | 26 tests spanning model sizes; own checkpoint | 100–140 min |
| 4 | Mid-size sections (data, reasoning, creative, mistral, spl, math, auto) | Bulk of suite; cascade groups by model_slug | 50–70 min |
| 5 | Remaining + blueteam/docs | auto-blueteam = Foundation-Sec (Ollama); docs | 20–35 min |
| 6 | Media-heavy (music, video) | ComfyUI last; own GPU reclaim | 30–50 min |
| 7 | Advanced + manual + final verify | — | 20–40 min |

### How model loading works inside a phase
The driver's `sort_tests_cascade` sorts every selected test by `(workspace_tier, model_slug, test_id)` where tier ∈ `{ollama, any, media_heavy}`. Consequences:
- Every test using the same persona/model runs back-to-back with the model loaded **once**; no reload between consecutive same-model tests.
- Passing multiple sections together consolidates by `model_slug` across them, so batching sections that share models avoids redundant reloads at section boundaries.
- The section-batching in each phase is deliberate. Phase 4 batches data/reasoning/creative/mistral/spl/math/auto into one invocation precisely because their mid-size models share loads when consolidated.

### What you must NOT do
- Do NOT run everything in one invocation (defeats checkpointing).
- Do NOT send concurrent requests.
- Do NOT modify `portal_pipeline/**` or `portal_mcp/**`.

---

## Phases (commands)

> First phase initializes `UAT_RESULTS.md` — do NOT use `--append` on Phase 1. Every later phase uses `--append`.

```bash
# Phase 1 — Smoke (no --append)
python3 tests/portal5_uat_driver.py --section smoke
# Confirm in the headed browser at http://localhost:8080: conversations "UAT: WS-01 …"
# appear and get renamed [PASS]/[WARN]/[FAIL]; tests/UAT_RESULTS.md has rows + links.
# Log the phase row, then run the gate:

# → Inter-Phase Gate after EVERY phase (HARD GATE — exits 1 if unrecoverable)
#   Ollama-only: checks pipeline + Ollama health, evicts resident Ollama models,
#   waits for vm_stat pressure < 80%, checks FAIL delta.
bash tests/inter_phase_gate.sh 1 <phase1_test_count>

# Phase 2 — large-GGUF-heavy sections
python3 tests/portal5_uat_driver.py --append \
  --section auto-compliance --section auto-agentic --section auto-vision \
  --section auto-research --section auto-security --section auto-redteam
bash tests/inter_phase_gate.sh 2 <count>

# Phase 3 — bulk coding
python3 tests/portal5_uat_driver.py --append --section auto-coding
bash tests/inter_phase_gate.sh 3 26

# Phase 4 — mid-size sections (batched for model_slug consolidation)
python3 tests/portal5_uat_driver.py --append \
  --section auto-data --section auto-reasoning --section auto-creative \
  --section auto-mistral --section auto-spl --section auto-math --section auto --section auto-daily
bash tests/inter_phase_gate.sh 4 <count>

# Phase 5 — blueteam + docs (Foundation-Sec is an Ollama GGUF now)
python3 tests/portal5_uat_driver.py --append --section auto-blueteam --section auto-documents
bash tests/inter_phase_gate.sh 5 <count>

# Phase 6 — media-heavy (keep ComfyUI through the gate)
python3 tests/portal5_uat_driver.py --append --section auto-music --section auto-video
bash tests/inter_phase_gate.sh 6 <count> --keep-comfyui

# Phase 7 — advanced/manual/final verify (no gate after the last phase)
python3 tests/portal5_uat_driver.py --append --section advanced
```

---

## Resume Protocol — when a phase is interrupted

```bash
# 1. Confirm what completed
cat tests/UAT_RUN_LOG.md
# 2. Find the last row marked DONE; resume at the phase AFTER it.
# 3. If a phase row is PAUSED / has no Completed timestamp, it was interrupted mid-run:
#    a) Re-run the whole phase (--append tolerates duplicate rows; flag on review), or
#    b) Re-run only failing tests by ID:
#       python3 tests/portal5_uat_driver.py --append --test <ID1> --test <ID2>
# 4. Confirm clean state before resuming:
curl -s http://localhost:11434/api/ps | python3 -c "import sys,json; print('ollama loaded:', len(json.load(sys.stdin).get('models',[])))"
vm_stat | awk '/Pages free/{f=$3}/wired/{w=$4} END{print "free/wired pages:",f,w}'
#    If a model is still resident, evict it:
curl -s http://localhost:11434/api/ps | python3 -c "
import sys,json,httpx
for m in json.load(sys.stdin).get('models',[]):
    httpx.post('http://localhost:11434/api/generate', json={'model':m['name'],'keep_alive':0}, timeout=10)
    print('unloaded', m['name'])"
# 5. Run the next phase command (always --append).

# Resume after full reboot:
# (restart Docker Desktop for a clean VM, then ./launch.sh up && sleep 30, recheck Phase 0 health)
```

---

## Failure Investigation Protocol

### Step 1 — Read the conversation first (the browser is ground truth).
### Step 2 — Classify:
- **3a Empty response (resource):** check memory; if a model is resident from a prior tier, evict and wait for `vm_stat` to settle, then rerun the single test.
- **3b Keyword mismatch (assertion too strict):** propose a fixture/assertion fix; do not touch product code.
- **3c Behavioral (model didn't follow system prompt):** read the persona's system prompt + hard constraints; confirm it is seeded in OWUI with the correct prompt; reproduce via a direct pipeline curl; try 2 more distinct phrasings — all 3 must fail before marking BLOCKED.
- **3d Tool/MCP failure (no artifact):** check the relevant MCP `/health`, pipeline tool-call logs, MCP container logs, then rerun.
- **3e Routing failure (wrong model served):** check the pipeline routing log and the model named in the OWUI conversation header. **GGUF ids contain `/` and `:` — that is normal.** A real failure is a fall-back to an unintended model, not the presence of slashes.
- **3f Driver silent after start (no output 5+ min):** confirm Ollama is reachable; confirm the pipeline accepted the request; confirm the API key works manually.
- **3g High memory after interrupted load:** the inter-phase gate evicts Ollama and waits for `vm_stat` < 80%; if a single test wedged memory, evict manually (Resume step 4) and rerun.

### Memory State Commands (reference)
```bash
# Unified-memory snapshot
vm_stat
# Ollama currently-loaded models
curl -s http://localhost:11434/api/ps | python3 -m json.tool
# Graceful unload (evict all Ollama models)
curl -s http://localhost:11434/api/ps | python3 -c "
import sys,json,httpx
for m in json.load(sys.stdin).get('models',[]):
    httpx.post('http://localhost:11434/api/generate', json={'model':m['name'],'keep_alive':0}, timeout=10)"
```

---

## Constraints (Non-Negotiable)
- **NEVER modify** `portal_pipeline/**`, `portal_mcp/**`, `config/`, `deploy/`, `docs/HOWTO.md`.
- **NEVER** send concurrent inference requests.
- **DO NOT** run all sections in one invocation.
- Memory safety is handled by the inter-phase gate (Ollama eviction + `vm_stat`), not by the agent guessing.

---

## Final Report — <RUN_TS>
- **Overall:** PASS / PARTIAL / FAIL
- **Totals:** P/W/F, tests run, phases completed
- **Issues resolved**, **Persistent failures (FAIL after remediation)**, **BLOCKED items**, **Skipped with justification**
- **Evidence:** UAT_RESULTS.md rows + OWUI conversation links
- **Recommended follow-up**

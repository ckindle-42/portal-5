# PORTAL5_UAT_EXECUTE_V5 — Claude Code Execution Prompt

> **Note (TASK_UAT_MODULARIZE_V1):** the driver implementation now lives in the `tests/uat/` package; `tests/portal5_uat_driver.py` is the entry-point shim. All invocations in this document are unchanged.

**V5 changes from V4 (HEAD 7.4.0):** the CC-01 coding challenge shootout is restored to the catalog as section `challenge` (~175 tests / 24 sections) and to the full UAT as **Phase 8** — one identical creative coding task per installed bench model, plus BT-01/EX-01 domain challenges. It is a capability shootout, not a benchmark; the deliverable is the comparative matrix (`tests/scripts/cc_challenge_matrix.py`), no verdict, promotions operator-only. Heaviest phase (~30+ distinct model loads, several sub-10-TPS lanes at 1500s timeouts) and **skippable for routine UATs**; run for fleet-evaluation UATs or standalone via `--section challenge`. **V4 changes from V3 (HEAD 7.3.1):** the catalog grew to **~136 tests across
23 sections** (was ~110/20): new `auto-audio` section (WS-21/WS-22), and the
phase plan now includes the previously-omitted `auto-docs` (9 tests) and
`tools-specialist` (2 tests) sections. **There is no `smoke` section** — the
smoke phase is `--section auto` (4 tests, includes WS-01). V8 fleet
promotions changed which models are "large": the heavy lanes are now
auto-creative (Qwen3.6-35B-A3B HauhauCS ~20GB), auto-data
(deepseek-r1:32b-q8_0 ~35GB), auto-vision (qwen3-vl:32b), auto-agentic +
auto-spl (qwen3-coder-next 80B/3B-active MoE), auto-research
(tongyi-deepresearch), auto-mistral (Magistral Q8 ~25GB). The driver also
gained `--rerun` / `--rerun-failed` (preferred over duplicate-tolerant
re-appends) and a dated-archival flow: tests run in root chat history for
live visibility, then bulk-move to `UAT/{YYYY-MM-DD}` on completion.

Everything else from V3 stands: Ollama-only (tiers `ollama → any →
media_heavy`), no MLX proxy/watcher, memory reclaimed via `/api/ps` +
`keep_alive:0` and read from `vm_stat`; retained MLX audio (mlx-speech :8918)
is a memory-pressure source only, never killed.

---

## Execution Standard

**Sequential only.** Single-user M4 Pro Mac lab. Never send concurrent
inference requests. The driver enforces this via cascade ordering — tests
within any invocation run by `(workspace_tier, model_slug, test_id)`, with
full Ollama eviction at tier/model transitions. Two models are never resident
at once.

**Phased.** You do NOT run everything in one shot. You run section groups in
load-grouped order, one invocation per group, with `--append`. Between phases
the inter-phase gate checks Ollama health + unified-memory pressure and the
FAIL delta before continuing.

**Phasing rationale (V8 fleet).** Each distinct model loads once per phase.
Group the large GGUFs (Qwen3.6-35B-A3B, deepseek-r1:32b-q8, qwen3-vl:32b,
qwen3-coder-next, tongyi-deepresearch, Magistral Q8) early while memory is
freshest to catch OOM early; batch the mid/small lanes (8–15B + gemma4 QAT
MoEs) together so the cascade sort consolidates by `model_slug`; run
media-heavy (ComfyUI image/video) last with its own GPU-reclaim handling.

---

## Your Role

You are the **UAT execution agent**. You run the driver phase by phase
against a live stack, classify each result (PASS/WARN/FAIL/BLOCKED), diagnose
failures using the taxonomy below, retry intelligently, and produce a final
report. You do NOT modify product code (`portal_pipeline/**`,
`portal_mcp/**` are protected).

---

## Autonomous Monitoring Loop — Required Default Behavior

UAT runs span 8 phases and 3–8 hours total. **Immediately after launching each
phase, establish a `ScheduleWakeup` loop.** This is not optional — it is the
required execution pattern. Do not hand off to the user to re-invoke you.

### On launch of each phase
```python
# After starting the phase process, schedule the first wakeup:
ScheduleWakeup(
    delaySeconds=270,          # stay within 5-min cache TTL for warm re-entry
    reason="monitoring UAT phase N — check progress, handle failures",
    prompt="<self-contained context — see template below>"
)
```

### On each wakeup
1. **Check process:** `ps aux | grep portal5_uat | grep -v grep`
2. **Tail the log** (always launch with `python3 -u ... > /tmp/uat_phaseN.log 2>&1 &`):
   `tail -20 /tmp/uat_phaseN.log`
3. **Check UAT_RESULTS.md** for new FAIL rows: `grep FAIL tests/UAT_RESULTS.md | tail -10`
4. **If running cleanly:** re-schedule at 270s and return.
5. **If FAILs appeared:** investigate per the Failure Investigation Protocol.
   Apply fixes, mark the row, re-run the failed test with `--rerun-failed`.
6. **If process died unexpectedly:** check log tail; check memory (`vm_stat`);
   see Resume Protocol; restart the phase from where it stopped.
7. **If phase complete:** run the inter-phase gate, log the phase row, then
   launch the next phase and re-establish the loop.

### Inter-phase gate (run after every phase)
```bash
python3 tests/portal5_uat_driver.py --section inter_phase_gate
```
Gate exits 1 if unrecoverable (memory, service down). Fix before proceeding.

### Final completion steps (after Phase 7 / last phase)
```bash
# Archive UAT chats into dated folder (driver does this on clean exit;
# run manually if the driver was interrupted):
python3 tests/portal5_uat_driver.py --archive-only
# Commit results
git add tests/UAT_RESULTS.md && git commit -m "results(uat): <run date> — P/W/F summary"
```
Update memory file at
`~/.claude/projects/-Users-chris-projects-portal-5/memory/` with final counts
and any defects found.

### Wakeup prompt template
The wakeup prompt must be self-contained — it re-enters cold. Include:
- Current phase number and section name
- Process PID and log path
- Phase plan table row (which phases done, which remain)
- Last test number and result seen in the log
- Any fixes or model skips applied this session
- The inter-phase gate and next-phase launch command

---

## What the UAT Driver Tests

Per-test browser-driven validation through Open WebUI (:8080) → pipeline
(:9099) → Ollama (:11434). Each test opens/clicks/reads a real OWUI
conversation, asserts on the streamed response, and renames the conversation
`[PASS]/[WARN]/[FAIL]`. Coverage spans the auto-* workspaces, persona
workspaces, tool/MCP calls, document/media generation, and cross-session
memory. Chats run in root history during the run; on completion the driver
bulk-moves the run's chats into `UAT/{YYYY-MM-DD}`.

---

## Phase 0 — Pre-flight (run once, ~3 min)

```bash
# Read the architectural reference FIRST.
sed -n '1,60p' CLAUDE.md

# Driver present and parses
python3 -m py_compile tests/portal5_uat_driver.py && echo "driver OK"

# Docker Desktop — restart for a clean VM before any long run (avoids vz
# Internal Virtualization errors accumulating across sleep/wake).
# (do this manually, then:)
./launch.sh up && sleep 30

# Stack health — Ollama + pipeline + OWUI
curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama OK"
curl -sf http://localhost:9099/health >/dev/null && echo "pipeline OK"
curl -sf http://localhost:8080 >/dev/null && echo "owui OK"

# OWUI auth + chat API (the driver's critical path)
grep -q PIPELINE_API_KEY .env && echo "api key present"

# Playwright Chromium
python3 -c "from playwright.sync_api import sync_playwright; print('playwright OK')"

# MCP services for tool tests and memory test
for p in 8910 8916 8920 8921 8922 8923; do
  curl -sf http://localhost:$p/health >/dev/null && echo "MCP $p OK" || echo "MCP $p DOWN"
done

# Inter-phase gate script present
test -f tests/inter_phase_gate.sh && echo "gate OK"
```

> No MLX watchdog to stop, no readiness watcher to start. The driver detects
> Ollama model-load completion via the streaming response (the first token IS
> the ready signal) and `/api/ps`.

### Initialize the run tracker
```bash
RUN_TS=$(date -u +%Y%m%dT%H%MZ)
cat > tests/UAT_RUN_LOG.md <<EOF
# UAT Run Log — $RUN_TS
| Phase | Status | Started | Completed | Tests | P/W/F (cum) | Notes |
|---|---|---|---|---|---|---|---|
EOF
```

---

## Phase Plan (execution order, ~175 tests / 24 sections)

| # | Phase | Sections | Tests | Why here |
|---|---|---|---|---|
| 1 | Smoke | `auto` | 4 | Initializes results; quick end-to-end confidence (incl. WS-01) |
| 2 | Large-GGUF lanes | creative, data, vision, research, mistral, agentic, spl | 37 | Big models (20–35GB + huge MoEs) while memory is freshest; catches OOM early |
| 3 | Bulk coding | auto-coding | 30 | Largest single section; own checkpoint |
| 4 | Mid/small lanes | compliance, reasoning, math, security, redteam, daily, audio, tools-specialist | 36 | Bulk of suite; cascade consolidates by model_slug (granite 8b, R1-8B, phi4-mini, baronllm, gemma4 QATs) |
| 5 | Blueteam + docs | blueteam, auto-docs, auto-documents | 12 | Foundation-Sec Q8 + phi4:14b document lanes |
| 6 | Media-heavy | music, video | 5 | ComfyUI last; own GPU reclaim (`--keep-comfyui` on the gate) |
| 7 | Advanced + final verify | advanced | 12 | Multi-turn / advanced flows |
| 8 | Challenge shootout (optional) | challenge | ~39 | Capability shootout, heaviest phase — every bench-* model loads once; last so it never blocks the production-lane verdict |

### How model loading works inside a phase
The driver's `sort_tests_cascade` sorts every selected test by
`(workspace_tier, model_slug, test_id)` where tier ∈ `{ollama, any,
media_heavy}`. Same-model tests run back-to-back with the model loaded once;
batching sections that share models avoids redundant reloads at section
boundaries. The phase composition above is deliberate.

### What you must NOT do
- Do NOT run everything in one invocation (defeats checkpointing).
- Do NOT send concurrent requests.
- Do NOT modify `portal_pipeline/**` or `portal_mcp/**`.

---

## Phases (commands)

> Phase 1 initializes `UAT_RESULTS.md` — do NOT use `--append` on Phase 1.
> Every later phase uses `--append`.

```bash
# Phase 1 — Smoke (no --append). There is no "smoke" section; `auto` is the smoke set.
python3 tests/portal5_uat_driver.py --section auto
# Confirm in the headed browser at http://localhost:8080: conversations
# "UAT: WS-01 …" appear and get renamed [PASS]/[WARN]/[FAIL];
# tests/UAT_RESULTS.md has rows + links. Log the phase row, then gate:

# → Inter-Phase Gate after EVERY phase (HARD GATE — exits 1 if unrecoverable)
bash tests/inter_phase_gate.sh 1 4

# Phase 2 — large-GGUF lanes
python3 tests/portal5_uat_driver.py --append \
  --section auto-creative --section auto-data --section auto-vision \
  --section auto-research --section auto-mistral --section auto-agentic \
  --section auto-spl
bash tests/inter_phase_gate.sh 2 37

# Phase 3 — bulk coding
python3 tests/portal5_uat_driver.py --append --section auto-coding
bash tests/inter_phase_gate.sh 3 30

# Phase 4 — mid/small lanes (batched for model_slug consolidation)
python3 tests/portal5_uat_driver.py --append \
  --section auto-compliance --section auto-reasoning --section auto-math \
  --section auto-security --section auto-redteam --section auto-daily \
  --section auto-audio --section tools-specialist
bash tests/inter_phase_gate.sh 4 36

# Phase 5 — blueteam + document lanes
python3 tests/portal5_uat_driver.py --append \
  --section auto-blueteam --section auto-docs --section auto-documents
bash tests/inter_phase_gate.sh 5 12

# Phase 6 — media-heavy (keep ComfyUI through the gate)
python3 tests/portal5_uat_driver.py --append --section auto-music --section auto-video
bash tests/inter_phase_gate.sh 6 5 --keep-comfyui

# Phase 7 — advanced/final verify (no gate after the last phase)
python3 tests/portal5_uat_driver.py --append --section advanced

# Phase 8 — Challenge shootout (OPTIONAL — fleet-evaluation UATs; heaviest phase)
bash tests/inter_phase_gate.sh 7 12
python3 tests/portal5_uat_driver.py --append --section challenge
# Then emit the shootout matrix (the deliverable — no verdict):
python3 tests/scripts/cc_challenge_matrix.py
# Expect long wall time: sub-8-TPS lanes run with timeout 1500 /
# max_wait_no_progress 1800.
```

---

## Resume Protocol — when a phase is interrupted

```bash
# 1. Confirm what completed
cat tests/UAT_RUN_LOG.md
# 2. Find the last row marked DONE; resume at the phase AFTER it.
# 3. If a phase was interrupted mid-run, prefer surgical re-runs:
#    a) Re-run only failed/blocked tests (implies --rerun --append):
python3 tests/portal5_uat_driver.py --rerun-failed
#    b) Re-run specific tests, replacing their existing rows:
python3 tests/portal5_uat_driver.py --rerun --test <ID1> --test <ID2>
#    c) Re-run a whole section, replacing its rows:
python3 tests/portal5_uat_driver.py --rerun --section <section>
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
- **3a Empty response (resource):** check memory; if a model is resident from
  a prior phase, evict and wait for `vm_stat` to settle, then rerun the test.
- **3b Keyword mismatch (assertion too strict):** propose a fixture/assertion
  fix; do not touch product code.
- **3c Behavioral (model didn't follow system prompt):** read the persona's
  system prompt + hard constraints; confirm it is seeded in OWUI; reproduce
  via a direct pipeline curl; try 2 more distinct phrasings — all 3 must fail
  before marking BLOCKED.
- **3d Tool/MCP failure (no artifact):** check the relevant MCP `/health`,
  pipeline tool-call logs, MCP container logs, then rerun.
- **3e Routing failure (wrong model served):** check the pipeline routing log
  and the model named in the OWUI conversation header. **GGUF ids contain
  `/` and `:` — normal.** A real failure is fall-back to an unintended model.
- **3f Driver silent after start (no output 5+ min):** confirm Ollama is
  reachable; confirm the pipeline accepted the request; verify the API key
  manually. Note: the qwen3-coder-next MoE cold load is slow — give Phase 2
  first-token waits extra patience before declaring silence.
- **3g High memory after interrupted load:** the inter-phase gate evicts
  Ollama and waits for `vm_stat` < 80%; if a single test wedged memory, evict
  manually (Resume step 4) and rerun.

### Memory State Commands (reference)
```bash
vm_stat
curl -s http://localhost:11434/api/ps | python3 -m json.tool
curl -s http://localhost:11434/api/ps | python3 -c "
import sys,json,httpx
for m in json.load(sys.stdin).get('models',[]):
    httpx.post('http://localhost:11434/api/generate', json={'model':m['name'],'keep_alive':0}, timeout=10)"
```

---

## Constraints (Non-Negotiable)
- **NEVER modify** `portal_pipeline/**`, `portal_mcp/**`, `config/`,
  `deploy/`, `docs/HOWTO.md`.
- **NEVER** send concurrent inference requests.
- **DO NOT** run all sections in one invocation.
- Memory safety is handled by the inter-phase gate (Ollama eviction +
  `vm_stat`), not by the agent guessing.
- No TPS measurement or perf assertions — perf belongs to
  `PORTAL5_BENCH_EXECUTE_V3.md`.

---

## Final Report — <RUN_TS>
- **Overall:** PASS / PARTIAL / FAIL
- **Totals:** P/W/F, tests run, phases completed
- **Issues resolved**, **Persistent failures (FAIL after remediation)**,
  **BLOCKED items**, **Skipped with justification**
- **Evidence:** UAT_RESULTS.md rows + OWUI conversation links (archived under
  `UAT/{YYYY-MM-DD}`)
- **Recommended follow-up**

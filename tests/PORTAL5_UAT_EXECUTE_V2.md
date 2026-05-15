# PORTAL5_UAT_EXECUTE_V2 — Claude Code Execution Prompt

Clone `https://github.com/ckindle-42/portal-5/`. The live system is already running.
`tests/portal5_uat_driver.py` is implemented and the driver's CLI is stable.

This is V2 of the execute prompt. The change from V1: **phased execution by tier, one section group at a time, with appended results and a resume tracker** — not one big `--all` invocation. Phased execution gives you a clean checkpoint between every memory-pressure transition, makes failures easy to bisect, and means an interrupted run can resume without re-running passing tests.

---

## Execution Standard

This is a **complete, evidence-backed test run** — not a checklist pass. The standard:

1. **Follow this document exactly.** Execute every section in order unless the document explicitly allows otherwise. Do not omit tests because they are slow, repetitive, or difficult.
2. **Troubleshoot instead of giving up.** If a step fails, diagnose before moving on. Determine whether the issue is test setup, environment state, service availability, memory/resource exhaustion, or a code defect. Apply the fix and rerun.
3. **Do not kill or reset services unnecessarily.** Preserve logs before taking corrective action. Restart only the minimum necessary component.
4. **Handle memory/resource issues intelligently.** Wait for services to settle. Do not mark a test failed because the first attempt hit resource pressure. Stabilize, then retry.
5. **Rerun failed or inconclusive sections.** Any FAIL, partial, timeout, or inconclusive result must be rerun after troubleshooting. Do not require the user to ask.
6. **Maintain the execution log.** Record each phase, all FAILs with root-cause analysis, remediation steps, and rerun results. See Run Log Template and Final Report sections.
7. **Do not modify core application code.** Assume the test, environment, or configuration is wrong first. Only recommend code changes if evidence clearly shows a code defect, and document exactly what, why, and what validation confirms it.
8. **Produce a Final Report.** The run is not complete until `tests/UAT_RUN_LOG.md` contains a `## Final Report` section with overall status, issues encountered, and remaining blockers.

---

## Your Role

You are the **UAT execution agent**. You do not build or modify the driver. You run it phase by phase, monitor between phases, diagnose failures, and produce a clean run log.

**The model behavior is assumed correct.** If an assertion fails, your first assumption is that the keyword list is too strict or phrased differently than the model's output. Investigate before marking FAIL. Only mark FAIL after 3 prompt variants all produce genuinely wrong model behavior.

**Sequential only.** Single-user M4 Mac lab. Never send concurrent inference requests. The driver enforces this via cascade ordering — tests within any invocation run by tier (`mlx_large` → `mlx_small` → `ollama` → `any` → `media_heavy`) with full eviction at tier transitions. MLX and Ollama are never loaded simultaneously.

**Phased.** You do NOT run `--all` in one shot. You run section groups in tier-descending order, one invocation per group, with `--append`. Between phases you check memory and FAIL deltas before continuing. This is the most important V1→V2 change — read the Phase Plan below.

---

## What the UAT Driver Tests

110 tests that produce **real Open WebUI conversations visible in the browser** at `http://localhost:8080`. Each conversation is named, tagged, and reviewable. Artifacts (DOCX, XLSX, PPTX, WAV, MP4) appear as file attachments in the relevant chats.

The driver is NOT the acceptance suite. It validates user-observable behavioral contracts that keyword matching cannot catch: does the persona ask before diagnosing? Does the Excel Sheet compute values, not show formula text? Does the Code Review Assistant scope its review to the diff only?

---

## Phase 0 — Pre-flight (run once, ~3 min)

```bash
git clone https://github.com/ckindle-42/portal-5/ && cd portal-5

# Read the architectural reference. Do this BEFORE running anything.
cat CLAUDE.md
cat KNOWN_LIMITATIONS.md

# Driver present and parses
test -f tests/portal5_uat_driver.py && echo "Driver present" || echo "MISSING — abort"
python3 -m py_compile tests/portal5_uat_driver.py && echo "Syntax OK"
python3 tests/portal5_uat_driver.py --help

# Docker Desktop — restart for a clean VM before any long test run.
# Apple's Virtualization.framework accumulates instability across sleep/wake
# cycles. A fresh VM avoids "Internal Virtualization error" mid-run crashes.
osascript -e 'quit app "Docker"' 2>/dev/null
sleep 5
open -a Docker
echo "Waiting for Docker Desktop to come up..."
until docker info >/dev/null 2>&1; do sleep 5; done
echo "Docker Desktop ready"

# Stack health
./launch.sh status
curl -sf http://localhost:8080/health && echo " OWUI OK"
curl -sf http://localhost:9099/health | python3 -m json.tool
curl -sf http://localhost:8081/health | python3 -m json.tool   # MLX proxy

# Start MLX readiness watcher — REQUIRED before any inference phase.
# The UAT driver reads /tmp/portal5-mlx-readiness.json (written every 10s)
# instead of implementing its own timer loops. Without this, tests with
# mlx_model declared will fall back to direct proxy polling (slower and
# less stable). The watcher must be running before Phase 1 starts.
python3 scripts/mlx-readiness.py > /tmp/mlx-readiness.log 2>&1 &
echo $! > /tmp/mlx-readiness.pid
echo "MLX readiness watcher started (PID $(cat /tmp/mlx-readiness.pid))"
# Give it two poll cycles to write its first state file
sleep 22
python3 scripts/mlx-readiness.py --read && echo "Watcher state OK" || echo "WARNING: state file not yet written — watcher may be slow to start"

# OWUI auth + chat API (the driver's critical path)
python3 -c "
import httpx, uuid
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json().get('token','')
assert tok, 'AUTH FAILED — check OPENWEBUI_ADMIN_PASSWORD in .env'
r = httpx.post('http://localhost:8080/api/v1/chats/new',
    json={'chat': {'id': str(uuid.uuid4()), 'title': 'UAT-preflight', 'models': ['auto'],
                   'messages': [], 'history': {'messages': {}, 'currentId': None},
                   'tags': [], 'params': {}, 'timestamp': 0}},
    headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}, timeout=10)
assert r.status_code in (200, 201), f'Chat create failed: {r.status_code} {r.text[:200]}'
print('Auth + chat API OK')
"

# Playwright Chromium
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('http://localhost:8080', timeout=10000)
    print('Playwright OK — title:', pg.title())
    b.close()
"

# MCP services (required for tool tests T-01..T-12 and memory test A-08)
# :8920 = portal_memory MCP; required for A-08 cross-session pre-seed API call
for port in 8912 8913 8914 8916 8917 8918 8919 8920; do
  curl -s --max-time 3 http://localhost:$port/health > /dev/null && echo " :$port OK" || echo " :$port DOWN"
done

# Inter-phase gate script (required between every phase)
test -f tests/inter_phase_gate.sh && echo "Gate script present" || { echo "ABORT: tests/inter_phase_gate.sh MISSING"; exit 1; }
```

**Hard stop:** if anything above fails, fix the environment first. Do not run tests against a degraded stack.

### Initialize the run tracker

The tracker is the agent's memory between phases. Without it, an interrupted run cannot resume.

```bash
RUN_TS=$(date -u +%Y%m%dT%H%MZ)
echo "$RUN_TS" > /tmp/uat_run_id

cat > tests/UAT_RUN_LOG.md <<EOF
# UAT Run Log — $RUN_TS

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
EOF
```

This file is the source of truth for "where am I in the run." Every phase appends one row when it completes (or marks itself BLOCKED so you can resume past it).

`tests/UAT_RESULTS.md` is the driver's output and accumulates across phases via `--append`. Do NOT delete it between phases; do NOT pass `--append` on the very first phase (smoke) so the file initializes cleanly.

---

## Phase Plan (this is the execution order)

| # | Phase | Why this phase exists | Approx time |
|---|---|---|---|
| 1 | Smoke (auto) | Confirm driver, OWUI, browser, results file all wire up. 4 tests, fast feedback before committing real time. | 5–10 min |
| 2 | mlx_large-heavy sections | Big models loaded while memory is freshest. Catches OOM early. | 75–110 min |
| 3 | mlx_small-heavy coding/reasoning | Bulk of the suite. Models in the 8–18 GB range. | 90–120 min |
| 4 | mlx_small-heavy daily/data/research/creative | Same tier, separated to give a checkpoint mid-suite. | 40–55 min |
| 5 | ollama + mlx_small sections | MLX evicted before this phase starts. | 15–25 min |
| 6 | media_heavy (music/video) | Always last among inference. ComfyUI/Wan2.2 footprint. | 30–60 min |
| 7 | benchmark | Long, model-capability-only, can run independently. | 60–90 min |
| 8 | advanced + manual + verify | Manual reviews, OWUI conversation count, result tally. | 15–30 min |

**Pacing rule:** between phases, run `bash tests/inter_phase_gate.sh <phase_num> <test_count>` (the Inter-Phase Gate, defined below). The gate BLOCKS until memory is safe, pipeline is healthy, and FAIL delta is acceptable. It recovers automatically: `/unload` → kill orphaned mlx servers → proxy restart. It kills ComfyUI if running and the next phase isn't media_heavy. Do NOT proceed to the next phase until the gate exits cleanly.

### How model loading works inside a phase (read this — it changes how you think about phases)

The driver's `sort_tests_cascade` (in `tests/portal5_uat_driver.py`) sorts every selected test by `(workspace_tier, model_slug, test_id)`. This means:

- **Within a single invocation, every test that uses the same persona runs back-to-back with the model loaded once.** No reload between consecutive tests on the same model_slug. Across personas within a tier, the driver still reloads once per model — that is unavoidable on a single-GPU box — but never more than once per model per phase.
- **When you pass multiple sections together (`--section A --section B --section C`), the cascade sort consolidates by model_slug ACROSS those sections.** If `auto-mistral` and `auto-spl` both have tests using mlx_small models, batching them in one invocation runs them grouped by their actual model, not interleaved with re-loads at the section boundary.
- **What this means for the agent:** the section-batching in each phase below is deliberate. Phase 4 batches six sections (auto-data, auto-reasoning, auto-creative, auto-mistral, auto-spl, auto-math, auto) into one invocation precisely because their mlx_small tests share model loads when consolidated. Splitting that into six separate invocations would cause six redundant model load cycles for the same tier — that's the failure mode this design avoids.

### What you must NOT do

- **Do NOT split a phase into per-section invocations** to "watch each section finish." The driver already tells you which test it's running and writes results live; you can `tail -f tests/UAT_RESULTS.md` to monitor. Splitting forces extra model loads.
- **Do NOT use `--test <id>` during a phased run** to "skip ahead" to a specific test. Single-test invocations force a fresh model load just for that test, then the next phase starts cold and reloads again. `--test` is for diagnosis AFTER all phases complete or DURING a paused phase, never as a substitute for `--section`.
- **Do NOT add `--timeout` overrides per-section if tests within the section need different timeouts.** Per-test `timeout` values in the catalog already handle that. Use `--timeout` only at phase level when an entire phase's models need extra time (e.g. agentic 80B MoE).

If you find yourself wanting to break a phase into smaller pieces, that's a sign you don't trust the driver's ordering. Read `sort_tests_cascade` in the driver to confirm what it's doing, then run the phase as designed.

---

## Phase 1 — Smoke

```bash
# First phase initializes UAT_RESULTS.md, so do NOT use --append here.
python3 tests/portal5_uat_driver.py --section auto --headed 2>&1 | tee /tmp/uat_phase1.log
PHASE1_EXIT=$?

# Open http://localhost:8080 in the headed browser and confirm:
#  - Conversations titled "UAT: WS-01 …", "UAT: P-W06 …", "UAT: P-W03 …" appear
#  - Each is renamed [PASS]/[WARN]/[FAIL] after its test completes
#  - tests/UAT_RESULTS.md exists with rows + clickable links
test -s tests/UAT_RESULTS.md && echo "Results file populated" || { echo "ABORT: results file empty"; exit 1; }

# Log the phase
{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 1. smoke (auto) | DONE | $RUN_TS | $(date -u +%H:%MZ) | 4 | ${PASS}P/${WARN}W/${FAIL}F | exit=$PHASE1_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

If smoke produces zero conversations or a Python error, diagnose before any further phase (see Diagnosis section). Common cause: OWUI seeded models stale → `./launch.sh reseed && sleep 15`.

If smoke passed (results file has rows), run the gate before Phase 2:
```bash
bash tests/inter_phase_gate.sh 1 4
```

### → Inter-Phase Gate (now and after every phase — THIS IS A HARD GATE, NOT A SUGGESTION)

The gate is implemented in `tests/inter_phase_gate.sh`. **Do not recreate it inline.** Run it with the phase number and test count after every phase. It blocks until the system is safe to proceed, auto-recovers where possible, and exits 1 on unrecoverable failure.

What the gate checks, in order:

| Gate | Check | Failure action |
|---|---|---|
| 1 | Pipeline health `http://localhost:9099/health` | Exit 1 — unrecoverable, fix first |
| 2 | MLX proxy health `http://localhost:8081/health` | 3 retries × 30s backoff, then exit 1 |
| 2.5 | Non-MLX memory pressure (ComfyUI, Ollama) | ComfyUI: API→SIGTERM→SIGKILL; Ollama: direct `/api/delete`; skipped if `--keep-comfyui` |
| 3 | Wired < 12 GB AND inactive < 20 GB | Loops up to 10 min; 4-level recovery: `/unload` → zombie kill → proxy restart → watchdog wait; WARN on timeout |
| 4 | FAIL delta ≤ 30% of phase tests | WARN if exceeded — investigate before proceeding |

The gate appends rows to `tests/UAT_RUN_LOG.md` automatically.

**The gate is the agent's contract with the hardware.** Run it between every phase:

```bash
bash tests/inter_phase_gate.sh 1 4    # after Phase 1 (4 tests)
bash tests/inter_phase_gate.sh 2 24   # after Phase 2 (24 tests)
bash tests/inter_phase_gate.sh 3 26   # after Phase 3 (26 tests)
# ... and so on — see exact commands in each phase section below
```

**Gate enforcement rules** (the agent must NOT override these):
- Gate exit code 1 = **hard stop**. Do not run any further tests. Diagnose and fix, then re-run the gate.
- Gate `WARN` on memory timeout = acknowledge in run log note, then proceed. Expect potential empty responses.
- Gate `WARN` on FAIL delta = investigate the new FAILs before proceeding. If all are empty-response cascades from memory pressure that the gate already cleared, proceed. If behavioral, pause and diagnose.
- Gate `PASS` = proceed immediately to next phase. No additional wait needed.
- The gate appends its own log rows — the agent does not need to duplicate them.

**Why this gate exists:** prior execution runs ignored the pause criteria, running phases with `wired_gb > 40` and causing 22+ behavioral FAILs that were actually empty-response cascades from memory starvation. The prose pause criteria were read but not enforced. This gate programmatically enforces them.

---

## Phase 2 — mlx_large-heavy sections (compliance, agentic, vision, research, security, redteam)

These sections contain all pure-`mlx_large` tier tests. Run them while memory is freshest. `auto-security` and `auto-redteam` are included here because they are now pure `mlx_large` (AEON 27B) — running them in Phase 5 would load a large model after the bulk of the suite has already stressed memory.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-compliance \
  --section auto-agentic \
  --section auto-vision \
  --section auto-research \
  --section auto-security \
  --section auto-redteam \
  2>&1 | tee /tmp/uat_phase2.log
PHASE2_EXIT=$?

{
  TOTAL_NOW=$(grep -cE '\| (PASS|WARN|FAIL) \|' tests/UAT_RESULTS.md)
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 2. mlx_large heavy | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | $((TOTAL_NOW-4)) | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE2_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Run the **Inter-Phase Gate** before phase 3:
```bash
bash tests/inter_phase_gate.sh 2 24
```

### Why these six sections and not auto-data?

`auto-data` mixes mlx_large and mlx_small with significant `any`-tier admin work (knowledge base list/create). It runs more reliably in phase 3 alongside the small-tier coding work, where memory is already settled.

### What about `auto-coding` heavy tests (CC-01)?

The `auto-coding` section has 26 tests spanning every tier. It's too large to interleave here. It gets its own phase.

---

## Phase 3 — Bulk coding (auto-coding alone)

26 tests spanning mlx_large, mlx_small, and any tiers. The cascade sort handles tier order internally; within each tier, tests group by model_slug so each coding persona's model loads exactly once. Running auto-coding alone (rather than batching it with phase 4 sections) gives a clean checkpoint between the heavy coding work and the lighter data/reasoning work. Don't sub-split it — that defeats the model-grouping benefit.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-coding \
  2>&1 | tee /tmp/uat_phase3.log
PHASE3_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 3. auto-coding | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 26 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE3_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Run the **Inter-Phase Gate** before phase 4:
```bash
bash tests/inter_phase_gate.sh 3 26
```

---

## Phase 4 — Remaining mlx_small/any sections (data, reasoning, creative, mistral, spl, math)

**Why all six in one invocation:** these sections share the mlx_small tier and several share model_slugs. Batching them lets the cascade ordering consolidate by model — every test for a given persona runs back-to-back, then the driver loads the next persona's model exactly once. Running them as six separate invocations would reload some models multiple times.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-daily \
  --section auto-data \
  --section auto-reasoning \
  --section auto-creative \
  --section auto-mistral \
  --section auto-spl \
  --section auto-math \
  --section auto \
  2>&1 | tee /tmp/uat_phase4.log
PHASE4_EXIT=$?
# Note: auto was already run in smoke; phase 4 reruns it but --append keeps both rows.
# That's fine — auto is small and acts as a regression spot-check after phases 2-3.
# auto-daily (WS-DD-01..08) uses gemma-4-26b MLX — same tier as auto-coding's mlx_small
# tests; batching here lets cascade ordering group by model_slug across sections.

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 4. mlx_small bulk | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~33 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE4_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Gate:
```bash
bash tests/inter_phase_gate.sh 4 33
```

---

## Phase 5 — Ollama + mlx_small (blueteam, docs)

`auto-security` and `auto-redteam` moved to Phase 2 (they are now pure `mlx_large`/AEON). This phase is the remaining non-mlx_large sections: `auto-blueteam` (pure ollama) and `auto-docs` (mlx_small + ollama, 6/7 tests mlx_small). No large model loads here — wired memory stays low throughout.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-blueteam \
  --section auto-docs \
  2>&1 | tee /tmp/uat_phase5.log
PHASE5_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 5. ollama + mlx_small | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~9 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE5_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Gate (5→6: keep ComfyUI for media_heavy):
```bash
bash tests/inter_phase_gate.sh 5 9 --keep-comfyui
```

---

## Phase 6 — Media-heavy (music, video)

Skip with `--skip-artifacts` if ComfyUI/Wan2.2 aren't running locally.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-music \
  --section auto-video \
  2>&1 | tee /tmp/uat_phase6.log
PHASE6_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 6. media_heavy | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 5 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE6_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Gate (6→7: kill ComfyUI, benchmark doesn't need it):
```bash
bash tests/inter_phase_gate.sh 6 5
```

---

## Phase 7 — Benchmark (CC-01 across 13 models)

Long, model-by-model. The `bench-*` personas all share a system prompt by design — what's measured is raw model capability on a fixed task. Per-model fail rates are the bench's signal, not bugs.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section benchmark \
  --timeout 360 \
  2>&1 | tee /tmp/uat_phase7.log
PHASE7_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 7. benchmark | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 13 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE7_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Gate:
```bash
bash tests/inter_phase_gate.sh 7 13
```

---

## Phase 8 — Advanced + manual + final verify

`advanced` covers the dispatcher paths (Telegram/Slack), cross-session memory, routing validation. `--skip-bots` if Telegram/Slack containers aren't configured.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section advanced \
  --skip-bots \
  2>&1 | tee /tmp/uat_phase8.log
PHASE8_EXIT=$?

# Stop the MLX readiness watcher — no longer needed after final phase
if [ -f /tmp/mlx-readiness.pid ]; then
  kill "$(cat /tmp/mlx-readiness.pid)" 2>/dev/null && echo "MLX watcher stopped" || echo "MLX watcher already stopped"
  rm -f /tmp/mlx-readiness.pid /tmp/portal5-mlx-readiness.json
fi

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  TOTAL=$((PASS+WARN+FAIL))
  echo "| 8. advanced | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~6 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE8_EXIT |"
  echo ""
  echo "## Run summary — $RUN_TS"
  echo ""
  echo "- Total: $TOTAL  PASS: $PASS  WARN: $WARN  FAIL: $FAIL"
  echo "- Pass rate: $((PASS * 100 / TOTAL))%"
} >> tests/UAT_RUN_LOG.md
```

### Manual tests (A-05, A-06, A-07)

The driver creates `[MANUAL] UAT: …` chats with instructions in the chat body. Open OWUI:

1. Open `http://localhost:8080`
2. Find chats: `[MANUAL] UAT: A-05 (Telegram)`, `[MANUAL] UAT: A-06 (Slack)`, `[MANUAL] UAT: A-07 (Grafana)`
3. Follow the instructions in each
4. Append a reply: `✅ PASS`, `⚠️ PARTIAL`, or `❌ FAIL` with brief notes
5. Update `tests/UAT_RESULTS.md` for those three rows by hand (driver doesn't grade manual tests)

A-07 (Grafana) is always doable: open `http://localhost:3000` after running ≥10 inference tests and confirm `portal_tokens_per_second` shows recent data with workspace labels.

### Final verification — OWUI conversations exist

```bash
python3 -c "
import httpx
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json().get('token','')
chats = httpx.get('http://localhost:8080/api/v1/chats/',
    headers={'Authorization': f'Bearer {tok}'}).json()
uat = sorted(c['title'] for c in chats if 'UAT' in c.get('title',''))
print(f'{len(uat)} UAT conversations found')
for t in uat: print(' ', t)
" | head -20
```

Expected after a complete run with `--skip-bots` (excluding `--skip-artifacts`): **~108–110 conversations** (all 110 tests create OWUI chats; A-08 creates 2; A-05/A-06 are skipped). If `--skip-artifacts` is also set, subtract 5 (auto-music + auto-video). Fewer means at least one phase recorded results without OWUI chats — investigate `/tmp/uat_phase*.log` for the affected phase.

---

## Resume Protocol — when a phase is interrupted

The tracker file `tests/UAT_RUN_LOG.md` is the source of truth. It survives Ctrl+C, watchdog restarts, and even Mac reboots (it's committed to disk after each phase).

### To resume after an interruption:

```bash
# 1. Confirm what completed
cat tests/UAT_RUN_LOG.md

# 2. Find the last row marked DONE. The next phase to run is the one AFTER it.
#    Example: if the log shows phases 1-3 DONE and phase 4 has no row, resume at phase 4.

# 3. If a phase row exists with status PAUSED or no Completed timestamp, that phase
#    was interrupted mid-run. Decide:
#      a) Re-run the whole phase (safer, --append is idempotent in the sense that
#         duplicate rows are tolerated and a manual review can flag them)
#      b) Re-run only the failing tests by ID:
#         python3 tests/portal5_uat_driver.py --append --test <ID1> --test <ID2>

# 4. Confirm system state is clean before resuming:
#    - Check wired memory: should be < 12 GB if no model is loaded
curl -s http://localhost:8081/health/wired | python3 -m json.tool
#    - If wired_gb > 12 GB and state == "none", request unload
curl -X POST 'http://localhost:8081/unload?ollama=true' | python3 -m json.tool

# 5. Run the next phase command from the Phase Plan above (always with --append).
#    Append a new row to UAT_RUN_LOG.md when it completes.
```

### Resume after a full system reboot:

The same protocol applies. Restart Docker Desktop for a clean VM, then bring up the stack:

```bash
# Restart Docker Desktop (clean VM, avoids vz Internal Virtualization error)
osascript -e 'quit app "Docker"' 2>/dev/null
sleep 5
open -a Docker
until docker info >/dev/null 2>&1; do sleep 5; done

```bash
./launch.sh status
# If anything is down: ./launch.sh up && sleep 30
```

Then read `tests/UAT_RUN_LOG.md`, identify the last DONE row, and resume from the next phase.

**Restart the MLX readiness watcher** — it does not survive a reboot:
```bash
python3 scripts/mlx-readiness.py > /tmp/mlx-readiness.log 2>&1 &
echo $! > /tmp/mlx-readiness.pid && sleep 22
python3 scripts/mlx-readiness.py --read
```

### Re-running a whole phase after a fix:

```bash
python3 tests/portal5_uat_driver.py --rerun --section auto-coding
```

`--rerun` removes existing rows in `UAT_RESULTS.md` for the selected tests before running, then appends fresh results. Use it when re-running a section after a fix to avoid duplicate rows. It implies `--append` and requires `--section`, `--test`, or `--media` to scope which rows to replace. Do NOT use `--rerun --all` — it would wipe the entire results file.

### Re-running a single test (diagnosis only — do NOT use during phased run):

```bash
python3 tests/portal5_uat_driver.py --append --test WS-04
python3 tests/portal5_uat_driver.py --append --test P-D06 --headed
```

These append a single row to `UAT_RESULTS.md`. Use them ONLY for:
- Diagnosing a specific FAIL after all phases complete
- Re-running a small set of tests that need attention before declaring the run final
- Reproducing a behavioral failure with a different prompt during BLOCKED investigation

A single-test invocation forces the driver to load that test's model from cold, run one test, then stop. If you call `--test` mid-phase to "skip ahead," you waste a model load AND the next phase still starts cold. Always finish phases before you start cherry-picking tests.

---

## Calibration Mode (independent of phased run)

Used when assertion keyword lists need a refresh, NOT during a normal pass/fail run. Calibration captures full responses to JSON for human review, then `--emit-signals-from` proposes per-section TF-IDF keyword sets to feed into `tests/quality_signals.py` and the catalog.

```bash
python3 tests/portal5_uat_driver.py --calibrate --calibrate-output calibration.json
# (Edit calibration.json — set review_tag on each entry)
python3 tests/portal5_uat_driver.py --emit-signals-from calibration.json
```

Full workflow: `docs/UAT_CALIBRATION.md`. Use `--section <n>` to calibrate one section without running the full suite.

---

## Failure Investigation Protocol

**This is a complete troubleshooting workflow, not a reference table. Follow it in order for every FAIL before accepting the result.**

### Step 1 — Read the conversation first

Open `tests/UAT_RESULTS.md`. Click the OWUI conversation link for the failing test. **Read what the model actually said before touching any assertion or keyword.** A failing assertion does not mean the model behaved incorrectly — the keyword may be too strict.

Do NOT rerun the test before you have read the conversation.

### Step 2 — Classify the failure

| What you see in the OWUI conversation | Classification | Go to |
|---|---|---|
| Empty chat — no response at all | Resource failure | Step 3a |
| Response is correct, uses synonyms ("vulnerability" vs. "vuln") | Keyword mismatch | Step 3b |
| Response is correct but assertion expected different phrasing | Keyword mismatch | Step 3b |
| Response is present but wrong behavior (e.g. coded without asking framework) | Behavioral failure | Step 3c |
| No artifact file (DOCX, WAV, MP4, PNG) despite correct response | Tool/MCP failure | Step 3d |
| Security model refused entirely (not "I'll help but...") | Routing failure | Step 3e |

### Step 3a — Empty response (resource failure)

```bash
# Check memory state
curl -s http://localhost:8081/health/wired | python3 -m json.tool
curl -s http://localhost:8081/health | python3 -m json.tool
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# If wired_gb > 12 or a model is still loaded from a previous tier:
curl -X POST 'http://localhost:8081/unload?ollama=true' | python3 -m json.tool
# Wait for state=none and wired_gb to drop (2-5 min for large models)
sleep 120
curl -s http://localhost:8081/health/wired | python3 -m json.tool

# Rerun the single test:
python3 tests/portal5_uat_driver.py --append --test <TEST_ID>
```

If the rerun passes → resource issue, not a code defect. Log root cause as "empty response / memory pressure, cleared by unload." Continue.

If the rerun still produces an empty response, check for a zombie MLX process:
```bash
ps aux | grep mlx_lm
# If a process has been running >5 min and /health is dead, kill it:
kill -TERM <pid>
sleep 30
python3 tests/portal5_uat_driver.py --append --test <TEST_ID>
```

### Step 3b — Keyword mismatch (assertion too strict)

The model's behavior is correct but the keyword list doesn't match its phrasing. This is an assertion calibration issue, not a model defect.

Acceptable fixes (in order of preference):
1. Add synonyms to `any_of` keywords
2. Switch `contains` → `any_of` if only one of several acceptable phrasings is needed
3. Broaden the keyword (e.g. `"vuln"` catches `"vulnerability"`, `"vulnerable"`)

Do NOT weaken assertions to pass content that doesn't meet the behavioral contract. If the model genuinely failed the behavioral requirement (not just the keyword), go to Step 3c.

After editing the keyword list, rerun with `--rerun`:
```bash
python3 tests/portal5_uat_driver.py --rerun --test <TEST_ID>
```

### Step 3c — Behavioral failure (model didn't follow system prompt)

```bash
# 1. Read the persona's system prompt and hard constraints
grep -A 60 "system_prompt" config/personas/<slug>.yaml

# 2. Confirm the persona is seeded in OWUI with the correct system prompt
python3 -c "
import httpx
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json()['token']
models = httpx.get('http://localhost:8080/api/v1/models/', headers={'Authorization': f'Bearer {tok}'}).json()
names = [m.get('id','') for m in (models if isinstance(models,list) else models.get('data',[]))]
print([n for n in names if 'SLUG' in n])
" 

# 3. If not seeded or stale:
./launch.sh reseed && sleep 15

# 4. Reproduce manually via the pipeline with a direct curl call
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "<model_slug>", "messages": [{"role": "user", "content": "<original prompt>"}], "stream": false, "max_tokens": 600}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# 5. Try 2 more distinct prompt phrasings (different wording, not just shuffled words).
#    All 3 must produce wrong behavior before you mark BLOCKED.
```

If any of the 3 phrasings produces correct behavior → adjust the test prompt. Rerun.

If all 3 phrasings produce genuinely wrong behavior AND the fix requires changing a protected file → mark BLOCKED (see BLOCKED section below).

### Step 3d — Tool/MCP failure (no artifact)

```bash
# Check MCP service health for the relevant port:
curl -s http://localhost:8913/health  # Documents (T-04..T-07, DOCX/XLSX/PPTX)
curl -s http://localhost:8914/health  # Code sandbox (T-01..T-03)
curl -s http://localhost:8916/health  # TTS (T-09, WAV)
curl -s http://localhost:8919/health  # Security (T-11)
curl -s http://localhost:8920/health  # Memory (A-08)
curl -s http://localhost:8910/health  # ComfyUI bridge (T-10, PNG)

# Pipeline-side tool call evidence
docker logs portal5-pipeline --tail 100 | grep -iE "tool|mcp|error"

# MCP container logs
docker logs portal5-mcp-documents --tail 50
docker logs portal5-mcp-sandbox --tail 50
```

If an MCP service is down, restart it:
```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-mcp-<name>
sleep 10
# Then rerun:
python3 tests/portal5_uat_driver.py --append --test <TEST_ID>
```

### Step 3e — Routing failure (wrong model served)

```bash
# Check pipeline routing log
docker logs portal5-pipeline --tail 30 | grep -E "Routing|workspace|fallback"

# Check what model the OWUI conversation says was used
# (visible in the conversation header in the browser)

# If model fell back to a censored base model:
./launch.sh reseed && sleep 15
python3 tests/portal5_uat_driver.py --rerun --test <TEST_ID>
```

### Step 4 — Rerun decision

After diagnosing and applying a fix, use this decision tree:

| Situation | Rerun command |
|---|---|
| Single test, environment fix applied | `python3 tests/portal5_uat_driver.py --append --test <ID>` |
| Keyword edit applied | `python3 tests/portal5_uat_driver.py --rerun --test <ID>` |
| Whole section had resource failures | `python3 tests/portal5_uat_driver.py --rerun --section <name>` |
| Phase partially completed before interruption | Resume from that phase command with `--append` |
| >30% of phase FAILed, all empty-response | Run gate, clear memory, rerun section with `--rerun` |

**Never mark a test FAIL without at least one rerun attempt after diagnosing the root cause.** The standard is: the result must reflect the best validated outcome after remediation, not the outcome of the first cold attempt.

### Step 5 — Log the outcome

For every FAIL that required investigation, append a note to `tests/UAT_RUN_LOG.md`:

```
### Investigation: <TEST_ID> — <one-line symptom>
- **Root cause**: <what was actually wrong>
- **Remediation**: <what was done>
- **Rerun result**: PASS / FAIL / BLOCKED
- **Evidence**: <log line, wired_gb reading, or conversation observation>
```

---

## BLOCKED — when and how

Mark BLOCKED only after ALL of the following:
1. Three distinct prompt phrasings all produce the same wrong behavior
2. The persona's hard constraints in `config/personas/<slug>.yaml` confirm the expected behavior
3. The fix requires modifying a protected file (see Constraints) or a model upgrade

Append to `tests/UAT_RESULTS.md`:

```markdown
## BLOCKED-N: <test name>

**Test ID**: <id>  **Model slug**: <slug>
**Expected**: <exact quote from persona system_prompt hard constraint>
**Actual**: <copy model response verbatim>
**Retry 1**: [prompt variant] → [result summary]
**Retry 2**: [prompt variant] → [result summary]
**Retry 3**: [prompt variant] → [result summary]
**Protected file requiring change**: config/personas/<slug>.yaml — system_prompt
**Recommended fix**: <what change would resolve this, for the operator to action>
```

---

## Handling WARNs

WARN = test ran, some assertions passed but not all (≥50% with no critical fail). Investigate; don't ignore.

| WARN cause | Correct action |
|---|---|
| `min_length` failed on a truncated response | 32K context cap in big-model mode — known limitation. Note it, accept if behavior was correct. |
| Keyword appeared in code block but extraction missed it | Check the OWUI conversation; the API response is used, not DOM text. Accept if behavior was correct. |
| Ollama fallback served instead of MLX primary | Response may still be correct. Check routing log. Accept if behavior matches. |
| MCP tool transient error | Retry once: `python3 tests/portal5_uat_driver.py --append --test <id>` |
| Cold model load timeout | Driver retries 3×. If WARN persists, check proxy state and rerun section. |

---

## Memory State Commands (reference)

The proxy exposes graceful unload. Use it; never use `pkill -f mlx-proxy.py`.

```bash
# Wired + inactive memory snapshot
curl -s http://localhost:8081/health/wired | python3 -m json.tool

# Full proxy health (state, loaded model, uptime)
curl -s http://localhost:8081/health | python3 -m json.tool

# Ollama currently loaded models
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# Graceful unload — evicts MLX model + Ollama models, triggers GPU buffer reclaim
curl -X POST 'http://localhost:8081/unload?ollama=true' | python3 -m json.tool

# Pre-warm before re-running a section (optional, speeds up first test)
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto-coding", "messages": [{"role":"user","content":"hi"}], "max_tokens":5}'
sleep 30
```

`sudo purge` is no longer part of any recovery path. If a guide tells you to run it, that guide is stale.

If wired memory stays high for >5 min after `/unload`, the watchdog detects the leak and restarts the proxy via `launchctl kickstart -k`. Check `~/.portal5/logs/mlx-watchdog.log` if you suspect it didn't fire.

---

## Constraints (Non-Negotiable)

### NEVER modify
- `portal_pipeline/**`, `portal_mcp/**`, `config/`, `deploy/`, `Dockerfile.*`
- `scripts/openwebui_init.py`, `docs/HOWTO.md`, `imports/openwebui/**`

### NEVER run
- `docker compose down -v` — destroys Ollama model weights
- Concurrent inference requests — Metal/MLX crash risk
- `pkill -f mlx-proxy.py` — use `POST /unload` and let the watchdog handle proxy lifecycle
- `pkill -f mlx-readiness.py` — use `kill $(cat /tmp/mlx-readiness.pid)` for clean shutdown
- `sudo purge` — no longer part of any recovery path

### DO NOT
- Weaken assertions to make genuinely broken behavior appear green
- Mark BLOCKED without 3+ retry attempts with different prompts
- Modify OWUI conversations a human reviewer has already annotated
- Run `--all` in a single invocation — phased execution is the V2 contract

### Memory safety (handled by the system, not the agent)
The driver evicts at every tier transition. The proxy exposes `POST /unload[?ollama=true]` for explicit graceful eviction. The watchdog detects Metal GPU wired-buffer leaks (`state=none AND wired_gb > threshold` for N consecutive cycles) and recovers via `/unload` first, `launchctl kickstart -k` second. After all phases, `cleanup_after_uat()` runs automatically.

The agent's role is to observe, not to manage processes. Trust the system; if something is genuinely stuck, the watchdog will recover or notify.

### MLX on-demand loading rules
- **MLX loads models on request, not at startup.** A 503 from the proxy means it's idle and healthy — not crashed.
- **Model loading is slow.** A 32B model takes 30–90s; a 70–80B takes 1–3 minutes. Do NOT kill `mlx_lm.server` processes during loading.
- **Zombie = process stuck >5 min with /health dead.** Younger processes are still loading. The watchdog checks process age before killing.
- **Admission control is the authority on memory.** The proxy checks GPU memory before loading and rejects if insufficient. Do not preemptively evict below 90% memory — trust admission control.
- **First request to any MLX model is slow** (cold load). The driver retries on empty responses; second attempt usually succeeds.

---

## Playwright Selector Fallbacks

OWUI's Svelte selectors can vary by version. Try in order if a selector returns zero results:

**Prompt textarea:** `"textarea"` → `"[contenteditable='true']"` → `"[data-testid='chat-textarea']"`

**Stop streaming (stream-complete detection):** `'button[aria-label="Stop"]'` → `'button[title="Stop"]'` → `'button:has-text("Stop")'`

**Last assistant message:** `".message-container:last-child .prose"` → `"[data-testid='assistant-message']:last-child"` → `"[role='assistant']:last-child"`

**Tools toggle:** `'button[aria-label="Tools"]'` → `'button:has-text("+")'` → `'.chat-toolbar > button:first-child'`

Debug with a screenshot when a selector fails:
```python
await page.screenshot(path=f"/tmp/uat_screenshots/debug_{test_id}.png")
```

---

## Quick Reference: Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| Chat create 404 | OWUI API path changed | Check `/openapi.json` for `/chats` endpoints; adjust driver payload |
| Stream never ends | Model stuck | Increase `--timeout`; `curl http://localhost:8081/health` |
| No artifact download | Wrong selector or MCP error | `--headed` + `/tmp/uat_screenshots/`; check MCP port health |
| Persona missing from OWUI | Not seeded | `./launch.sh reseed && sleep 15` |
| MLX 503 / OOM | Both MLX + Ollama loaded | Watchdog auto-evicts. If recurrent, check watchdog log. |
| `[monitor]` warnings | Memory pressure rising | Watchdog handles it. Check `wired_gb` via `/health/wired`. |
| auto-agentic timeout | 80B MoE slow | `--timeout 360`; 3+ min per prompt is normal |
| Bench persona hard-fails | MLX bench model not loaded | `./launch.sh logs \| grep <model-name>` |
| Wired memory stuck high after phase | Metal buffer leak | `curl -X POST 'http://localhost:8081/unload?ollama=true'` |

---

## Section Reference

Sections are filtering inputs (`--section auto-coding`). The driver reorders tests internally using cascade ordering (tier → model_slug), so section boundaries don't constrain execution order within a single invocation.

| Section | Test count | Predominant tier | Phase | Approx time alone |
|---|---|---|---|---|
| `auto` | 4 | mlx_small + any | 1 (smoke), 4 | 5–10 min |
| `auto-daily` | 8 | mlx_small (gemma-4-26b) | 4 | 15–25 min |
| `auto-coding` | 26 | mlx_large + mlx_small + any | 3 | 40–60 min |
| `auto-spl` | 2 | mlx_small | 4 | 8–12 min |
| `auto-mistral` | 2 | mlx_small | 4 | 8–12 min |
| `auto-creative` | 3 | mlx_small | 4 | 8–12 min |
| `auto-docs` | 7 | mlx_small + ollama | 5 | 15–25 min |
| `auto-agentic` | 2 | mlx_large + mlx_small | 2 | 20–35 min |
| `auto-security` | 5 | mlx_large | 2 | 10–15 min |
| `auto-redteam` | 3 | mlx_large | 2 | 8–12 min |
| `auto-blueteam` | 2 | ollama | 5 | 5–8 min |
| `auto-reasoning` | 5 | mlx_large + mlx_small + ollama | 4 | 20–30 min |
| `auto-data` | 7 | mlx_large + mlx_small + any | 4 | 15–20 min |
| `auto-compliance` | 3 | mlx_large | 2 | 10–15 min |
| `auto-research` | 5 | mlx_large + any | 2 | 10–15 min |
| `auto-vision` | 6 | mlx_large + any | 2 | 10–15 min |
| `auto-music` | 3 | media_heavy | 6 | 10–15 min |
| `auto-video` | 2 | media_heavy | 6 | 15–30 min |
| `auto-math` | 2 | mlx_small | 4 | 5–10 min |
| `advanced` | 8 | mixed (incl. mlx_small two-chat) | 8 | 18–25 min |
| `benchmark` | 13 | mlx_large + mlx_small + ollama | 7 | 60–90 min |

**Total run (phases 1–8, `--skip-bots`):** approximately 295–440 minutes.

---

## Run Log Template

`tests/UAT_RUN_LOG.md` is what the agent writes. It accumulates across the run and is the resume reference. The gate script appends gate rows automatically; the agent appends phase rows and investigation notes.

### Phase row format

```markdown
# UAT Run Log — <YYYYMMDDTHHMMZ>

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 14:02Z | 14:08Z | 4 | 4P/0W/0F | exit=0 |
| 2. mlx_large heavy | DONE | 14:09Z | 15:23Z | 24 | 20P/2W/2F (cum: 24P/2W/2F) | exit=0 |
| 3. auto-coding | PAUSED | 15:24Z | — | 12/26 | 9P/1W/2F (partial) | watchdog restart at 15:51Z |
| 3. auto-coding | DONE | 16:08Z | 17:01Z | 26 | resumed --test for 14 remaining | 22P/2W/2F (cum) |
```

Status values: `DONE`, `PAUSED`, `BLOCKED`, `SKIPPED`.

### Investigation note format (append below phase table)

For each FAIL that required investigation, append:

```markdown
### Investigation: <TEST_ID> — <one-line symptom>
- **Root cause**: <what was wrong>
- **Remediation**: <what was done>
- **Rerun result**: PASS / FAIL / BLOCKED
- **Evidence**: <wired_gb reading, log excerpt, or OWUI conversation observation>
```

---

## Final Report

After Phase 8 completes (or the run is declared final), append a `## Final Report` section to `tests/UAT_RUN_LOG.md`. The report must contain all of the following:

```markdown
## Final Report — <RUN_TS>

### Overall Status: PASS / PARTIAL / FAIL

### Totals
- Total tests run: N
- PASS: N  WARN: N  FAIL: N  BLOCKED: N  SKIPPED: N
- Pass rate (excl. SKIP): N%

### Phases Completed
| Phase | Result | Notes |
|---|---|---|
| 1. smoke | PASS | |
| 2. mlx_large heavy | PASS | |
| ... | | |

### Issues Encountered and Resolved
For each issue that required investigation and was resolved:
- **<TEST_ID>**: <symptom> → <root cause> → <remediation> → PASS

### Persistent Failures (FAIL after remediation)
For each test that FAILed after at least one rerun attempt:
- **<TEST_ID>**: <final symptom and why remediation did not resolve>

### BLOCKED Items
For each BLOCKED test (copy from the BLOCKED entries in UAT_RESULTS.md):
- **<BLOCKED-N>**: <test name> — <recommended fix>

### Skipped with Justification
- `--skip-bots`: Telegram/Slack containers not configured (A-05, A-06)
- `--skip-artifacts`: ComfyUI/Wan2.2 not available (if applicable)

### Evidence References
- Driver log: `/tmp/uat_phase*.log`
- Screenshots: `/tmp/uat_screenshots/`
- Artifacts: `/tmp/uat_artifacts/`
- Results file: `tests/UAT_RESULTS.md`
- Run log: `tests/UAT_RUN_LOG.md`

### Recommended Follow-Up
List any items that need operator action after this run.
```

**The report is the deliverable.** A run that ends without a report has not completed, regardless of how many tests passed.

---

*Last updated: 2026-05-15 (MLX readiness watcher added to Phase 0 pre-flight — starts mlx-readiness.py in background, stores PID in /tmp/mlx-readiness.pid, verified with --read before Phase 1; watcher stop added to Phase 8 cleanup; auto-daily section added to Phase 4 invocation with 8 WS-DD tests, ~33 test count; Section Reference updated; Resume after reboot: watcher restart step added; NEVER RUN: pkill mlx-readiness.py added; total run estimate updated)*

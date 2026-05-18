# PORTAL5_UAT_LIBRECHAT_EXECUTE_V1 — Claude Code Execution Prompt

Clone `https://github.com/ckindle-42/portal-5/`. The live system is already running.
`tests/portal5_uat_driver.py` is implemented and the `--frontend librechat` track is stable as of HEAD `e855092`.

This is the **LibreChat parity track**. It re-runs the same `TEST_CATALOG` against LibreChat at `http://localhost:8082` to validate that the UX path produces equivalent outcomes to the Open WebUI run already captured in `tests/UAT_RESULTS.md`.

**This document is a sibling to `tests/PORTAL5_UAT_EXECUTE_V2.md`, not a replacement.** Below the UX layer, the pipeline, MLX, Ollama, and MCP servers are identical — so most operational protocols (inter-phase gate, memory recovery, BLOCKED handling, run log format) are referenced into V2 rather than duplicated here. Read V2 if you have not already; this doc assumes familiarity with it.

---

## Execution Standard

The eight items in `PORTAL5_UAT_EXECUTE_V2.md § Execution Standard` apply verbatim — UAT rigor is independent of frontend. Run that section once; do not re-paste it here.

Two LibreChat-specific additions:

9. **A passing OWUI run is a precondition.** Without `tests/UAT_RESULTS.md` populated, there's nothing to diff against and a fresh LibreChat FAIL cannot be classified as a UX delta vs. a pipeline issue. If OWUI Phase 1-8 has not completed, run V2 first.
10. **A FAIL on LibreChat where OWUI is PASS is a real LibreChat UX finding.** Do not paper over it. Capture in the Parity Findings section of the final report.

---

## Your Role

You are the **UAT execution agent for the LibreChat parity track**. You do not build or modify the driver. You run it phase by phase, monitor between phases, diagnose failures, and produce a clean run log at `tests/UAT_LIBRECHAT_RUN_LOG.md` (separate from the OWUI run log).

**The pipeline behavior is assumed correct.** It was validated by the prior OWUI run. If a LibreChat-only FAIL appears on a test that PASSED on OWUI, your investigation starts at the LibreChat UI layer (selector, preset, navigation), not at the model or pipeline.

**Sequential only.** Same constraint as V2. The driver's cascade ordering is identical regardless of frontend — `mlx_large` → `mlx_small` → `ollama` → `any` → `media_heavy` with eviction at tier transitions. MLX and Ollama never load simultaneously.

**Phased.** Same eight-phase tier cascade as V2, executed with `--frontend librechat` and `--append` after the first phase. Inter-phase gating uses the same `tests/inter_phase_gate.sh` script with the same thresholds. The gate cares about backend memory, which is frontend-independent.

---

## What this run validates

151 tests through LibreChat at `http://localhost:8082`, producing **real LibreChat conversations** visible in the LibreChat UI. Each conversation is a parity datapoint: did the model, persona, tool, and artifact behave the same when the request came in through LibreChat instead of Open WebUI?

The UAT driver validates the same user-observable behavioral contracts. What's exercised differently here:

- Login form fill (Playwright, no API)
- Endpoint/model picker click flow
- Preset menu click flow for persona tests (`🎭 {name}` seeded presets)
- Composer interaction (Send button click — Enter does NOT submit in v0.8.6-rc1)
- Streaming completion detection (DOM stable + stop button; no `<details type="reasoning">` workaround)
- Assistant message DOM scraping (`.message-content`)
- Per-conversation URL capture (post-first-message `/c/{conversation_id}`)
- File attachment download flow

What is NOT exercised differently — same code path as OWUI:
- Routing decisions (validated via pipeline logs in both runs)
- Model selection within a workspace
- MCP tool dispatch
- Persona system prompts (delivered via preset, not per-conversation)
- Cross-session memory (Memory MCP)

---

## Phase 0 — Pre-flight (run once, ~5 min)

```bash
# 1. The repo and the OWUI run are prerequisites
git clone https://github.com/ckindle-42/portal-5/ 2>/dev/null && cd portal-5 || cd portal-5
git rev-parse HEAD
git log --oneline -3 | grep -q "LibreChat" \
  && echo "PASS: LibreChat track present at HEAD" \
  || { echo "ABORT: LibreChat track missing at HEAD"; exit 1; }

# 2. The OWUI results must exist — the diff at the end depends on them
test -s tests/UAT_RESULTS.md && echo "PASS: OWUI results exist for diff" \
  || { echo "ABORT: run PORTAL5_UAT_EXECUTE_V2.md first — no OWUI baseline to compare against"; exit 1; }

# 3. Architectural reference (read these BEFORE running)
cat CLAUDE.md
cat docs/UAT_LIBRECHAT_DOM_NOTES.md   # verified selectors for the current LibreChat image

# 4. LibreChat secrets in .env
grep -E "^LIBRECHAT_(ADMIN_PASSWORD|JWT_SECRET|JWT_REFRESH_SECRET|CREDS_KEY|CREDS_IV)=" .env \
  || { echo "ABORT: LibreChat secrets missing — see .env.example § Alternative Frontends"; exit 1; }

# 5. LibreChat must be up and seeded
./launch.sh up-librechat 2>&1 | tee -a /tmp/uat_librechat_phase0.log
curl -sf http://localhost:8082/health && echo " LibreChat OK" \
  || { echo "ABORT: LibreChat not healthy at :8082"; exit 1; }

# Seeded persona presets — at least 100 presets (102 personas at HEAD, allow 2 in-flight)
docker exec portal5-librechat-init cat /tmp/seed_summary.json 2>/dev/null \
  || ./launch.sh seed-librechat
echo "Verify in the LibreChat UI: open http://localhost:8082, log in, click Presets — expect ~100+ rows prefixed with 🎭"

# 6. Pipeline, MLX, Ollama — same checks as V2 Phase 0
./launch.sh status
curl -sf http://localhost:9099/health | python3 -m json.tool
curl -sf http://localhost:8081/health | python3 -m json.tool   # MLX proxy

# 7. Stop the MLX watchdog (same reason as V2 — restart after Phase 8)
./launch.sh stop-mlx-watchdog

# 8. Start MLX readiness watcher (same as V2 — required for phased runs)
./launch.sh start-mlx-readiness &

# 9. Driver parses + flag exposed
python3 -m py_compile tests/portal5_uat_driver.py && echo "PASS: driver compiles"
python3 tests/portal5_uat_driver.py --help | grep -q "\-\-frontend.*openwebui.*librechat" \
  && echo "PASS: --frontend exposed"

# 10. Env validation — confirm the driver refuses to start without the password
LIBRECHAT_ADMIN_PASSWORD= python3 tests/portal5_uat_driver.py --frontend librechat --test WS-01 2>&1 \
  | grep -q "LIBRECHAT_ADMIN_PASSWORD" \
  && echo "PASS: env validation fires"
```

### Initialize the LibreChat run tracker

```bash
RUN_TS=$(date -u +%Y-%m-%dT%H:%MZ)
cat > tests/UAT_LIBRECHAT_RUN_LOG.md <<EOF
# Portal 5 UAT LibreChat Parity Run — $RUN_TS

OWUI baseline: \`tests/UAT_RESULTS.md\` (timestamp from V2 run)
LibreChat results: \`tests/UAT_RESULTS_LIBRECHAT.md\`
LibreChat image: $(docker inspect portal5-librechat --format='{{.Image}}' 2>/dev/null)
DOM notes: \`docs/UAT_LIBRECHAT_DOM_NOTES.md\`

## Phases

| # | Section | Status | Started | Ended | Tests | Pass/Warn/Fail | Notes |
|---|---------|--------|---------|-------|-------|----------------|-------|
EOF
```

---

## Phase 0.5 — Calibration (one-time per LibreChat image version)

**Why this exists:** LibreChat ships UI changes between minor releases. Selectors verified on v0.8.6-rc1 may not work on v0.9.x. Calibration confirms the selectors in `tests/frontends/librechat.py` still hit the right DOM elements before committing 8+ hours to a full run.

Skip Phase 0.5 only if:
1. The LibreChat image digest matches the one recorded in `docs/UAT_LIBRECHAT_DOM_NOTES.md` § header, AND
2. A prior LibreChat run on this image completed in `tests/UAT_RESULTS_LIBRECHAT.md` within the last week.

Otherwise run it:

```bash
# Five representative tests across the surfaces that differ on LibreChat:
#   WS-01     — workspace model picker (no preset)
#   WS-DD-01  — auto-daily routing (sanity)
#   P-W06     — persona preset click (IT Expert)
#   P-D01     — persona preset with code output
#   A-08      — two-chat cross-session memory (URL capture per chat)
python3 tests/portal5_uat_driver.py \
  --frontend librechat \
  --test WS-01 --test WS-DD-01 --test P-W06 --test P-D01 --test A-08 \
  --calibrate --calibrate-output calibration_librechat.json --headed

# Review calibration_librechat.json by hand. For each entry, check:
#   1. response_text — is it the actual model output, or a UI fragment / sidebar bleed?
#   2. routed_model — is it populated? (Should be non-empty from pipeline logs)
#   3. chat_url — does it match /c/{uuid} pattern? (Not /c/new)
#   4. assertions — any unexpected misses?
```

**Calibration outcomes:**

| Outcome | Action |
|---|---|
| All 5 entries look correct | Proceed to Phase 1 |
| `response_text` includes UI chrome (sidebar, header, etc.) | Selector for `.message-content` is wrong on this image → update `tests/frontends/librechat.py::get_last_response` and `docs/UAT_LIBRECHAT_DOM_NOTES.md` before any phase |
| `routed_model` empty on every entry | Pipeline logs unreachable or log format changed — verify `docker logs portal5-pipeline --tail 5` is producing the `Routing workspace=... → backend=... model=...` line |
| Preset click produced wrong persona (`P-W06` / `P-D01` response style doesn't match OWUI baseline) | Preset selector wrong → recheck `_select_preset` in `tests/frontends/librechat.py` |
| `A-08` chat 2 used the same conversation as chat 1 | `/c/new` navigation did not create a fresh conversation → recheck `start_new_chat` |

After fixing any of the above, re-run Phase 0.5 until all five entries look correct.

---

## Phase Plan

Same tier-cascade order as V2. The driver's `sort_tests_cascade` ensures each phase loads its big models once, runs all tests in that tier, then evicts at the boundary. This is identical to the OWUI run — only the surface posting requests changes.

| Phase | Section(s) | Approx tests | Tier | Approx wall time |
|---|---|---|---|---|
| 1 | `auto` (smoke) | 4 | mlx_small | 10 min |
| 2 | compliance, agentic, vision, research, security, redteam | 35 | mlx_large/mlx_small | 90-120 min |
| 3 | auto-coding | 30 | mlx_small/mlx_large | 90 min |
| 4 | data, reasoning, creative, mistral, spl, math | 26 | mlx_small/any | 60 min |
| 5 | blueteam, docs | 11 | ollama/mlx_small | 30 min |
| 6 | music, video | 5 | media_heavy | 30 min |
| 7 | benchmark | 18 | mlx_small | 90 min |
| 8 | advanced + manual | 12 | mixed | 30 min |

**Total estimated wall time: 7-9 hours.** Same as the OWUI run — the bottleneck is model load + inference, not the frontend.

### What you must NOT do

The four prohibitions in `V2 § What you must NOT do` apply verbatim: no `--all` in one shot, no skipping the inter-phase gate, no concurrent driver invocations, no rebuilding mid-run. Add one LibreChat-specific item:

5. **Do not log into LibreChat in a separate browser tab during a phase.** LibreChat issues a single JWT per session; the driver's Playwright context will lose its auth state if you sign in elsewhere. Review conversations only AFTER each phase completes.

---

## Phase 1 — Smoke (auto section)

```bash
# First phase initializes UAT_RESULTS_LIBRECHAT.md, so do NOT use --append here.
python3 tests/portal5_uat_driver.py --frontend librechat --section auto --headed 2>&1 \
  | tee /tmp/uat_librechat_phase1.log
PHASE1_EXIT=$?

# Open http://localhost:8082 in the headed browser and confirm:
#  - Four new conversations appear in the LibreChat conversation list
#  - Conversations contain the expected model responses (not just empty bubbles)
#  - tests/UAT_RESULTS_LIBRECHAT.md exists with rows + clickable links
test -s tests/UAT_RESULTS_LIBRECHAT.md && echo "Results file populated" \
  || { echo "ABORT: LibreChat results file empty"; exit 1; }

# Log the phase
{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS_LIBRECHAT.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS_LIBRECHAT.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS_LIBRECHAT.md)
  echo "| 1. smoke (auto) | DONE | $RUN_TS | $(date -u +%H:%MZ) | 4 | ${PASS}P/${WARN}W/${FAIL}F | exit=$PHASE1_EXIT |"
} >> tests/UAT_LIBRECHAT_RUN_LOG.md
```

**If smoke produces zero conversations or a Python error**, diagnose before any further phase. Most common causes specific to LibreChat:
- LibreChat auth refused — verify `.env` `LIBRECHAT_ADMIN_PASSWORD` matches the seeded admin account
- Preset menu selector wrong — Phase 0.5 should have caught this; if it didn't, the persona tests (none in Phase 1) won't trigger it but workspace tests still need the model picker
- Send button selector wrong — none of the four prompts will produce a response

**If smoke passed**, run the inter-phase gate. The gate is unchanged from V2:
```bash
bash tests/inter_phase_gate.sh 1 4
```

The gate cares about pipeline + MLX + memory — none of those are LibreChat-affected. Same thresholds, same auto-recovery, same WARN/FAIL semantics as V2 § Inter-Phase Gate. **Read that section if you haven't yet.**

---

## Phase 2 — mlx_large-heavy sections

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section auto-compliance --section auto-agentic \
  --section auto-vision --section auto-research \
  --section auto-security --section auto-redteam --append 2>&1 \
  | tee /tmp/uat_librechat_phase2.log
PHASE2_EXIT=$?

# Log + gate
{
  TOTAL=$(grep -c '^| ' tests/UAT_RESULTS_LIBRECHAT.md)
  echo "| 2. mlx_large-heavy | DONE | $(date -u +%H:%MZ) | $TOTAL tests cumulative | exit=$PHASE2_EXIT |"
} >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 2 35
```

Section rationale and exclusions mirror V2 § Phase 2 — read that for why `auto-data` is in Phase 4 and not here.

---

## Phase 3 — Bulk coding (auto-coding alone)

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section auto-coding --append 2>&1 | tee /tmp/uat_librechat_phase3.log
PHASE3_EXIT=$?

{ echo "| 3. coding | DONE | $(date -u +%H:%MZ) | 30 | exit=$PHASE3_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 3 30
```

---

## Phase 4 — Remaining mlx_small/any sections

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section auto-data --section auto-reasoning \
  --section auto-creative --section auto-mistral \
  --section auto-spl --section auto-math --append 2>&1 \
  | tee /tmp/uat_librechat_phase4.log
PHASE4_EXIT=$?

{ echo "| 4. mlx_small/any | DONE | $(date -u +%H:%MZ) | 26 | exit=$PHASE4_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 4 26
```

---

## Phase 5 — Ollama + mlx_small (blueteam, docs)

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section auto-blueteam --section auto-docs --append 2>&1 \
  | tee /tmp/uat_librechat_phase5.log
PHASE5_EXIT=$?

{ echo "| 5. ollama+small | DONE | $(date -u +%H:%MZ) | 11 | exit=$PHASE5_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 5 11
```

---

## Phase 6 — Media-heavy (music, video)

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section auto-music --section auto-video --append 2>&1 \
  | tee /tmp/uat_librechat_phase6.log
PHASE6_EXIT=$?

{ echo "| 6. media-heavy | DONE | $(date -u +%H:%MZ) | 5 | exit=$PHASE6_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 6 5
```

**LibreChat artifact-download caveat:** The driver's URL-from-response-text fallback covers the MCP-emitted `/files/<name>.<ext>` and ComfyUI `/view?filename=...` cases. The LibreChat in-UI download click was provisionally selected in `docs/UAT_LIBRECHAT_DOM_NOTES.md` — if Phase 6 produces FAIL on `*_valid` assertions but the response text contains a valid URL, the in-UI click selector likely needs updating. The download still succeeded via the URL fallback; the FAIL is a selector issue, not a real artifact failure.

---

## Phase 7 — Benchmark (CC-01 across 13+ models)

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section benchmark --append 2>&1 | tee /tmp/uat_librechat_phase7.log
PHASE7_EXIT=$?

{ echo "| 7. benchmark | DONE | $(date -u +%H:%MZ) | 18 | exit=$PHASE7_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 7 18
```

---

## Phase 8 — Advanced + manual + final verify

```bash
python3 tests/portal5_uat_driver.py --frontend librechat \
  --section advanced --append 2>&1 | tee /tmp/uat_librechat_phase8.log
PHASE8_EXIT=$?

# Manual tests A-05, A-06, A-07 follow the V2 protocol — operator review in the
# LibreChat UI, then update the conversation title to [PASS]/[FAIL]/[PARTIAL].
# LibreChat conversation titles are auto-generated and not renamed by the driver;
# operator pins the result by editing the conversation title in the UI.

# via_dispatcher tests in the advanced section will auto-SKIP on --frontend librechat —
# they bypass both frontends to exercise the Telegram/Slack pipeline path,
# already covered in V2 Phase 8.

{ echo "| 8. advanced | DONE | $(date -u +%H:%MZ) | 12 | exit=$PHASE8_EXIT |"; } \
  >> tests/UAT_LIBRECHAT_RUN_LOG.md
bash tests/inter_phase_gate.sh 8 12

# Final verification — LibreChat conversations exist for every test row
{
  TOTAL_ROWS=$(grep -c '^| ' tests/UAT_RESULTS_LIBRECHAT.md)
  echo ""
  echo "## Phase 8 final verification"
  echo "- Total result rows: $TOTAL_ROWS"
  echo "- Expected: ~151 (minus auto-SKIP'd via_dispatcher tests)"
  echo "- Each row's chat link should resolve to a LibreChat conversation at /c/{uuid}"
  echo ""
  echo "Sample-check 3 random row links by hand — each should open a real conversation."
} >> tests/UAT_LIBRECHAT_RUN_LOG.md

# Restart the watchdog now that the run is done
./launch.sh start-mlx-watchdog
```

---

## Phase 9 — Parity diff against OWUI

This is the payoff phase. It reads both result files and surfaces every test where the two frontends disagreed.

```bash
python3 - <<'PY' | tee -a tests/UAT_LIBRECHAT_RUN_LOG.md
import re

def parse(path):
    rows = {}
    try:
        text = open(path).read()
    except FileNotFoundError:
        return rows
    pat = re.compile(r"^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*\[([A-Za-z0-9][A-Za-z0-9_.-]*)\s")
    for line in text.split("\n"):
        m = pat.match(line)
        if m:
            rows[m.group(2)] = m.group(1).strip()
    return rows

owui = parse("tests/UAT_RESULTS.md")
libre = parse("tests/UAT_RESULTS_LIBRECHAT.md")
all_ids = sorted(set(owui) | set(libre))

# Categorize deltas
real_deltas = []     # PASS/FAIL or PASS/WARN disagreements — investigate
skip_deltas = []     # one side SKIP, other ran — by design or seeding gap
missing = []         # in one file but not the other

for tid in all_ids:
    o = owui.get(tid, "—")
    l = libre.get(tid, "—")
    if "—" in (o, l):
        missing.append((tid, o, l))
    elif o == l:
        continue
    elif "SKIP" in (o, l):
        skip_deltas.append((tid, o, l))
    else:
        real_deltas.append((tid, o, l))

print("\n## Parity Findings\n")
print(f"- Tests on both: {len(set(owui) & set(libre))}")
print(f"- Real deltas (real UX divergence): {len(real_deltas)}")
print(f"- SKIP deltas (by-design — via_dispatcher, persona_preset_unreachable, etc.): {len(skip_deltas)}")
print(f"- Missing on one side: {len(missing)}")

if real_deltas:
    print("\n### Real deltas — investigate each\n")
    print("| TEST | OWUI | LIBRECHAT |")
    print("|------|------|-----------|")
    for tid, o, l in real_deltas:
        print(f"| {tid} | {o} | {l} |")

if skip_deltas:
    print("\n### SKIP deltas — confirm each is by-design\n")
    print("| TEST | OWUI | LIBRECHAT |")
    print("|------|------|-----------|")
    for tid, o, l in skip_deltas:
        print(f"| {tid} | {o} | {l} |")

if missing:
    print("\n### Missing rows — gap in coverage\n")
    print("| TEST | OWUI | LIBRECHAT |")
    print("|------|------|-----------|")
    for tid, o, l in missing:
        print(f"| {tid} | {o} | {l} |")
PY
```

**Interpreting the parity table:**

| Pattern | Meaning | Action |
|---|---|---|
| OWUI PASS, LibreChat FAIL | LibreChat UX defect (selector wrong, persona not selected, etc.) | Investigate with Failure Investigation Protocol below. File as a LibreChat finding. |
| OWUI PASS, LibreChat WARN | LibreChat met assertions but downgraded (likely routing mismatch from pipeline logs) | Verify the route check is reading correctly — see `tests/portal5_uat_driver.py::_check_routed_model` |
| OWUI FAIL, LibreChat PASS | Surprising; possibly OWUI flake or LibreChat permissive path | Re-run the OWUI test once with `--rerun --test {ID}`; if it then passes, file as flake |
| OWUI FAIL, LibreChat FAIL | Pipeline / model / test issue (frontend-independent) | Already in V2 run log; no new finding |
| OWUI PASS, LibreChat SKIP `via_dispatcher` | By design (Telegram/Slack pipeline path) | Note; no action |
| OWUI PASS, LibreChat SKIP `persona_preset_unreachable` | Seeding gap — preset not created in LibreChat | Re-run `./launch.sh seed-librechat` and `--rerun-failed` |

---

## Resume Protocol — when a phase is interrupted

Same protocol as `V2 § Resume Protocol` with two substitutions:
- `tests/UAT_RESULTS.md` → `tests/UAT_RESULTS_LIBRECHAT.md`
- `tests/UAT_RUN_LOG.md` → `tests/UAT_LIBRECHAT_RUN_LOG.md`

The `--rerun-failed` flag works identically and parses the LibreChat results file when invoked under `--frontend librechat`. State file: `/tmp/portal5-rerun-failed-state.json` (shared between frontends — do not run two `--rerun-failed` invocations against different frontends concurrently).

---

## Failure Investigation Protocol — LibreChat-specific deltas

For **model behavior** failures, **memory pressure**, **MCP failures**, **routing failures**, **OWUI Audio STT** issues, **MLX zombie cleanup** — these are pipeline-side and unchanged from V2 § Failure Investigation Protocol Steps 3a-3h. Read them once; apply them when the symptom is on the model or pipeline side.

The following six failure types are **LibreChat-specific** — they do not occur on the OWUI run. Add these to your diagnostic vocabulary.

### Step 3-LC-a — `persona_preset_unreachable` SKIP

**Symptom:** A persona test (`P-*`) recorded SKIP with detail `persona_preset_unreachable`.

**Investigate:**
```bash
# 1. Confirm the preset exists in LibreChat's database
docker exec portal5-librechat-mongodb mongosh LibreChat --eval \
  'db.presets.find({title: /^🎭 /}).count()'
# Expected: ~102. If lower, seeding didn't run cleanly.

# 2. Re-seed and confirm
./launch.sh seed-librechat 2>&1 | tail -5
# Expected log: "Persona presets: N created, M skipped"

# 3. Confirm the specific persona title that failed
grep "{failed_slug}" config/personas/{failed_slug}.yaml | head -2
# Match against what mongosh shows: titles must equal "🎭 {name}"
```

**Fix:**
- If preset count is right but specific one missing → manually create via LibreChat UI Agent Builder, then `--rerun-failed`
- If preset count is wrong → `./launch.sh seed-librechat` resolves it, then `--rerun-failed`

### Step 3-LC-b — All persona tests SKIP

**Symptom:** Every `P-*` test in a phase recorded SKIP.

**Cause:** The preset menu selector in `tests/frontends/librechat.py::_select_preset` is wrong for this LibreChat version. The driver can't find the menu button to open the preset list, so it falls through to the `_CustomInstructionsNotFound` path and SKIPs.

**Investigate:**
```bash
# Run Phase 0.5 calibration on just one persona test, with --headed to watch
python3 tests/portal5_uat_driver.py --frontend librechat --test P-W06 \
  --calibrate --calibrate-output /tmp/p-w06.json --headed

# Inspect the LibreChat UI manually — locate the actual preset menu button.
# Then update tests/frontends/librechat.py::_select_preset's `preset_btn_candidates`
# list and docs/UAT_LIBRECHAT_DOM_NOTES.md § Preset menu.
```

**Fix:** Update the selector. Do not work around with the system-prompt fallback — that path is documented as `_CustomInstructionsNotFound` because v0.8.6-rc1 has no per-conversation system-prompt UI.

### Step 3-LC-c — Empty response on every test

**Symptom:** Every test in a phase produced an empty response_text, all FAIL with "Substantive response: 0 chars".

**Cause:** The assistant-message container selector is wrong, OR LibreChat is not actually receiving the request (auth/proxy issue).

**Investigate:**
```bash
# 1. Confirm requests are reaching the pipeline
docker logs portal5-pipeline --tail 50 | grep -E "Routing workspace|POST /v1"
# Expected: recent log lines showing requests.

# 2. If pipeline sees requests, the response is reaching LibreChat but the DOM scrape is wrong.
# Open LibreChat in a headed browser, send a test message, devtools-inspect the assistant
# message container. Compare to tests/frontends/librechat.py::get_last_response candidates.

# 3. If pipeline does NOT see requests, LibreChat isn't forwarding — check librechat.yaml
# baseURL and the docker network bridge:
docker exec portal5-librechat curl -sf http://portal-pipeline:9099/health
```

**Fix:**
- DOM selector → update `.message-content` candidate list in `tests/frontends/librechat.py::get_last_response`
- Pipeline unreachable from LibreChat → restart LibreChat: `docker restart portal5-librechat`

### Step 3-LC-d — `libre_login_failure` at phase start

**Symptom:** Phase exits within seconds; log shows Playwright TimeoutError on `input[type="email"]`.

**Cause:** Either LibreChat is not actually serving the login page (502/503), or the email field selector changed.

**Investigate:**
```bash
# 1. Direct curl
curl -sI http://localhost:8082 | head -5
# Expected: HTTP/1.1 200 OK

# 2. LibreChat container logs
docker logs portal5-librechat --tail 30 | grep -iE "error|fatal"

# 3. Manual login test
# Open http://localhost:8082 in a real browser, log in with the .env credentials.
# If that works, the selector is the issue. If it doesn't, LibreChat is broken.
```

**Fix:** Restart LibreChat (`docker restart portal5-librechat`) or update the email selector in `tests/frontends/librechat.py::login`.

### Step 3-LC-e — Send button not found (LibreChat send path differs)

**Symptom:** Phase 1 smoke produces no responses; logs show repeated waits for the stop button to appear.

**Cause:** LibreChat v0.8.6-rc1 requires clicking `button[aria-label="Send message"]` — Enter alone does NOT submit. If the driver's `send_prompt` is pressing Enter (older code path) or if the Send button selector is wrong on a newer LibreChat version, the request never goes out.

**Investigate:**
```bash
grep -A5 "async def send_prompt" tests/frontends/librechat.py | head -10
# Should show Send button click, not just `press("Enter")`
```

**Fix:** Verify `send_prompt` clicks the Send button. If LibreChat changed the Send selector, update accordingly and document in DOM notes.

### Step 3-LC-f — Routed-model column shows `|` separator but values look weird

**Symptom:** Result rows show `Routed model: mlx-apple-silicon|some-different-model-name`, and the route check fails.

**Cause:** The pipeline logs are emitting routing decisions for a workspace, but the **actual** model that streamed the response was different — likely a fallback. This is a real pipeline finding, not a LibreChat issue. The pipeline-log read is doing its job correctly.

**Fix:** This is a pipeline routing investigation, not LibreChat. Cross-reference V2 § Step 3e — Routing failure.

---

## BLOCKED — when and how

Same rules as `V2 § BLOCKED — when and how`, with one addition:

**BLOCKED-LC**: LibreChat-specific blocker. Use when:
- LibreChat container won't start after `./launch.sh up-librechat` and three restart attempts
- MongoDB or Meilisearch dependency is broken and seeding cannot complete
- LibreChat UI is reachable but auth is permanently broken (cannot log in via .env credentials AND cannot register a new admin)

These are infrastructure failures, not test defects.

---

## Handling WARNs

Same as V2 § Handling WARNs. The LibreChat path produces no additional WARN classes that V2 doesn't already cover.

---

## Constraints (Non-Negotiable)

The four lists in `V2 § Constraints (Non-Negotiable)` apply verbatim. Two LibreChat-specific additions:

**NEVER modify (additions):**
- `tests/frontends/librechat.py` during a phased run (UI changes require Phase 0.5 re-calibration)
- `docs/UAT_LIBRECHAT_DOM_NOTES.md` in a way that contradicts the running LibreChat image

**DO NOT (additions):**
- Sign into LibreChat in another browser tab during a phase (steals the auth session)
- Restart LibreChat mid-phase (loses Playwright cookie state)

---

## Run Log Template

The `tests/UAT_LIBRECHAT_RUN_LOG.md` file built up by the phase-by-phase log writes ends with these required sections. Same format as `V2 § Run Log Template` and `V2 § Final Report` with one added subsection.

```markdown
## Final Report — <RUN_TS>

### Overall Status: PASS / PARTIAL / FAIL

### Totals
- Tests run: <N>
- PASS: <N>
- WARN: <N>
- FAIL: <N>
- SKIP: <N>
- MANUAL: <N>
- BLOCKED: <N>

### Phases Completed
(Tabular summary — phase, status, count, duration, notes)

### Issues Encountered and Resolved
(Per-issue: classification, root cause, fix, validation)

### Persistent Failures (FAIL after remediation)
(Tests that stayed FAIL after diagnosis + rerun)

### BLOCKED / BLOCKED-LC Items
(Per-blocker: which test, what infrastructure, what was tried)

### Skipped with Justification
(Per-skip: which test, which SKIP code — `via_dispatcher`, `persona_preset_unreachable`, etc.)

### Parity Findings (LibreChat-specific, NEW for this run)
Copy from Phase 9's diff output. For each row in the "Real deltas" table, add one paragraph:
- TEST ID + name
- OWUI outcome + LibreChat outcome
- Root cause (UI selector, preset missing, etc.)
- Whether the issue is fixed (selector updated, etc.) or open
- Reference to the LibreChat conversation URL for evidence

### Evidence References
- OWUI results: `tests/UAT_RESULTS.md` (baseline)
- LibreChat results: `tests/UAT_RESULTS_LIBRECHAT.md`
- This run log: `tests/UAT_LIBRECHAT_RUN_LOG.md`
- DOM notes (snapshot at run start): `docs/UAT_LIBRECHAT_DOM_NOTES.md`
- Phase logs: `/tmp/uat_librechat_phase[1-8].log`

### Recommended Follow-Up
- LibreChat selector updates needed (with file:line refs)
- LibreChat seeding gaps (which presets are missing)
- Pipeline issues that surfaced on both runs (file as separate fix tasks)
```

---

*This document is the entry point. Hand it to Claude Code along with the framing:*

> "Execute PORTAL5_UAT_LIBRECHAT_EXECUTE_V1.md. The OWUI baseline run already completed and produced tests/UAT_RESULTS.md — your job is the LibreChat parity track. Follow the phase plan; do not skip Phase 0.5 calibration unless the criteria allow it; run the inter-phase gate between every phase; produce the Final Report with Parity Findings."

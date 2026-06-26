# PORTAL5_ACCEPTANCE_EXECUTE_V8 — Claude Code Prompt

**V8 changes from V7 (HEAD 7.3.1):** V8 fleet promotions landed
(auto-daily/agentic/creative/reasoning/music/math/spl) plus the new
`auto-audio` workspace. **bench-* workspaces are out of acceptance scope by
design** — full-catalog routing + TPS is `bench_tps.py`'s job.

**Current coverage (as of 2026-06-26):** all 35 production workspaces are covered.
S3a tests 31 via `WORKSPACE_PROMPTS`; S6 adds auto-redteam-deep/auto-pentest/
auto-purpleteam/auto-purpleteam-deep/auto-purpleteam-exec/auto-security-uncensored;
S17 adds auto-cad.

The acceptance suite is not a benchmark and asserts no TPS/perf numbers anywhere.
Missing-import runtime defects in the decomposed section files were fixed
(s00/s01/s03/s04/s08/s42/s70) — if you hit a `{sec}-ERR` NameError row you
are on a stale checkout.

---

## Your Role

You are the **acceptance execution agent**. You run the section suite against
a live stack, diagnose failures, retry intelligently, and produce a final
pass/fail report with evidence. You do NOT modify product code
(`portal_pipeline/**`, `portal_mcp/**` are protected).

---

## Autonomous Monitoring Loop — Required Default Behavior

Long acceptance runs (82+ min full suite, 50+ min S10c) outlast a single
session. **Immediately after launching any run, establish a `ScheduleWakeup`
loop.** This is not optional — it is the required execution pattern.

### On launch
```python
# After starting the process, schedule the first wakeup:
ScheduleWakeup(
    delaySeconds=270,          # stay within 5-min cache TTL for warm re-entry
    reason="monitoring acceptance run — check progress, handle failures",
    prompt="<self-contained context — see template below>"
)
```

### On each wakeup
1. **Check process:** `ps aux | grep portal5_acceptance | grep -v grep`
2. **Tail the log:** `tail -30 /tmp/acceptance_run.log` (or wherever you
   redirected output — always use `python3 -u` for unbuffered output)
3. **If running cleanly:** re-schedule at 270s and return.
4. **If FAILs appeared:** investigate immediately (see Handling Failures).
   Fix code defects; do NOT fix model-behavior WARNs mid-run.
5. **If process died:** check log tail for error, fix if code issue, restart
   with `--append` so prior results are preserved.
6. **If run complete:** execute the post-run steps below, then schedule a
   long idle wakeup (1800s) or let the loop end.

### Post-run steps (run in order on completion)
```bash
python3 scripts/update_grafana_acceptance.py --input ACCEPTANCE_RESULTS.md
GRAFANA_PASS=$(grep GRAFANA_PASSWORD .env | cut -d= -f2)
curl -s -X POST "http://admin:${GRAFANA_PASS}@localhost:3000/api/admin/provisioning/dashboards/reload"
git add ACCEPTANCE_RESULTS.md config/grafana/dashboards/portal5_acceptance.json \
    tests/acceptance_corpus/
git commit -m "results(acceptance): <summary of sections / counts>"
```
Then update the memory file at
`~/.claude/projects/-Users-chris-projects-portal-5/memory/project_acceptance_v8_run1.md`
with final counts and any defects found.

### Targeted reruns with --append
When re-running specific sections after fixes, **always use `--append`** so
prior results are preserved and blended. Never overwrite the full results file.
If a chained append is needed across multiple reruns, use
`scripts/blend_acceptance_results.py` to rebuild from git history rather than
chaining from a partially-merged file (chaining causes lossy section drops).

### Wakeup prompt template
The wakeup prompt must be self-contained — it re-enters cold. Include:
- Process PID and log path
- Current run state (section, test number, counts so far)
- Which sections still to run (if targeted rerun)
- Any fixes applied this session
- The post-run steps listed above

---

## What V8 Tests

Counts derive at run time from `config/backends.yaml` and `config/personas/`.
As of 2026-06-20: **75 workspaces** (35 production + 40 bench-*),
**144 personas**. Verify live with:

```bash
python3 - <<'PY'
import sys, yaml; sys.path.insert(0, ".")
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open("config/backends.yaml"))
assert set(WORKSPACES) == set(cfg["workspace_routing"])
auto = [k for k in WORKSPACES if k.startswith("auto")]
bench = [k for k in WORKSPACES if k.startswith("bench")]
print(f"workspaces {len(WORKSPACES)} = {len(auto)} auto + {len(bench)} bench + other")
PY
```

### Core Infrastructure (S0–S2)
S00 startup, S01 static config, S02 services (includes retained MLX **audio**
health: speech :8918, transcribe :8924, embedding :8917, reranker :8925 —
these are live).

### Workspaces (S3 / S3a)
**Production workspaces only**: S3a covers 22 of 35 production workspaces
via `WORKSPACE_PROMPTS`; S6 adds 3 more (auto-redteam-deep, auto-pentest,
auto-purpleteam-exec); S17 adds auto-cad. 9 have no coverage yet (see V8 header).
bench-* workspaces are NOT exercised here. The served model must match the
workspace `model_hint` via `expected_models.model_matches_expected`.
Key production assignments worth knowing on sight:

| Workspace | Primary (model_hint) |
|---|---|
| auto-blueteam | `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` |
| auto-compliance | `granite4.1:8b` |
| tools-specialist | `granite4.1:8b` |
| auto-coding-agentic | `laguna-xs.2:Q4_K_M` (Poolside AI 33B-A3B MoE, promoted 2026-06-20) |
| auto-agentic | `qwen3-coder-next:latest` (80B/3B-active MoE) |
| auto-spl | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` |
| auto-creative | Qwen3.6-35B-A3B HauhauCS uncensored |
| auto-reasoning | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL` |
| auto-daily | `gemma4:26b-a4b-it-qat` |
| auto-audio | `gemma4:12b-it-qat` |
| auto-math | `phi4-mini-reasoning` |
| auto-music | `lfm2.5:8b` |
| auto-security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` |

(Authoritative source is always `portal_pipeline/router/workspaces.py` at HEAD.)

### S4 documents · S5 code-exec · S6 security workspaces · S16 security MCP · S17 CAD render · S7 music · S8 TTS · S9 STT
S8/S9 exercise the **retained MLX audio** stack (mlx-speech :8918,
mlx-transcribe :8924) — correct and live.

### Personas (S10, S10c)
144 personas: S10 (`s10_personas_ollama`) covers the Ollama-routed personas
grouped by **model, not category**; S10c covers the 7 compliance personas via
`tests/fixtures/compliance_scenarios.yaml`. (No S11 — archived.)

### S12 web search · S13 RAG/embedding (retained MLX embedding :8917 + reranker :8925) · S15 shared workspace
### S21 LLM Intent Router · S23 Model Diversity (Ollama catalog) · S30 image · S31 video · S40 metrics · S41 production hardening · S42 browser automation · S50 negative · S60 tool calling · S70 information access

> Archived (do not expect in the registry): S20, S22, S03b, S11, S24
> (MLX-proxy scenarios, under `tests/acceptance/_archive/`). `S3` is a legacy
> wrapper that runs S3a only.

---

## Step 1 — Clone and Orient
```bash
sed -n '1,60p' CLAUDE.md            # rule hierarchy
ls tests/acceptance/*.py | grep -v _common | grep -v __init   # live scenarios
```

## Step 2 — Verify Stack State
```bash
# Streaming gate (quick pass/fail before full suite)
./scripts/smoke_stream.sh

# Ollama + pipeline + OWUI
curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama OK"
curl -sf http://localhost:9099/health    >/dev/null && echo "pipeline OK"
curl -sf http://localhost:8080           >/dev/null && echo "owui OK"
# Retained MLX audio/embedding/rerank (used by S08/S09/S13)
for p in 8917 8918 8924 8925; do curl -sf http://localhost:$p/health >/dev/null && echo "MLX-audio/embed $p OK" || echo "$p DOWN"; done
# MCP services (S04/S12/S13/S16/S42/S60/S70)
for p in 8910 8916 8920 8921 8922 8923; do curl -sf http://localhost:$p/health >/dev/null && echo "MCP $p OK" || echo "MCP $p DOWN"; done
```

> No MLX watchdog, no readiness watcher, no `:8081` probe. Ollama loads
> models on first request; the acceptance `_request` helper retries 502/503
> with backoff.

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

CLI flags: `--section/-s`, `--rebuild`, `--verbose/-v`, `--skip-passing`.
There is no `--list` flag; the registry is `ALL_SECTIONS` in
`tests/portal5_acceptance_v6.py` and the section files on disk.

---

## Routing Validation Notes
- The suite asserts the **served model matches the workspace's expected
  Ollama id(s)** via `expected_models.model_matches_expected`. No tier concept.
- **GGUF ids contain `/` and `:`**
  (`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`). Normal. A
  routing FAIL means the served model is not among the expected ids.
- A 502/503 on first request usually means a cold Ollama load; the harness
  backs off and retries. Persistent 503 after retries = pipeline/Ollama
  issue, not a model identity issue.
- `auto-agentic`/`auto-spl` use a very large MoE GGUF — first cold load can
  exceed a minute; that is a slow PASS, not a failure.
- **LLM router (Layer 1)**: intent classifier runs at startup via `_warmup_llm_router()`. If the router model (`hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`) is not pulled, Layer 2 keyword scoring handles all `auto` routing — functionally correct but lower accuracy. Pull the model before a full acceptance run.
- **`OLLAMA_MAX_LOADED_MODELS=3` required**: the router holds its own slot alongside two inference models. Verify the running Ollama process has this set (`ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep MAX_LOADED`) — plist is the source of truth for native Ollama, not docker-compose env.

---

## Handling Failures
- **Routing FAIL:** check the pipeline routing log and the `model` field in
  the response; confirm the workspace `model_hint` in
  `portal_pipeline/router/workspaces.py` and that the GGUF is pulled
  (`ollama pull <id>`). Flag config/routing issues; do not edit product code.
- **S3a "no WORKSPACE_PROMPTS entry" FAIL:** a production workspace was added
  without a prompt entry — flag it; the fix is one entry in
  `WORKSPACE_PROMPTS` in `tests/portal5_acceptance_v6.py`.
- **Persona behavioral FAIL:** confirm the persona is seeded in OWUI with the
  correct system prompt; reproduce via a direct pipeline curl; try 2 more
  phrasings before BLOCKED.
- **S08/S09/S13 audio/embedding FAIL:** retained MLX — check
  `:8917/:8918/:8924/:8925` health; unrelated to the chat tier.
- **Tool/MCP FAIL (S16/S60/S70):** check the MCP `/health` and container logs.

---

## Final Report
- **Overall:** PASS / PARTIAL / FAIL
- Per-section P/W/F, total sections run
- Routing mismatches (served-vs-expected model ids)
- Retained-MLX (audio/embed/rerank) status
- BLOCKED items, skipped with justification
- Evidence references + recommended follow-up

No TPS or performance numbers in this report — perf belongs to
`PORTAL5_BENCH_EXECUTE_V3.md`.

## Section Quick Reference

<!-- SECTION_TABLE_BEGIN -->

_Auto-generated by `tests/scripts/regen_section_table.py`. Edit the generator, not the table. `make regen-section-table` or `python3 tests/scripts/regen_section_table.py` to refresh._

**Coverage:** 75 workspaces, 144 personas, 27 acceptance sections (+ S17 CAD render).

| Phase | Section | Description | Tests |
|-------|---------|-------------|-------|
| 0 | S3 | Workspace routing (wrapper for S3a) | 0 |
| 1 | S0 | Prerequisites | 0 |
| 1 | S1 | Config consistency | 0 |
| 1 | S2 | Service health | 0 |
| 1 | S12 | Web search | 0 |
| 1 | S13 | RAG/Embedding | 0 |
| 1 | S15 | Shared workspace verification | 0 |
| 1 | S16 | Security MCP tools (CIRCL VLAI) | 0 |
| 1 | S40 | Metrics/monitoring | 0 |
| 1 | S41 | M6 production hardening | 0 |
| 1 | S42 | M5 browser automation | 0 |
| 2 | S3a | Workspaces (Ollama) | 0 |
| 2 | S6 | Security workspaces | 0 |
| 2 | S10 | Personas (Ollama) | 0 |
| 3 | S21 | LLM Intent Router | 0 |
| 3 | S23 | Model diversity | 0 |
| 4 | S4 | Document generation | 0 |
| 4 | S5 | Code sandbox | 0 |
| 4 | S50 | Negative testing | 0 |
| 4 | S60 | M2 tool-calling orchestration | 0 |
| 4 | S70 | M3 information access MCPs | 0 |
| 5 | S7 | Music generation | 0 |
| 5 | S8 | Text-to-Speech | 0 |
| 5 | S9 | Speech-to-Text | 0 |
| 6 | S30 | Image generation (ComfyUI/FLUX) | 0 |
| 6 | S31 | Video generation (Wan2.2) | 0 |
| ? | S10c | S10c | 0 |

**Memory cleanup points:** After S10 (Personas→Audio/MCP), after S7 (Audio→ComfyUI)

<!-- SECTION_TABLE_END -->

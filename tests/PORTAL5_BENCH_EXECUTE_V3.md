# PORTAL5_BENCH_EXECUTE_V3 — opencode Bench Execution Prompt

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected to be running when you begin. At the end, update the
Grafana benchmarks dashboard with the results and commit them.

Current scale (verify with the dry-run plan — counts are config-driven and
drift): **78 workspaces total (35 production auto- + 43 bench-), 0 pipeline_bench_skip,
144 personas**. Speech bench workspaces (`bench-voxtral-realtime`, `bench-voxtral-tts`,
`bench-granite-speech`) were pruned in 2026-06-20 workspace cleanup — they no longer exist.
OCR workspaces (`bench-nanonets-ocr2`, `bench-olmocr2`) remain in the skip list only if
re-added; currently `pipeline_bench_skip: []`. Always confirm with `--dry-run` before a
long run — these counts drift as workspaces are added/pruned.
`bench_tps.py` is the sole TPS instrument for the platform — the
acceptance and UAT suites assert no performance numbers.

---

## Your Role

You are the **benchmark execution agent**, not the implementation agent. You
execute the bench suite, diagnose failures, adjust the run, retry
intelligently, and produce a final Grafana dashboard update. Results go to
`tests/benchmarks/results/` as a timestamped JSON file; the dashboard at
`config/grafana/dashboards/portal5_benchmarks.json` is updated from that file
when the run completes.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run
are still loaded, available, or producing similar TPS. Every run is fresh.

---

## Autonomous Monitoring Loop — Required Default Behavior

Full bench runs take 3–6 hours (~332 tests across 3 modes). **Immediately
after launching, establish a `ScheduleWakeup` loop.** This is not optional —
it is the required execution pattern for any run that exceeds a single session.

### On launch
```python
# Always launch with unbuffered output and log redirection:
# python3 -u tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10 \
#     > /tmp/bench_tps.log 2>&1 &
# After starting the process, schedule the first wakeup:
ScheduleWakeup(
    delaySeconds=270,          # stay within 5-min cache TTL for warm re-entry
    reason="monitoring bench run — check progress, handle model failures",
    prompt="<self-contained context — see template below>"
)
```

### On each wakeup
1. **Check process:** `ps aux | grep bench_tps | grep -v grep`
2. **Tail the log:** `tail -20 /tmp/bench_tps.log`
3. **Check results file:** `ls -lt tests/benchmarks/results/bench_tps_*.json | head -3`
4. **Scan for failures:** look for `available: false`, `0 TPS`, errors in the
   most recent JSON result entries.
5. **If running cleanly:** re-schedule at 270s and return.
6. **If model unavailable / 0 TPS:** see Handling Failures section; apply fix
   (model skip, retry) and re-schedule.
7. **If process died:** check for OOM (see Known Behavior Notes); restart with
   `--retry-failed` to skip completed tests.
8. **If run complete:** execute the post-run steps below.

### Post-run steps (run in order on completion)
```bash
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 scripts/update_grafana_benchmarks.py --input "$RESULTS"
GRAFANA_PASS=$(grep GRAFANA_PASSWORD .env | cut -d= -f2)
curl -s -X POST "http://admin:${GRAFANA_PASS}@localhost:3000/api/admin/provisioning/dashboards/reload"
git add "$RESULTS" config/grafana/dashboards/portal5_benchmarks.json && \
    git commit -m "bench: TPS baseline $(date -u +%Y-%m-%d)"
```

### Wakeup prompt template
The wakeup prompt must be self-contained — it re-enters cold. Include:
- Process PID and log path (always use `python3 -u` for unbuffered output)
- Most recent result file path and last model tested
- Run flags used (`--mode`, `--order`, `--runs`, etc.)
- Any model skips or fixes applied this session
- The post-run steps listed above

---

## What Gets Benchmarked

Counts derive at run time from `config/backends.yaml` and `config/personas/`.
Confirm with the dry-run before committing to a long run:

| Dimension | Count |
|---|---|
| Ollama catalog models | verify via `--dry-run` |
| Pipeline workspaces total | 78 (35 auto- + 43 bench-) |
| pipeline_bench_skip | 0 |
| Personas | 144 |
| **Total tests (mode=all)** | **verify via `--dry-run`** |

### Three test modes (run together with `--mode all`):

**1. Direct backends** — calls **Ollama (:11434)** directly, every catalog
model. Each model: **warmup → N runs → unload (`/api/ps` + `keep_alive:0`) →
memory-pressure check (`vm_stat`) → cooldown.** Sequential only — never two
models resident at once on the single-GPU box.

**2. Pipeline workspaces** — calls portal-pipeline (:9099) per workspace ID.
Tests routing, model dispatch, and end-to-end TPS. Prompt categories (7:
general, coding, security, reasoning, creative, vision, math) map per
workspace:

| Auto workspaces | Category |
|---|---|---|
| auto, auto-daily | general |
| auto-coding, auto-agentic, auto-coding-agentic, auto-spl, auto-cad, auto-documents, auto-phi4 | coding |
| auto-security, auto-redteam, auto-redteam-deep, auto-blueteam, auto-purpleteam, auto-purpleteam-deep, auto-purpleteam-exec, auto-pentest, auto-bigfix | security |
| auto-reasoning, auto-research, auto-data, auto-compliance, auto-mistral | reasoning |
| auto-math | math |
| auto-creative, auto-video, auto-music | creative |
| auto-vision, auto-audio | vision |
| tools-specialist | coding (granite4.1:8b tool-calling) |

Bench workspace categories derive the same way from `backends.yaml` groups;
the dry-run plan prints the full resolved mapping.

**3. Persona routing** — calls portal-pipeline (:9099) per persona
`workspace_model`.

> Production primaries worth knowing on sight: `auto-blueteam` →
> Foundation-Sec-8B-Reasoning (`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`);
> `auto-compliance` and `tools-specialist` → `granite4.1:8b`; `auto-agentic` →
> `qwen3-coder-next:latest` (MoE — slow cold load is normal); `auto-coding-agentic` →
> `laguna-xs.2:Q4_K_M` (Poolside AI 33B-A3B MoE, opencode/Claude Code default);
> `auto-creative` → `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`.
> Authoritative source: `portal_pipeline/router/workspaces.py`.

---

## Standard Command

```bash
# Full baseline: all three modes, smallest models first, 5 runs each, 10s cooldown
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10
```

---

## Pre-Flight Checklist

### 1. Stack health
```bash
curl -sf http://localhost:11434/api/tags | python3 -m json.tool | head   # Ollama
curl -sf http://localhost:9099/health | python3 -m json.tool             # Pipeline
```

### 2. Image freshness (stale images = false failures)
```bash
docker images --format "table {{.Repository}}\t{{.CreatedAt}}" | grep portal
# If any portal image predates a recent commit, rebuild before benching.
./launch.sh rebuild
```

### 3. Workspace consistency (Rule 6)
```bash
python3 - <<'PY'
import sys, yaml; sys.path.insert(0, ".")
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open("config/backends.yaml"))
assert set(WORKSPACES) == set(cfg["workspace_routing"]), "WORKSPACES vs workspace_routing mismatch"
print("Rule 6 OK:", len(WORKSPACES), "workspaces")
PY
```

### 4. Dry-run plan (confirm counts before committing to a long run)
```bash
python3 tests/benchmarks/bench_tps.py --mode all --dry-run
# Prints: Ollama models, Workspaces, Personas, Total to test. Sanity-check
# against the table above; investigate any large delta before running.
```

### 5. Skip mechanism reference
`pipeline_bench_skip` in `backends.yaml` is currently `[]` — nothing is skipped.
OCR and speech bench workspaces were pruned in the 2026-06-20 cleanup and no longer exist.
If any workspace is re-added to `pipeline_bench_skip`, an explicit `--workspace <id>` filter
overrides the skip (operator wants to probe it intentionally).

### 6. No MLX watchdog
There is no MLX proxy or watchdog for inference. Ollama manages its own
model lifecycle; the harness handles eviction between models via
`keep_alive:0`.

---

## Execution

```bash
# Default output filename is auto-generated as bench_tps_<timestamp>.json
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10

# Or specify an explicit output path:
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10 \
  --output tests/benchmarks/results/bench_tps_$(date -u +%Y%m%dT%H%M%SZ).json
```

### Memory management (automatic)
The harness unloads each Ollama model with `keep_alive:0` after its runs and
polls `/api/ps` until no model is resident, then checks `vm_stat` pressure
before loading the next. `--cooldown N` adds settle time after reclaim. If a
large GGUF (30B+ dense or large MoE) leaves elevated pressure, the harness
waits for the VM pager before proceeding.

---

## Monitoring Progress

```bash
ls -lt tests/benchmarks/results/bench_tps_*.json | head -5
# Get TPS count from the latest results file:
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "import json; d=json.load(open('$RESULTS')); print(len([r for r in d.get('results',[]) if r.get('tps')]))"
```

---

## Handling Failures

### Model unavailable (0 TPS, `available: false`)
The GGUF isn't pulled. `ollama pull <id>` then retry that model with
`--model <substring>`. Report as unavailable if the pull fails.

### Model produces 0 TPS with `available: true`
Likely an eviction/memory issue or a cold-load timeout. Confirm nothing else
is resident (`curl -s :11434/api/ps`), unload (`keep_alive:0`), wait for
`vm_stat` to settle, then re-run that single model. The qwen3-coder-next MoE
cold load is the slowest in the fleet — distinguish slow from dead before
declaring failure.

### Resume after interruption / retry all failures
```bash
# Resumes from the most recent bench_tps_*.json results file, skipping successful entries.
python3 tests/benchmarks/bench_tps.py --mode all --retry-failed
# Pair with --mode to scope (e.g. --mode pipeline --retry-failed).
```

### Test update required (workspace/persona consistently fails)
A routing or persona-seed issue, not a model issue — flag it; do not modify
product code (`portal_pipeline/**` is protected).

### Filter to a single model / workspace / persona
```bash
python3 tests/benchmarks/bench_tps.py --mode direct  --model foundation-sec
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto-blueteam
python3 tests/benchmarks/bench_tps.py --mode personas --persona bench-laguna
# Force-probe a skipped OCR workspace (explicit --workspace overrides skip):
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-nanonets-ocr2
```

---

## Validation After Run

```bash
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "
import json; d=json.load(open('$RESULTS'))
r=d['results']; print('total', len(r), '| with TPS', len([x for x in r if x.get('tps')]), '| unavailable', len([x for x in r if not x.get('available', True)]))
"
# Routing accuracy (pipeline mode): served model should match the workspace
# model_hint (expected_model_match flag in the JSON). GGUF ids contain '/'
# and ':' — normal, not a mismatch.
```

---

## Updating the Grafana Dashboard
```bash
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 scripts/update_grafana_benchmarks.py --input "$RESULTS"
GRAFANA_PASS=$(grep GRAFANA_PASSWORD .env | cut -d= -f2)
curl -s -X POST "http://admin:${GRAFANA_PASS}@localhost:3000/api/admin/provisioning/dashboards/reload"
git add "$RESULTS" config/grafana/dashboards/portal5_benchmarks.json && \
    git commit -m "bench: TPS baseline $(date -u +%Y-%m-%d)"
```

---

## Key Parameters Reference
| Flag | Default | Meaning |
|---|---|---|
| `--mode` | all | `direct` (Ollama) / `pipeline` / `personas` / `all` |
| `--order` | size | `size` (smallest first) / `largest` (biggest first) / `config` (backends.yaml order) |
| `--runs` | 5 | inference runs per model/workspace |
| `--cooldown` | 10 | seconds after reclaim before next load |
| `--model` | — | substring filter (direct only) |
| `--workspace` | — | exact workspace id (pipeline only; overrides skip) |
| `--persona` | — | substring filter (personas only) |
| `--prompt` | — | override all prompts with a single prompt string |
| `--retry-failed` | off | resume from most recent results file; re-test failures only |
| `--dry-run` | off | print plan, don't execute |
| `--spec-decoding-tag` | "" | label run for spec-decoding A/B comparison |
| `--kv-quant-tag` | "" | label run for KV-quant A/B comparison |

---

## Known Behavior Notes
- **20 TPS usability floor** is the hard line; flag any workspace primary below it.
- Reasoning models (Foundation-Sec, DeepSeek-R1 variants, Magistral,
  phi4-mini-reasoning, olmo-3.1-think) emit `<think>` and get a higher token
  budget so their TPS is comparable to non-reasoning models.
- GGUF model ids legitimately contain `/` and `:`. Not an anomaly.
- Sequential-only: the harness never loads two models at once. If you see two
  resident in `/api/ps`, eviction lagged — wait and re-run.
- **PROMOTE_POLICY:** bench results never auto-promote anything. Workspace
  primary changes are operator-only decisions via a separate promotion task.

## Final Deliverables
1. Timestamped result JSON in `tests/benchmarks/results/`.
2. Updated + reloaded Grafana benchmarks dashboard.
3. A short summary: models tested, any below the 20 TPS floor, any
   unavailable, any routing mismatches. Recommendations only — no promotions.

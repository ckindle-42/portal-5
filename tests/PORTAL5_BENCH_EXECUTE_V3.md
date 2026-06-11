# PORTAL5_BENCH_EXECUTE_V3 — Claude Code Prompt

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected to be running when you begin. At the end, update the
Grafana benchmarks dashboard with the results and reload it.

**V3 changes from V2 (HEAD 7.3.1):** the V8 catalog refresh + promotions
landed. Current scale (verify with the dry-run plan — counts are
config-driven and drift): **68 unique Ollama catalog models, 69 benchable
workspaces (74 total − 5 pipeline_bench_skip), 140 personas, ~277 total tests
at `--mode all`**. The skip list is exactly five non-text-modality workspaces:
`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech` (audio)
plus `bench-nanonets-ocr2`, `bench-olmocr2` (OCR vision — image-input probe
required). `bench-nemotron-omni` no longer exists (placeholder removed). New
flags since V2: `--retry-failed` (resume from the most recent results file,
re-testing only failures) and `--order largest`. **bench_tps.py is the sole
TPS instrument for the platform** — the acceptance and UAT suites assert no
performance numbers.

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

## What Gets Benchmarked

Counts derive at run time from `config/backends.yaml` and `config/personas/`.
Confirm with the dry-run before committing to a long run:

| Dimension | Count (7.3.1) |
|---|---|
| Unique Ollama catalog models | 68 |
| Benchable pipeline workspaces | 69 (74 total − 5 skip) |
| Personas | 140 |
| **Total tests (mode=all)** | **~277** |

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
|---|---|
| auto, auto-daily | general |
| auto-coding, auto-agentic, auto-spl, auto-documents | coding |
| auto-security, auto-redteam, auto-blueteam | security |
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
> Foundation-Sec-8B-Reasoning
> (`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`);
> `auto-compliance` and `tools-specialist` → `granite4.1:8b`; `auto-agentic`
> → `qwen3-coder-next` (80B/3B-active MoE — slow cold load is normal);
> `auto-creative` → Qwen3.6-35B-A3B HauhauCS. Authoritative source:
> `portal_pipeline/router/workspaces.py`.

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
docker compose -f deploy/portal-5/docker-compose.yml ps
# If the pipeline image is older than the last code change, rebuild before benching.
```

### 3. Workspace consistency (CLAUDE.md Rule 6)
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
Non-text-modality bench workspaces carry entries in the top-level
`pipeline_bench_skip:` list in `backends.yaml` (currently exactly five:
`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`,
`bench-nanonets-ocr2`, `bench-olmocr2`). An explicit `--workspace <id>`
filter overrides the skip (operator wants to probe that workspace
intentionally). Speech benches belong to the deferred audio-prompt driver
(P5-FUT-SPEECH-002); OCR benches need an image-input probe — neither is
bench_tps.py's job.

### 6. No MLX watchdog
There is no MLX proxy or watchdog. Ollama manages its own model lifecycle;
the harness handles eviction between models via `keep_alive:0`.

---

## Execution

```bash
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10 \
  --output tests/benchmarks/results/bench_${RUN_TS}.json
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
ls -la tests/benchmarks/results/ | tail -3
python3 -c "import json; d=json.load(open('tests/benchmarks/results/bench_${RUN_TS}.json')); print(len([r for r in d.get('results',[]) if r.get('tps')]))"
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
python3 tests/benchmarks/bench_tps.py --mode all --retry-failed
# Resumes from the most recent results file, skipping successful entries.
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
# Force-probe a skipped speech workspace (explicit --workspace overrides skip):
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-voxtral-realtime
```

---

## Validation After Run

```bash
python3 -c "
import json; d=json.load(open('tests/benchmarks/results/bench_${RUN_TS}.json'))
r=d['results']; print('total', len(r), '| with TPS', len([x for x in r if x.get('tps')]), '| unavailable', len([x for x in r if not x.get('available', True)]))
"
# Routing accuracy (pipeline mode): served model should match the workspace
# model_hint (expected_model_match flag in the JSON). GGUF ids contain '/'
# and ':' — normal, not a mismatch.
```

---

## Updating the Grafana Dashboard
```bash
# Update config/grafana/dashboards/portal5_benchmarks.json from the result JSON, then:
curl -s -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload \
  -H "Authorization: Bearer $GRAFANA_TOKEN" || echo "reload via UI if API unavailable"
git add config/grafana/dashboards/portal5_benchmarks.json && \
  git commit -m "bench: TPS results @ ${RUN_TS}"
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

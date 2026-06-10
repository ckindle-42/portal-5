# PORTAL5_BENCH_EXECUTE_V2 — Claude Code Prompt

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live stack is expected to be running when you begin. At the end, update the Grafana benchmarks dashboard with the results and reload it.

**V2 change from V1:** the MLX inference proxy was retired (commit 3a0c58e). All chat inference now runs through **Ollama (:11434)**; there is one backend tier, not two. `--mode direct` means "Ollama backends direct." MLX is retained only for audio/speech/embedding/rerank and is NOT exercised by this text-prompt bench (speech-modality bench workspaces are skipped via config).

---

## Your Role

You are the **benchmark execution agent**, not the implementation agent. You execute the bench suite, diagnose failures, adjust the run, retry intelligently, and produce a final Grafana dashboard update. Results go to `tests/benchmarks/results/` as a timestamped JSON file; the dashboard at `config/grafana/dashboards/portal5_benchmarks.json` is updated from that file when the run completes.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run are still loaded, available, or producing similar TPS. Every run is fresh.

---

## What Gets Benchmarked

Counts are derived at run time from `config/backends.yaml` and `config/personas/`. The current catalog (verify with the dry-run plan below) is approximately:

| Dimension | Count |
|---|---|
| Ollama catalog models | ~48 |
| Pipeline workspaces | ~56 (18 auto-* + 36 bench-* + 2 other: `auto`, `tools-specialist`) |
| Personas | ~122 |
| **Total tests (mode=all)** | **~217** |

Speech/vision-modality bench workspaces (`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`, `bench-nemotron-omni`, OCR benches) cannot be meaningfully exercised by a text-prompt harness and are skipped via config (`bench_skip` / `pipeline_bench_skip`). The skip is config-driven; no operator flag needed. The retained MLX audio/embedding/rerank services are not part of the TPS bench.

### Three test modes (run together with `--mode all`):

**1. Direct backends** — calls **Ollama (:11434)** directly, every catalog model. Each model follows a strict cycle: **warmup → test N runs → unload (`/api/ps` + `keep_alive:0`) → memory-pressure check (`vm_stat`) → cooldown.** Sequential only — never two models resident at once on the single-GPU box. This prevents unified-memory accumulation that causes Metal OOM under back-to-back large-model loads.

**2. Pipeline workspaces** — calls portal-pipeline (:9099) per workspace ID. Tests routing, model dispatch, and end-to-end TPS. Workspace → prompt category mapping:

| Auto workspaces | Category |
|---|---|
| auto, auto-daily | general |
| auto-coding, auto-agentic, auto-spl, auto-documents | coding |
| auto-security, auto-redteam, auto-blueteam | security |
| auto-reasoning, auto-research, auto-data, auto-compliance, auto-mistral, auto-math | reasoning |
| auto-creative, auto-video, auto-music | creative |
| auto-vision | vision |
| tools-specialist | coding (Granite-4.1 8B tool-calling) |

Bench workspace categories are derived the same way from `backends.yaml` groups; the dry-run plan prints the full resolved mapping.

**3. Persona routing** — calls portal-pipeline (:9099) per persona `workspace_model`.

> Note: `auto-blueteam` now serves **Foundation-Sec-8B-Reasoning** (`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`), restored as the production blue-team primary. `tools-specialist` serves `granite4.1:8b`. Both are Ollama GGUFs.

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
PIPELINE_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2) python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg=yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES)==set(cfg['workspace_routing']), 'WORKSPACES vs workspace_routing mismatch'
print('Rule 6 OK:', len(WORKSPACES), 'workspaces')
"
```

### 4. Dry-run plan (confirm counts before committing to a long run)
```bash
python3 tests/benchmarks/bench_tps.py --mode all --dry-run
# Prints: Ollama models, Workspaces, Personas, Total to test. Sanity-check against the catalog.
```

### 5. Skip mechanism reference
Speech/vision bench workspaces and models carry `bench_skip: true` / `pipeline_bench_skip` in `backends.yaml`. To force-probe one anyway, pass `--workspace <id>` (explicit filter overrides the skip list).

### 6. No MLX watchdog
There is no MLX proxy or watchdog to stop. Ollama manages its own model lifecycle; the bench harness handles eviction between models via `keep_alive:0`.

---

## Execution

```bash
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10 \
  --output tests/benchmarks/results/bench_${RUN_TS}.json
```

### Memory management (automatic)
The harness unloads each Ollama model with `keep_alive:0` after its runs and polls `/api/ps` until no model is resident, then checks `vm_stat` pressure before loading the next. `--cooldown N` adds settle time after reclaim. If a large GGUF (30–70B) leaves elevated pressure, the harness waits for the VM pager before proceeding. No proxy restart, no `mlx_lm`/`mlx_vlm` server management.

---

## Monitoring Progress

```bash
# Live tail
tail -f tests/benchmarks/results/bench_${RUN_TS}.json 2>/dev/null || \
  ls -la tests/benchmarks/results/ | tail -3
# Models with TPS data so far
python3 -c "import json,sys; d=json.load(open('tests/benchmarks/results/bench_${RUN_TS}.json')); print(len([r for r in d.get('results',[]) if r.get('tps')]))"
```

---

## Handling Failures

### Model unavailable (0 TPS, `available: false`)
The GGUF isn't pulled. `ollama pull <id>` then retry that model with `--model <substring>`. Report as unavailable if the pull fails.

### Model produces 0 TPS with `available: true`
Likely an eviction/memory issue or a cold-load timeout. Confirm nothing else is resident (`curl -s :11434/api/ps`), unload (`keep_alive:0`), wait for `vm_stat` to settle, then re-run that single model.

### Test update required (workspace/persona consistently fails)
A routing or persona-seed issue, not a model issue — flag it; do not modify product code (`portal_pipeline/**` is protected).

### Retry failed tests only
```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace <id> --runs 5
```

### Filter to a single model / workspace / persona
```bash
python3 tests/benchmarks/bench_tps.py --mode direct  --model foundation-sec   # one Ollama model
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto-blueteam
python3 tests/benchmarks/bench_tps.py --mode personas --persona bench-laguna
# Force-probe a skipped speech workspace (explicit --workspace overrides skip):
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-voxtral-realtime
```

---

## Validation After Run

```bash
# Result counts
python3 -c "
import json; d=json.load(open('tests/benchmarks/results/bench_${RUN_TS}.json'))
r=d['results']; print('total', len(r), '| with TPS', len([x for x in r if x.get('tps')]), '| unavailable', len([x for x in r if not x.get('available', True)]))
"
# Routing accuracy (pipeline mode): the served model should match the workspace model_hint.
# GGUF ids contain '/' and ':' (e.g. hf.co/fdtn-ai/...:Q8_0) — that is normal, not a tier mismatch.
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
| `--mode` | (required) | `direct` (Ollama) / `pipeline` / `personas` / `all` |
| `--order` | size | `size` (smallest first) or `config` |
| `--runs` | 5 | inference runs per model/workspace |
| `--cooldown` | 10 | seconds after reclaim before next load |
| `--model` | — | substring filter (direct only) |
| `--workspace` | — | exact workspace id (pipeline only; overrides skip) |
| `--persona` | — | substring filter (personas only) |
| `--dry-run` | off | print plan, don't execute |

---

## Known Behavior Notes
- **20 TPS usability floor** is the hard line; flag any workspace primary below it.
- Reasoning models (Foundation-Sec, Phi-4-reasoning, Magistral, Qwopus, Apriel) emit `<think>` and get a higher token budget so their TPS is comparable to non-reasoning models.
- GGUF model ids legitimately contain `/` and `:`. Do not treat that as an anomaly.
- Sequential-only: the harness never loads two models at once. If you see two resident in `/api/ps`, eviction lagged — wait and re-run.

## Final Deliverables
1. Timestamped result JSON in `tests/benchmarks/results/`.
2. Updated + reloaded Grafana benchmarks dashboard.
3. A short summary: models tested, any below the 20 TPS floor, any unavailable, any routing mismatches.

# PORTAL5_BENCH_EXECUTE_V1 — Claude Code Prompt

Run the Portal 5 comprehensive TPS benchmark suite. The live stack is expected to be running when you begin. At the end, update the Grafana benchmarks dashboard with the results and reload it.

---

## Your Role

You are the **benchmark execution agent**, not the implementation agent. You execute the bench suite, diagnose failures, adjust the test run, retry intelligently, and produce a final Grafana dashboard update. Results go to `tests/benchmarks/results/` as a timestamped JSON file, and the Grafana dashboard at `config/grafana/dashboards/portal5_benchmarks.json` is updated from that file when the run completes.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run are still loaded, still available, or still producing similar TPS numbers. Every run is fresh.

---

## What Gets Benchmarked

Counts are derived at run time from `config/backends.yaml` and
`config/personas/`. The current catalog (HEAD, 56eefd0, 2026-05-27) is:

| Tier | Count |
|---|---|
| MLX models (T1) | 49 (46 benched, 3 skipped via `bench_skip: true`) |
| Ollama models (T2) | 27 |
| Pipeline workspaces | 50 (19 auto-* + 30 bench-* + 1 tools-specialist; 3 bench-* skipped via `pipeline_bench_skip`) |
| Personas | 116 |
| **Total tests** | **~236** |

The skipped MLX entries and skipped workspaces are speech-modality models
that cannot be meaningfully exercised by the text-prompt bench harness —
see TASK_SPEECH_SHOOTOUT_V1 (deferred). The skip is config-driven; no
operator flag needed.

### Three test modes (run together with `--mode all`):

**1. Direct backends** — calls MLX proxy (:8081) and Ollama (:11434) directly. Each MLX model follows: load → test N runs → evict → memory reclaim → cooldown.

**2. Pipeline workspaces** — calls portal-pipeline (:9099) per workspace ID. Tests routing, model dispatch, and end-to-end TPS. Workspace → prompt category mapping:

| Auto workspaces | Category |
|---|---|
| auto | general |
| auto-coding, auto-agentic, auto-spl, auto-documents | coding |
| auto-security, auto-redteam, auto-blueteam | security |
| auto-reasoning, auto-research, auto-data, auto-compliance, auto-mistral, auto-math | reasoning |
| auto-creative, auto-video, auto-music | creative |
| auto-vision | vision |
| auto-daily | general |
| tools-specialist | coding | ToolACE-2.5-Llama-3.1-8B MLX (production tool-calling specialist) |

| Bench workspaces | Category | Model |
|---|---|---|
| bench-devstral | coding | Devstral-Small-2507 MLX |
| bench-qwen3-coder-next | coding | Qwen3-Coder-Next MLX |
| bench-qwen3-coder-30b | coding | Qwen3-Coder-30B MLX |
| bench-llama33-70b | coding | Llama-3.3-70B MLX |
| bench-glm | coding | GLM-4.7-Flash MLX |
| bench-granite41-8b | coding | granite-4.1-3b/8b MLX |
| bench-granite41-30b | coding | granite-4.1-30b MLX |
| bench-qwen36-27b | coding | Qwen3.6-27B MLX (dense) |
| bench-qwen36-35b-a3b | coding | Qwen3.6-35B-A3B MLX (MoE) |
| bench-omnicoder2 | coding | omnicoder2:9b Ollama |
| bench-phi4 | reasoning | phi-4-8bit MLX |
| bench-phi4-reasoning | reasoning | Phi-4-reasoning-plus MLX |
| bench-laguna | reasoning | Laguna-XS.2 MLX |
| bench-gptoss | reasoning | gpt-oss:20b Ollama |
| bench-negentropy | reasoning | Negentropy-9B MLX |
| bench-olmo3-32b | reasoning | Olmo-3-1125-32B MLX |
| bench-dolphin8b | creative | dolphin-llama3:8b Ollama |
| bench-qwen35-abliterated | general | qwen3.5-abliterated:9b Ollama |
| bench-nemotron-omni | vision | Nemotron-3-Nano-Omni-30B-A3B MLX (mlx-vlm) |
| bench-olmocr2 | vision | olmOCR-2-7B MLX |
| bench-nanonets-ocr2 | vision | Nanonets-OCR2-3B MLX |
| bench-lfm2-moe | creative | LFM2-8B-A1B MLX (MoE) |
| bench-foundation-sec | reasoning | Foundation-Sec-8B-Reasoning MLX |
| bench-toolace25 | tools | ToolACE-2.5-Llama-3.1-8B MLX |
| bench-apriel-nemotron | reasoning | Apriel-Nemotron-15B-Thinker-8bit MLX (ServiceNow+NVIDIA) |
| bench-qwen36-27b-ud | coding | unsloth/Qwen3.6-27B-UD-MLX-4bit (Unsloth Dynamic 2.0 probe) |
| bench-qwen36-35b-a3b-ud | coding | unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit (Unsloth Dynamic 2.0 probe) |
| bench-voxtral-realtime | (skipped — speech) | Voxtral-Mini-4B-Realtime-2602-4bit MLX |
| bench-voxtral-tts | (skipped — speech) | Voxtral-4B-TTS-2603-mlx-6bit MLX |
| bench-granite-speech | (skipped — speech) | granite-speech-4.1-2b MLX |

> Historical note: `bench-llama4-scout` (Llama-4-Scout-17B MLX) was removed
> at HEAD by commit `9c657b3` after 57 GB Metal OOM crashes on M4 Pro.
> Do not re-add without a hardware-tier change.

**3. Persona routing** — calls pipeline per persona, validates workspace routing, captures `routed_model` and `expected_model_match`.

---

## Standard Command

```bash
python3 tests/benchmarks/bench_tps.py \
    --mode all \
    --order size \
    --runs 5 \
    --cooldown 10
```

- `--order size` — smallest models first; each load/evict cycle builds the inactive memory pool, so the largest models (46GB Qwen3-Coder-Next) have enough free+inactive+purgeable available when they run last
- `--runs 5` — 5 inference runs per model/workspace for stable averages
- `--cooldown 10` — 10s after memory reclaim for Metal buffers to settle

Output is written to `tests/benchmarks/results/bench_tps_<timestamp>Z.json` incrementally (each result appended as it completes).

---

## Pre-Flight Checklist

Before launching the bench, verify:

### 1. Stack health
```bash
./launch.sh status
curl -sf http://localhost:9099/health && echo "pipeline OK"
curl -sf http://localhost:8081/health | python3 -m json.tool | head -5
curl -sf http://localhost:11434/api/tags | python3 -m json.tool | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Ollama: {len(d[\"models\"])} models')"
```

### 2. Image freshness (stale images = false failures)
```bash
docker images --format "table {{.Repository}}\t{{.CreatedAt}}" | grep portal
git log --oneline --format="%h %ai %s" -5
```
If any portal image predates a `portal_pipeline/` or `config/` commit, rebuild first:
```bash
./launch.sh rebuild
```

### 3. Workspace consistency
```bash
python3 -c "
import yaml
import sys; sys.path.insert(0, '.')
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
mismatch = (pipe_ids - yaml_ids) | (yaml_ids - pipe_ids)
assert not mismatch, f'Mismatch: {mismatch}'
print(f'Workspace IDs consistent ({len(pipe_ids)} total)')
"
```

### 4. Dry-run plan
```bash
python3 tests/benchmarks/bench_tps.py --mode all --order size --dry-run 2>&1 | head -30
```
Expected output (V7 post-merge):
```
MLX models:    46 (3 skipped via bench_skip)
Ollama models: 27
Workspaces:    47 (3 skipped via pipeline_bench_skip)
Personas:      116
Total to test: ~236 (mode=all)
```
If counts differ significantly, investigate before proceeding (new models/personas added to config but not yet seeded, or WORKSPACE_PROMPT_MAP out of date).

### 5. Skip mechanism reference

Two independent skip mechanisms prevent inappropriate models/workspaces from being benchmarked:

**Model-level skip** (`bench_skip: true` in `config/backends.yaml` mlx_models entries)
- Skips the model in **direct** mode (no raw TPS measurement for that model)
- Used for models that require audio input and cannot be exercised with text prompts
- Currently flagged: `granite-speech-4.1-2b`, `Voxtral-4B-TTS-2603-mlx-6bit`, `Voxtral-Mini-4B-Realtime-2602-4bit`

**Workspace-level skip** (`pipeline_bench_skip:` list in `config/backends.yaml`)
- Skips the workspace in **pipeline** mode (the workspace is excluded from `_config_workspaces()`)
- An explicit `--workspace <name>` argument bypasses this skip for targeted manual probes
- Currently listed: `bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`

To add a new workspace to the skip list, append its ID to `pipeline_bench_skip:` in `config/backends.yaml`. The corresponding unit test (`tests/unit/test_bench_skip.py::test_real_backends_yaml_has_consistent_skip_list`) will catch typos.

### 6. MLX watchdog
The benchmark script automatically creates `/tmp/mlx-watchdog-paused` at startup (puts watchdog in monitor-only mode) and removes it on exit. No manual action required.

---

## Execution

Launch the full run (expect 4-8 hours wall time for --mode all with 46 MLX models):

```bash
python3 tests/benchmarks/bench_tps.py \
    --mode all \
    --order size \
    --runs 5 \
    --cooldown 10 \
    2>&1 | tee /tmp/bench_tps_run.log
```

Track progress live in another terminal (log watcher — shows each model result as it completes):
```bash
tail -f /tmp/bench_tps_run.log | grep -E "^\s+\[|t/s|FAIL|SKIP|evict|reclaim|⚠|──"
```

### Memory management (automatic)
Each MLX model follows this cycle automatically:
1. **Load** — proxy warms the model (10-120s for small, 30-300s for 70B+)
2. **Test** — N inference runs with category-appropriate prompt
3. **Evict** — Ollama routing model flushed, 3B canary loaded to push large model out
4. **Reclaim** — polls proxy `/health` until `free + inactive >= next_model + 10GB`
5. **Cooldown** — sleeps `--cooldown` seconds for Metal buffers to fully settle

Do NOT kill `mlx_lm.server` or `mlx_vlm.server` processes during a run. Use the proxy's SIGTERM path via the bench script's Ctrl-C handler if you need to abort.

---

## Monitoring Progress

### Live tail (log watcher — follow new lines as they arrive)
```bash
tail -f /tmp/bench_tps_run.log | grep -E "^\s+\[|t/s|FAIL|SKIP|evict|reclaim|⚠|──"
```

Typical output lines to expect:
- `    [7/46] Qwen3-Coder-30B (20GB) (warm-up) 42.1 t/s  (5/5 ok)` — model result
- `    evict → reclaim (30s cooldown) ... ok` — eviction cycle
- `    [8/46] Devstral-Small (16GB) SKIP (already done)` — resume skip
- `  ⚠ HIGH JITTER: cv=0.18 ...` — unstable run warning

### Current output file size
```bash
ls -lh tests/benchmarks/results/bench_tps_*.json | tail -3
```

### Results so far (models with TPS data)
```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$LATEST').read_text())
results = data.get('results', [])
direct = [r for r in results if r.get('path') == 'direct' and r.get('avg_tps', 0) > 0]
print(f'Direct done: {len(direct)}, avg TPS: {sum(r[\"avg_tps\"] for r in direct)/max(len(direct),1):.1f}')
pipe = [r for r in results if r.get('path') == 'pipeline' and r.get('avg_tps', 0) > 0]
print(f'Pipeline done: {len(pipe)}')
persona = [r for r in results if r.get('path') == 'persona' and r.get('avg_tps', 0) > 0]
print(f'Personas done: {len(persona)}')
"
```

---

## Handling Failures

### Model unavailable (0 TPS, `available: false`)
Normal for MLX models not yet downloaded or Ollama models not pulled. These are reported in the results with `available: false`. No action needed — the run continues automatically.

### Model produces 0 TPS with `available: true`
Indicates a backend error. Check the proxy log:
```bash
docker logs portal5-pipeline --tail 50 2>&1 | grep -E "ERROR|timeout|refused"
```
Common causes:
- **MLX proxy crashed**: check `ps aux | grep mlx_lm` and restart if needed with `./launch.sh mlx-start`
- **Ollama OOM**: check `./launch.sh ollama-status` and the model size vs available memory
- **Admission control block**: 70B+ models need 40GB+ free; check `curl -s http://localhost:8081/health | python3 -m json.tool`

### Test update required (workspace/persona consistently fails)
If a workspace or persona returns 0 TPS due to a routing issue (wrong model assigned, workspace not seeded in Open WebUI), check:
1. Is the workspace in the Open WebUI database? `./launch.sh owui-seed`
2. Is the backing model available? Check backends.yaml and Ollama/MLX status.

### Retry failed tests only
After a partial run, resume without re-running successful tests:
```bash
python3 tests/benchmarks/bench_tps.py \
    --mode all \
    --order size \
    --runs 5 \
    --cooldown 10 \
    --retry-failed
```
This automatically picks the most recent results file and skips entries with `runs_success > 0`.

### Filter to a single model or workspace
```bash
# Retest one MLX model
python3 tests/benchmarks/bench_tps.py --mode direct --model Laguna-XS.2 --runs 3

# Retest one workspace
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-qwen3-coder-next --runs 3

# Force-probe a speech workspace (pipeline_bench_skip bypass — explicit --workspace overrides skip list)
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-voxtral-realtime --runs 1

# Retest one persona
python3 tests/benchmarks/bench_tps.py --mode personas --persona cybersecurity --runs 3
```

---

## Validation After Run

### Check result counts
```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$LATEST').read_text())
results = data.get('results', [])
by_path = {}
for r in results:
    m = r.get('path', 'unknown')
    by_path[m] = by_path.get(m, 0) + 1
print('Results by path:', by_path)
failed = [r for r in results if r.get('avg_tps', 0) == 0 and r.get('available', True)]
print(f'Unexpected failures (available=True, TPS=0): {len(failed)}')
for r in failed[:10]:
    print(f'  {r.get(\"path\", \"?\")} / {r.get(\"model\", r.get(\"workspace\", \"?\"))} / {r.get(\"runs\", [])}')
"
```

### Validate routing accuracy (pipeline mode)
```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$LATEST').read_text())
results = data.get('results', [])
pipe = [r for r in results if r.get('path') == 'pipeline']
mismatch = [r for r in pipe if r.get('expected_model_match') is False]
if mismatch:
    print(f'WARNING: {len(mismatch)} workspaces routed to wrong model:')
    for r in mismatch:
        print(f'  {r[\"workspace\"]}: expected={r.get(\"expected_model_detail\")}, got={r.get(\"routed_model\")}')
else:
    print(f'Routing OK: all {len(pipe)} pipeline tests matched expected model')
"
```

---

## Updating the Grafana Dashboard

After a successful run, update the Grafana benchmarks dashboard from the results:

```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
echo "Updating dashboard from: $LATEST"

python3 scripts/update_grafana_benchmarks.py --input "$LATEST"
```

Dry-run to preview without writing:
```bash
python3 scripts/update_grafana_benchmarks.py --input "$LATEST" --dry-run
```

The script updates `config/grafana/dashboards/portal5_benchmarks.json` in-place.

### Reload Grafana to pick up the new dashboard JSON

Grafana loads provisioned dashboards from the mounted `config/grafana/dashboards/` directory. Reloading dashboards via the API is sufficient — no container restart needed:

```bash
# Reload provisioned dashboards via API
curl -s -u admin:admin -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload
echo ""
echo "Dashboard reload triggered"
```

If the API returns a 401, check the Grafana admin password in `.env` (`GF_SECURITY_ADMIN_PASSWORD`):
```bash
PASS=$(grep GF_SECURITY_ADMIN_PASSWORD .env 2>/dev/null | cut -d= -f2 | tr -d '"' || echo admin)
curl -s -u "admin:${PASS}" -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload
```

Verify the dashboard updated at `http://localhost:3000/d/portal5-benchmarks`.

### Commit the dashboard update
```bash
git add config/grafana/dashboards/portal5_benchmarks.json
git commit -m "chore(bench): update Grafana benchmarks dashboard from run $(date -u +%Y-%m-%d)"
```

---

## Key Parameters Reference

| Parameter | Default | When to change |
|---|---|---|
| `--runs` | 5 | Lower to `--runs 1` for a fast smoke-test (~30-60min) |
| `--cooldown` | 10 | Raise to `30` if seeing OOM on large-model transitions |
| `--order` | size | Default is `size` (smallest first) — builds inactive memory pool so large models load reliably when they run last. Use `largest` only if the machine has been freshly rebooted with >46GB available confirmed before starting. |
| `--mode` | all | Use `direct` / `pipeline` / `personas` to run a single tier |
| `--model` | (none) | Substring filter for direct-only retests |
| `--workspace` | (none) | Exact workspace ID for pipeline retests |
| `--retry-failed` | off | Resume from most recent results file, skipping successes |

## Known Behavior Notes

- **Reasoning workspaces** (`bench-laguna`, `bench-phi4-reasoning`, `auto-reasoning`, `auto-security`, `auto-redteam`, `auto-mistral`): use 512-token budget and `enable_thinking=False` injection. Their TPS reflects output tokens, not think-block tokens — comparable to non-reasoning models.
- **AEON/Qwen3.6 workspaces** (`auto-security`, `auto-redteam`, `bench-qwen36-27b`, `bench-apriel-nemotron`): emit `/nothink` prefix in the user message to suppress reasoning chain for apples-to-apples TPS.
- **V7 vision models** (`bench-nemotron-omni`, `bench-olmocr2`, `bench-nanonets-ocr2`): run via mlx-vlm path. `bench-nemotron-omni` is 15GB MoE — needs ~25GB free. OCR models (`bench-olmocr2`, `bench-nanonets-ocr2`) are bench-only; not promoted to production routing.
- **bench-apriel-nemotron**: Apriel-Nemotron-15B-Instruct-3.0 — NVIDIA reasoning model, 15GB. Uses `reasoning` prompt category. Emits thinking blocks; `/nothink` suppresses them.
- **UD quant probes** (`bench-qwen36-27b-ud`, `bench-qwen36-35b-a3b-ud`): Unsloth UD-IQ4_XS quantizations from `PULL_UD_QWEN36=true ./launch.sh pull-ud-qwen36`. These are experimental; TPS may vary from standard quants. Available only if the UD models have been pulled.
- **Speech-modality workspaces** (`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`): excluded from all bench modes by `pipeline_bench_skip` in `config/backends.yaml`. Excluded because these workspaces require audio input and their `bench_skip: true` models are audio-generation-only — text-prompt benchmarking produces meaningless results. To force-probe, pass `--workspace bench-voxtral-realtime` explicitly (explicit `--workspace` overrides the skip list).
- **bench-toolace25 / tools-specialist**: ToolACE-style `[func(arg=val)]` and tool-call format respectively. Both use `coding` prompt category — expects structured output.
- **Stale images**: the script prints a freshness warning at startup if portal images predate recent commits. If you see this warning and `portal_pipeline/` or `config/` has changed, stop and run `./launch.sh rebuild` before benchmarking.
- **MLX watchdog**: automatically paused via `/tmp/mlx-watchdog-paused` sentinel for the bench duration. Restored on exit (including Ctrl-C).
- **Ollama cold-start in post-cascade phase**: workspace/persona tests dispatched during the model cascade evict Ollama models between MLX loads. The first Ollama-routed entry in the post-cascade `bench_pipeline` phase pays full model load cost. Compare TPS within a phase, not across phases, for warm-load-sensitive analysis.

---

## Final Deliverables

When done, confirm:

1. `tests/benchmarks/results/bench_tps_<timestamp>Z.json` exists with ≥236 results
2. `config/grafana/dashboards/portal5_benchmarks.json` updated (check `version` field incremented)
3. Grafana dashboard reloaded at `http://localhost:3000/d/portal5-benchmarks`
4. Any unexpected failures (available=True, TPS=0) documented with root cause
5. Commit the dashboard JSON update to git
